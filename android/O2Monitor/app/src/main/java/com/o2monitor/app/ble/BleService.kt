package com.o2monitor.app.ble

import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Intent
import android.content.SharedPreferences
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import dagger.hilt.android.AndroidEntryPoint
import java.util.UUID
import javax.inject.Inject

@AndroidEntryPoint
class BleService : Service() {

    @Inject
    lateinit var prefs: SharedPreferences

    companion object {
        const val ACTION_READING = "com.o2monitor.READING"
        const val EXTRA_SPO2 = "spo2"
        const val EXTRA_HEART_RATE = "heartRate"
        const val EXTRA_BATTERY_LEVEL = "batteryLevel"
        const val EXTRA_MOVEMENT = "movement"
        const val ACTION_STOP = "com.o2monitor.STOP"

        private const val NOTIFICATION_CHANNEL_ID = "o2monitor_ble"
        private const val NOTIFICATION_ID = 1001
        private const val SCAN_TIMEOUT_MS = 30_000L
        private const val POLL_INTERVAL_MS = 5_000L
        private const val STALE_TIMEOUT_MS = 60_000L

        private val CCCD_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        private val RX_UUID = UUID.fromString(BleProtocol.RX_UUID)
        private val TX_UUID = UUID.fromString(BleProtocol.TX_UUID)
    }

    private var state: BleState = BleState.IDLE
    private var gatt: BluetoothGatt? = null
    private var txCharacteristic: BluetoothGattCharacteristic? = null
    private val packetParser = PacketParser()
    private val handler = Handler(Looper.getMainLooper())
    private var lastReadingTimeMs: Long = 0L
    private var latestReading: OxiReading? = null
    private var reconnectDelayMs: Long = 5_000L

    // Runnable refs for cancellation
    private val scanTimeoutRunnable = Runnable { onScanTimeout() }
    private val pollRunnable = object : Runnable {
        override fun run() {
            sendPollCommand()
            handler.postDelayed(this, POLL_INTERVAL_MS)
        }
    }
    private val staleWatchdogRunnable = Runnable { onStaleTimeout() }
    private val reconnectRunnable = Runnable { transitionToScanning() }

    // ---- Bluetooth objects ----

    private val bluetoothAdapter: BluetoothAdapter? by lazy {
        (getSystemService(BLUETOOTH_SERVICE) as? android.bluetooth.BluetoothManager)?.adapter
    }

    private val scanner: BluetoothLeScanner? get() = bluetoothAdapter?.bluetoothLeScanner

