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
import com.o2monitor.app.data.ReadingRepository
import dagger.hilt.android.AndroidEntryPoint
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

@AndroidEntryPoint
class BleService : Service() {

    @Inject
    lateinit var prefs: SharedPreferences

    @Inject
    lateinit var repository: ReadingRepository

    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var readingCount = 0

    companion object {
        const val ACTION_READING = "com.o2monitor.READING"
        const val EXTRA_SPO2 = "spo2"
        const val EXTRA_HEART_RATE = "heartRate"
        const val EXTRA_BATTERY_LEVEL = "batteryLevel"
        const val EXTRA_MOVEMENT = "movement"
        const val EXTRA_QUEUE_COUNT = "queueCount"
        const val EXTRA_UPLOAD_OK = "uploadOk"
        const val ACTION_STOP = "com.o2monitor.STOP"

        private const val NOTIFICATION_CHANNEL_ID = "o2monitor_ble"
        private const val NOTIFICATION_ID = 1001
        private const val SCAN_TIMEOUT_MS = 30_000L
        private const val POLL_INTERVAL_MS = 60_000L
        private const val STALE_TIMEOUT_MS = 180_000L
        private const val HISTORY_INTERVAL_MS = 60_000L

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
    private var reconnectAttempt: Int = 0
    private val backoffSchedule = longArrayOf(5_000, 60_000, 120_000, 300_000, 600_000)
    private var session: O2Session? = null
    private val downloadedFiles = mutableSetOf<String>()
    private var sessionInitialized = false
    @Volatile private var sessionBusy = false

    // Runnable refs for cancellation
    private val scanTimeoutRunnable = Runnable { onScanTimeout() }
    private val pollRunnable = object : Runnable {
        override fun run() {
            sendPollCommand()
            handler.postDelayed(this, POLL_INTERVAL_MS)
        }
    }
    private val historyRunnable = object : Runnable {
        override fun run() {
            serviceScope.launch { downloadNewFiles() }
            handler.postDelayed(this, HISTORY_INTERVAL_MS)
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
        startForeground(NOTIFICATION_ID, buildNotification("O2 Monitor", "Initializing…"))
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
        reconnectAttempt = 0
        sessionInitialized = false
        downloadedFiles.clear()
        val g = gatt
        val tx = txCharacteristic
        if (g != null && tx != null) {
            session = O2Session(g, tx)
        }
        handler.post(pollRunnable)
        scheduleStaleWatchdog()
    }

    private fun transitionToReconnecting() {
        cancelAllRunnables()
        session = null
        sessionInitialized = false
        disconnectGatt()
        updateState(BleState.RECONNECTING)
        val delay = backoffSchedule[reconnectAttempt.coerceAtMost(backoffSchedule.size - 1)]
        reconnectAttempt++
        handler.postDelayed(reconnectRunnable, delay)
        android.util.Log.i("BleService", "Reconnecting in ${delay / 1000}s (attempt $reconnectAttempt)")
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
            if (descriptor != null) {
                if (android.os.Build.VERSION.SDK_INT >= 33) {
                    gatt.writeDescriptor(descriptor, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                } else {
                    @Suppress("DEPRECATION")
                    descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    @Suppress("DEPRECATION")
                    gatt.writeDescriptor(descriptor)
                }
            } else {
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
                @Suppress("DEPRECATION")
                handleNotificationData(characteristic.value)
            }
        }

        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray
        ) {
            if (characteristic.uuid == RX_UUID) {
                handleNotificationData(value)
            }
        }
    }

    // ---- Polling ----

    @SuppressLint("MissingPermission")
    private fun sendPollCommand() {
        val tx = txCharacteristic ?: return
        val g = gatt ?: return
        val cmd = BleProtocol.buildCommand(BleProtocol.CMD_READ_SENSORS)
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            g.writeCharacteristic(tx, cmd, BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE)
        } else {
            @Suppress("DEPRECATION")
            tx.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
            @Suppress("DEPRECATION")
            tx.value = cmd
            @Suppress("DEPRECATION")
            g.writeCharacteristic(tx)
        }
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

    private fun handleNotificationData(data: ByteArray) {
        val packets = packetParser.feed(data)
        for (packet in packets) {
            session?.feedParsedPacket(packet)
            // Only parse as live reading when session is NOT busy with commands
            // (otherwise file data gets misinterpreted as vitals)
            if (!sessionBusy) {
                val reading = BleProtocol.parseReading(packet.payload) ?: continue
                handler.post { onReadingReceived(reading) }
            }
        }
    }

    private fun onReadingReceived(reading: OxiReading) {
        latestReading = reading
        lastReadingTimeMs = System.currentTimeMillis()
        readingCount++

        // Reset watchdog
        scheduleStaleWatchdog()

        // After first successful reading, init session and start history downloads
        if (!sessionInitialized && session != null) {
            sessionInitialized = true
            serviceScope.launch {
                sessionBusy = true
                try { session?.setTime(java.time.LocalDateTime.now()) } catch (_: Exception) {}
                sessionBusy = false
                handler.post {
                    handler.postDelayed(historyRunnable, HISTORY_INTERVAL_MS)
                }
            }
        }

        // Enqueue and upload in background
        val patientId = prefs.getString("patient_id", null)
        serviceScope.launch {
            if (patientId != null) {
                repository.enqueue(patientId, reading)
            }
            val uploadOk = repository.flushToCloud()
            val queueCount = repository.pendingCount()

            // Prune expired readings every 100 readings
            if (readingCount % 100 == 0) {
                repository.pruneExpired()
            }

            // Broadcast to UI (on IO thread — LocalBroadcastManager is thread-safe)
            val intent = Intent(ACTION_READING).apply {
                putExtra(EXTRA_SPO2, reading.spo2)
                putExtra(EXTRA_HEART_RATE, reading.heartRate)
                putExtra(EXTRA_BATTERY_LEVEL, reading.batteryLevel)
                putExtra(EXTRA_MOVEMENT, reading.movement)
                putExtra(EXTRA_QUEUE_COUNT, queueCount)
                putExtra(EXTRA_UPLOAD_OK, uploadOk)
            }
            LocalBroadcastManager.getInstance(this@BleService).sendBroadcast(intent)
        }

        // Update notification
        updateNotification()
    }

    // ---- History download ----

    private suspend fun downloadNewFiles() {
        val s = session ?: return
        val patientId = prefs.getString("patient_id", null) ?: return

        sessionBusy = true
        try {
            val info = s.getInfo() ?: return
            val fileListRaw = info["FileList"] ?: return
            val filenames = VldParser.parseFileList(fileListRaw)

            for (filename in filenames) {
                if (filename in downloadedFiles) continue
                val blob = s.downloadFile(filename) ?: continue
                downloadedFiles.add(filename)

                val (header, records) = try {
                    VldParser.parse(blob)
                } catch (_: Exception) { continue }

                val startMs = java.util.Calendar.getInstance().apply {
                    set(header.startYear, header.startMonth - 1, header.startDay,
                        header.startHour, header.startMinute, header.startSecond)
                }.timeInMillis

                for (record in records) {
                    if (!record.isValid) continue
                    val recordMs = startMs + (record.offsetSeconds * 1000).toLong()
                    val reading = OxiReading(spo2 = record.spo2, heartRate = record.heartRate, batteryLevel = 0, movement = record.motion)
                    repository.enqueueAt(patientId, reading, recordMs)
                }

                repository.flushToCloud()
            }
        } catch (e: Exception) {
            android.util.Log.w("BleService", "History download failed: ${e.message}")
        } finally {
            sessionBusy = false
        }
    }

    // ---- Notification ----

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            NOTIFICATION_CHANNEL_ID,
            "O2 Monitor",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Live SpO2 and heart rate monitoring"
            lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
            setShowBadge(true)
        }
        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.createNotificationChannel(channel)
    }

    private fun buildNotification(title: String, text: String): android.app.Notification {
        val builder = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .setSilent(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setCategory(NotificationCompat.CATEGORY_STATUS)

        val r = latestReading
        if (r != null && state == BleState.READING) {
            builder
                .setContentTitle("SpO2 ${r.spo2}%  •  HR ${r.heartRate} bpm")
                .setContentText("Battery ${r.batteryLevel}%")
                .setStyle(NotificationCompat.BigTextStyle()
                    .bigText("SpO2  ${r.spo2}%\nHeart Rate  ${r.heartRate} bpm\nBattery  ${r.batteryLevel}%")
                    .setBigContentTitle("O2 Monitor — Live"))
        } else {
            builder
                .setContentTitle("O2 Monitor")
                .setContentText(text)
        }

        return builder.build()
    }

    private fun updateNotification() {
        val text = when (state) {
            BleState.READING -> {
                val r = latestReading
                if (r != null) "SpO2 ${r.spo2}% | HR ${r.heartRate}"
                else "Connected, waiting for reading…"
            }
            BleState.SCANNING -> "Scanning for oximeter…"
            BleState.CONNECTING -> "Connecting…"
            BleState.RECONNECTING -> "Reconnecting…"
            BleState.IDLE -> "Idle"
        }
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification("O2 Monitor", text))
    }

    // ---- Helpers ----

    private fun cancelAllRunnables() {
        handler.removeCallbacks(scanTimeoutRunnable)
        handler.removeCallbacks(pollRunnable)
        handler.removeCallbacks(historyRunnable)
        handler.removeCallbacks(staleWatchdogRunnable)
        handler.removeCallbacks(reconnectRunnable)
    }
}
