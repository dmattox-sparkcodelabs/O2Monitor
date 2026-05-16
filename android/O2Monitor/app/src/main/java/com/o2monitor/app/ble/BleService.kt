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
import java.time.LocalDateTime
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
        private const val HISTORY_INTERVAL_MS = 60_000L
        private const val STALE_TIMEOUT_MS = 180_000L  // 3× history interval

        private val CCCD_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        private val RX_UUID = UUID.fromString(BleProtocol.RX_UUID)
        private val TX_UUID = UUID.fromString(BleProtocol.TX_UUID)
    }

    private var state: BleState = BleState.IDLE
    private var gatt: BluetoothGatt? = null
    private var txCharacteristic: BluetoothGattCharacteristic? = null
    private var session: O2Session? = null
    private val handler = Handler(Looper.getMainLooper())
    private var lastReadingTimeMs: Long = 0L
    private var latestReading: OxiReading? = null
    private var reconnectDelayMs: Long = 5_000L

    // Tracks filenames already downloaded in this connection so we don't re-fetch
    private val downloadedFiles = mutableSetOf<String>()

    // Runnable refs for cancellation
    private val scanTimeoutRunnable = Runnable { onScanTimeout() }
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
        downloadedFiles.clear()

        // Build the session now that we have gatt + txCharacteristic
        val g = gatt ?: return
        val tx = txCharacteristic ?: return
        session = O2Session(g, tx)

        // Kick off the initial setup + first poll on the IO dispatcher
        serviceScope.launch { startReadingSession() }

        scheduleStaleWatchdog()
    }

    private fun transitionToReconnecting() {
        cancelAllRunnables()
        session = null
        disconnectGatt()
        updateState(BleState.RECONNECTING)
        handler.postDelayed(reconnectRunnable, reconnectDelayMs)
        reconnectDelayMs = (reconnectDelayMs * 2).coerceAtMost(30_000L)
    }

    // ---- Session startup ----

    /**
     * Called once when READING state is entered (on IO dispatcher via serviceScope).
     *
     * Flow:
     *   1. readSensors() — one immediate live reading for fast dashboard update
     *   2. setTime()     — sync device clock
     *   3. Schedule 60s repeating history download cycle
     */
    private suspend fun startReadingSession() {
        val s = session ?: return

        // 1. Immediate live reading
        val initial = s.readSensors()
        if (initial != null) {
            handler.post { onReadingReceived(initial) }
        }

        // 2. Sync device clock
        s.setTime(LocalDateTime.now())

        // 3. Schedule history download cycle on main thread
        handler.post {
            serviceScope.launch { downloadNewFiles() }
            handler.postDelayed(historyRunnable, HISTORY_INTERVAL_MS)
        }
    }

    // ---- History download ----

    /**
     * Download any new .vld files from the device, parse them, and enqueue the
     * resulting readings.  Called from the IO dispatcher (serviceScope.launch).
     */
    private suspend fun downloadNewFiles() {
        val s = session ?: return

        val info = s.getInfo() ?: return
        val fileListRaw = info["FileList"] ?: return
        val filenames = VldParser.parseFileList(fileListRaw)

        for (filename in filenames) {
            if (filename in downloadedFiles) continue

            val blob = s.downloadFile(filename) ?: continue
            downloadedFiles += filename

            val (header, records) = try {
                VldParser.parse(blob)
            } catch (_: IllegalArgumentException) {
                continue
            }

            val patientId = prefs.getString("patient_id", null)
            var emittedAny = false

            for (record in records) {
                if (!record.isValid) continue

                // Reconstruct the absolute timestamp for this record
                val sessionStart = java.util.Calendar.getInstance().apply {
                    set(
                        header.startYear, header.startMonth - 1, header.startDay,
                        header.startHour, header.startMinute, header.startSecond
                    )
                    set(java.util.Calendar.MILLISECOND, 0)
                }.timeInMillis
                val recordTimestampMs = sessionStart + (record.offsetSeconds * 1000).toLong()

                val reading = OxiReading(
                    spo2 = record.spo2,
                    heartRate = record.heartRate,
                    batteryLevel = 0,  // battery not stored in .vld records
                    movement = record.motion
                )

                if (patientId != null) {
                    repository.enqueueAt(patientId, reading, recordTimestampMs)
                }
                emittedAny = true

                // Broadcast the most recent reading for dashboard updates
                handler.post { onReadingReceived(reading) }
            }

            if (emittedAny) {
                readingCount++
                val uploadOk = repository.flushToCloud()
                val queueCount = repository.pendingCount()

                if (readingCount % 100 == 0) {
                    repository.pruneExpired()
                }

                // Update the broadcast with queue state on the last reading
                val last = records.lastOrNull { it.isValid }
                if (last != null) {
                    val lastReading = OxiReading(
                        spo2 = last.spo2,
                        heartRate = last.heartRate,
                        batteryLevel = 0,
                        movement = last.motion
                    )
                    val intent = Intent(ACTION_READING).apply {
                        putExtra(EXTRA_SPO2, lastReading.spo2)
                        putExtra(EXTRA_HEART_RATE, lastReading.heartRate)
                        putExtra(EXTRA_BATTERY_LEVEL, lastReading.batteryLevel)
                        putExtra(EXTRA_MOVEMENT, lastReading.movement)
                        putExtra(EXTRA_QUEUE_COUNT, queueCount)
                        putExtra(EXTRA_UPLOAD_OK, uploadOk)
                    }
                    LocalBroadcastManager.getInstance(this@BleService).sendBroadcast(intent)
                }
            }
        }
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
                session?.feedNotification(characteristic.value)
            }
        }

        // API level 33+ override — delegate to the session
        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray
        ) {
            if (characteristic.uuid == RX_UUID) {
                session?.feedNotification(value)
            }
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

    private fun onReadingReceived(reading: OxiReading) {
        latestReading = reading
        lastReadingTimeMs = System.currentTimeMillis()

        // Reset stale watchdog whenever we successfully process data
        scheduleStaleWatchdog()

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
        handler.removeCallbacks(historyRunnable)
        handler.removeCallbacks(staleWatchdogRunnable)
        handler.removeCallbacks(reconnectRunnable)
    }
}