    // ---- Service lifecycle ----

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification("Initializing…"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (state == BleState.IDLE) {
            transitionToScanning()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        cancelAllRunnables()
        disconnectGatt()
        stopBleScan()
        updateState(BleState.IDLE)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ---- State transitions ----

    private fun updateState(newState: BleState) {
        state = newState
        updateNotification()
    }

    private fun transitionToScanning() {
        cancelAllRunnables()
        disconnectGatt()
        reconnectDelayMs = reconnectDelayMs.coerceAtMost(30_000L)
        updateState(BleState.SCANNING)
        startBleScan()
    }

    private fun transitionToConnecting(device: BluetoothDevice) {
        stopBleScan()
        cancelAllRunnables()
        updateState(BleState.CONNECTING)
        connectToDevice(device)
    }

    private fun transitionToReading() {
        updateState(BleState.READING)
        lastReadingTimeMs = System.currentTimeMillis()
        reconnectDelayMs = 5_000L
        handler.post(pollRunnable)
        scheduleStaleWatchdog()
    }

    private fun transitionToReconnecting() {
        cancelAllRunnables()
        disconnectGatt()
        updateState(BleState.RECONNECTING)
        handler.postDelayed(reconnectRunnable, reconnectDelayMs)
        reconnectDelayMs = (reconnectDelayMs * 2).coerceAtMost(30_000L)
    }

    // ---- BLE Scanning ----

    @SuppressLint("MissingPermission")
    private fun startBleScan() {
        val savedMac = prefs.getString("device_mac", null)

        val filters = mutableListOf<ScanFilter>()
        if (!savedMac.isNullOrBlank()) {
            filters.add(
                ScanFilter.Builder()
                    .setDeviceAddress(savedMac)
                    .build()
            )
        } else {
            filters.add(
                ScanFilter.Builder()
                    .setDeviceName(null)
                    .build()
            )
        }

        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()

        scanner?.startScan(filters, settings, scanCallback)
        handler.postDelayed(scanTimeoutRunnable, SCAN_TIMEOUT_MS)
    }

    @SuppressLint("MissingPermission")
    private fun stopBleScan() {
        handler.removeCallbacks(scanTimeoutRunnable)
        scanner?.stopScan(scanCallback)
    }

    private val scanCallback = object : ScanCallback() {
        @SuppressLint("MissingPermission")
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device
            val name = device.name ?: return
            if (name.startsWith("O2M")) {
                transitionToConnecting(device)
            }
        }

        override fun onScanFailed(errorCode: Int) {
            transitionToReconnecting()
        }
    }

    private fun onScanTimeout() {
        stopBleScan()
        transitionToReconnecting()
    }

    // ---- BLE Connection ----

    @SuppressLint("MissingPermission")
    private fun connectToDevice(device: BluetoothDevice) {
        gatt = device.connectGatt(this, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
    }

    @SuppressLint("MissingPermission")
    private fun disconnectGatt() {
        gatt?.disconnect()
        gatt?.close()
        gatt = null
        txCharacteristic = null
    }

    private val gattCallback = object : BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    gatt.discoverServices()
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    handler.post { transitionToReconnecting() }
                }
            }
        }

        @SuppressLint("MissingPermission")
        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                handler.post { transitionToReconnecting() }
                return
            }

            var rxChar: BluetoothGattCharacteristic? = null
            var txChar: BluetoothGattCharacteristic? = null

            for (service in gatt.services) {
                val rx = service.getCharacteristic(RX_UUID)
                val tx = service.getCharacteristic(TX_UUID)
                if (rx != null && tx != null) {
                    rxChar = rx
                    txChar = tx
                    break
                }
            }

            if (rxChar == null || txChar == null) {
                handler.post { transitionToReconnecting() }
                return
            }

            txCharacteristic = txChar

            // Enable notifications on RX characteristic
            gatt.setCharacteristicNotification(rxChar, true)
            val descriptor = rxChar.getDescriptor(CCCD_UUID)
            descriptor?.let {
                it.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                gatt.writeDescriptor(it)
            } ?: run {
                // No CCCD descriptor — proceed directly
                handler.post { transitionToReading() }
            }
        }

        override fun onDescriptorWrite(
            gatt: BluetoothGatt,
            descriptor: BluetoothGattDescriptor,
            status: Int
        ) {
            if (descriptor.uuid == CCCD_UUID) {
                handler.post {
                    if (status == BluetoothGatt.GATT_SUCCESS) {
                        transitionToReading()
                    } else {
                        transitionToReconnecting()
                    }
                }
            }
        }

        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic
        ) {
            if (characteristic.uuid == RX_UUID) {
                val packets = packetParser.feed(characteristic.value)
                for (packet in packets) {
                    val reading = BleProtocol.parseReading(packet.payload) ?: continue
                    handler.post { onReadingReceived(reading) }
                }
            }
        }

        // API level 33+ override — delegate to the compat version above
        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray
        ) {
            if (characteristic.uuid == RX_UUID) {
                val packets = packetParser.feed(value)
                for (packet in packets) {
                    val reading = BleProtocol.parseReading(packet.payload) ?: continue
                    handler.post { onReadingReceived(reading) }
                }
            }
        }
    }

    // ---- Polling ----

    @SuppressLint("MissingPermission")
    private fun sendPollCommand() {
        val tx = txCharacteristic ?: return
        val g = gatt ?: return
        tx.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        tx.value = BleProtocol.buildCommand(BleProtocol.CMD_READ_SENSORS)
        g.writeCharacteristic(tx)
    }

    private fun scheduleStaleWatchdog() {
        handler.removeCallbacks(staleWatchdogRunnable)
        handler.postDelayed(staleWatchdogRunnable, STALE_TIMEOUT_MS)
    }

    private fun onStaleTimeout() {
        if (state == BleState.READING) {
            transitionToReconnecting()
        }
    }

    // ---- Reading handling ----

    private fun onReadingReceived(reading: OxiReading) {
        latestReading = reading
        lastReadingTimeMs = System.currentTimeMillis()

        // Reset watchdog
        scheduleStaleWatchdog()

        // Broadcast to UI
        val intent = Intent(ACTION_READING).apply {
            putExtra(EXTRA_SPO2, reading.spo2)
            putExtra(EXTRA_HEART_RATE, reading.heartRate)
            putExtra(EXTRA_BATTERY_LEVEL, reading.batteryLevel)
            putExtra(EXTRA_MOVEMENT, reading.movement)
        }
        LocalBroadcastManager.getInstance(this).sendBroadcast(intent)

        // Update notification
        updateNotification()
    }

    // ---- Notification ----

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            NOTIFICATION_CHANNEL_ID,
            "O2 Monitor BLE",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "BLE foreground service for oximeter monitoring"
        }
        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.createNotificationChannel(channel)
    }

    private fun buildNotification(text: String) =
        NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle("O2 Monitor")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .setSilent(true)
            .build()

    private fun updateNotification() {
        val text = when (state) {
            BleState.READING -> {
                val r = latestReading
                if (r != null) "Monitoring SpO2 — ${r.spo2}% | HR ${r.heartRate}"
                else "Connected, waiting for reading…"
            }
            BleState.SCANNING -> "Scanning for oximeter…"
            BleState.CONNECTING -> "Connecting…"
            BleState.RECONNECTING -> "Reconnecting…"
            BleState.IDLE -> "Idle"
        }
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }

    // ---- Helpers ----

    private fun cancelAllRunnables() {
        handler.removeCallbacks(scanTimeoutRunnable)
        handler.removeCallbacks(pollRunnable)
        handler.removeCallbacks(staleWatchdogRunnable)
        handler.removeCallbacks(reconnectRunnable)
    }
}
