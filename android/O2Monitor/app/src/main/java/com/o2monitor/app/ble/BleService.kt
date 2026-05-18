package com.o2monitor.app.ble

import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
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
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Intent
import android.content.SharedPreferences
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import com.o2monitor.app.MainActivity
import com.o2monitor.app.data.ReadingRepository
import dagger.hilt.android.AndroidEntryPoint
import java.time.LocalDateTime
import java.util.Calendar
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
        const val ACTION_STATE = "com.o2monitor.STATE"
        const val EXTRA_SPO2 = "spo2"
        const val EXTRA_HEART_RATE = "heartRate"
        const val EXTRA_BATTERY_LEVEL = "batteryLevel"
        const val EXTRA_MOVEMENT = "movement"
        const val EXTRA_QUEUE_COUNT = "queueCount"
        const val EXTRA_UPLOAD_OK = "uploadOk"
        const val EXTRA_STATE = "state"
        const val ACTION_STOP = "com.o2monitor.STOP"

        private const val NOTIFICATION_CHANNEL_ID = "o2monitor_ble_v2"
        private const val NOTIFICATION_ID = 1001
        private const val SCAN_TIMEOUT_MS = 30_000L
        private const val HISTORY_SYNC_INTERVAL_MS = 60_000L
        private const val SENSOR_UNRESPONSIVE_RETRY_MS = 5 * 60_000L
        private const val STALE_TIMEOUT_MS = 180_000L
        private const val CCCD_WRITE_TIMEOUT_MS = 3_000L
        private const val MTU_REQUEST_TIMEOUT_MS = 1_500L
        private const val REQUESTED_MTU = 64
        private const val TAG = "BleService"

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
    private var servicesDiscoveryStarted = false
    private var session: O2Session? = null
    private val historyFileProgress = mutableMapOf<String, HistoryFileProgress>()
    private var loadedHistoryProgressKey: String? = null
    @Volatile private var historySyncBusy = false
    @Volatile private var historyClockSynced = false

    // Runnable refs for cancellation
    private val scanTimeoutRunnable = Runnable { onScanTimeout() }
    private val mtuRequestTimeoutRunnable = Runnable { gatt?.let { discoverServicesOnce(it) } }
    private val descriptorWriteTimeoutRunnable = Runnable { onDescriptorWriteTimeout() }
    private val historySyncRunnable = Runnable { syncHistory() }
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
        // Re-broadcast current state so dashboard picks it up when it (re)attaches
        broadcastState(state)
        latestReading?.let { sendReadingBroadcast(it, 0, true) }
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
        if (state != newState) {
            android.util.Log.i(TAG, "State: $state -> $newState")
        }
        state = newState
        broadcastState(newState)
        updateNotification()
    }

    private fun transitionToScanning() {
        cancelAllRunnables()
        disconnectGatt()
        reconnectDelayMs = reconnectDelayMs.coerceAtMost(SENSOR_UNRESPONSIVE_RETRY_MS)
        updateState(BleState.SCANNING)
        startBleScan()
    }

    private fun transitionToConnecting(device: BluetoothDevice) {
        stopBleScan()
        cancelAllRunnables()
        servicesDiscoveryStarted = false
        updateState(BleState.CONNECTING)
        connectToDevice(device)
    }

    private fun transitionToReading() {
        updateState(BleState.READING)
        lastReadingTimeMs = System.currentTimeMillis()
        reconnectDelayMs = 5_000L
        historySyncBusy = false
        historyClockSynced = false
        historyFileProgress.clear()
        loadedHistoryProgressKey = null
        val g = gatt
        val tx = txCharacteristic
        if (g == null || tx == null) {
            android.util.Log.w(TAG, "Cannot start history sync without an active GATT session")
            transitionToReconnecting()
            return
        }
        session = O2Session(g, tx)
        scheduleHistorySync(0L)
        scheduleStaleWatchdog()
    }

    private fun transitionToReconnecting(retryDelayMs: Long? = null) {
        cancelAllRunnables()
        session = null
        historySyncBusy = false
        historyClockSynced = false
        disconnectGatt()
        updateState(BleState.RECONNECTING)
        val delay = retryDelayMs ?: reconnectDelayMs
        handler.postDelayed(reconnectRunnable, delay)
        reconnectDelayMs = if (retryDelayMs == null) {
            (reconnectDelayMs * 2).coerceAtMost(SENSOR_UNRESPONSIVE_RETRY_MS)
        } else {
            SENSOR_UNRESPONSIVE_RETRY_MS
        }
    }

    // ---- BLE Scanning ----

    @SuppressLint("MissingPermission")
    private fun startBleScan() {
        val bleScanner = scanner
        if (bleScanner == null) {
            android.util.Log.e(TAG, "BLE scanner unavailable; Bluetooth may be off")
            transitionToReconnecting()
            return
        }

        stopBleScan()

        val savedMac = prefs.getString("device_mac", null)?.trim()
        android.util.Log.i(TAG, "Starting BLE scan (savedMac=$savedMac)")

        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()

        try {
            bleScanner.startScan(null, settings, scanCallback)
            android.util.Log.i(TAG, "BLE scan started")
        } catch (e: Exception) {
            android.util.Log.e(TAG, "BLE scan failed to start: ${e.message}")
            transitionToReconnecting()
            return
        }
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
            if (state != BleState.SCANNING) return

            val device = result.device
            val name = device.name ?: result.scanRecord?.deviceName ?: ""
            val savedMac = prefs.getString("device_mac", null)?.trim()
            val macMatches = !savedMac.isNullOrBlank() &&
                device.address.equals(savedMac, ignoreCase = true)
            val nameMatches = name.startsWith("O2") ||
                name.startsWith("Checkme") ||
                name.startsWith("Viatom") ||
                name.startsWith("Wellue")
            val shouldConnect = macMatches || (savedMac.isNullOrBlank() && nameMatches)

            if (shouldConnect) {
                android.util.Log.i(TAG, "Found oximeter: name='$name' address=${device.address}")
                if (savedMac != device.address) {
                    prefs.edit().putString("device_mac", device.address).apply()
                }
                transitionToConnecting(device)
            } else if (!savedMac.isNullOrBlank() && nameMatches) {
                android.util.Log.i(
                    TAG,
                    "Ignoring oximeter name='$name' address=${device.address}; savedMac=$savedMac"
                )
            }
        }

        override fun onScanFailed(errorCode: Int) {
            android.util.Log.e(TAG, "BLE scan failed with error code $errorCode")
            transitionToReconnecting()
        }
    }

    private fun onScanTimeout() {
        android.util.Log.w(TAG, "BLE scan timed out")
        stopBleScan()
        transitionToReconnecting()
    }

    // ---- BLE Connection ----

    @SuppressLint("MissingPermission")
    private fun connectToDevice(device: BluetoothDevice) {
        android.util.Log.i(TAG, "Connecting to ${device.address}")
        gatt = device.connectGatt(this, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
    }

    @SuppressLint("MissingPermission")
    private fun disconnectGatt() {
        gatt?.disconnect()
        gatt?.close()
        gatt = null
        txCharacteristic = null
        session = null
        servicesDiscoveryStarted = false
    }

    @SuppressLint("MissingPermission")
    private fun requestMtuThenDiscover(gatt: BluetoothGatt) {
        val requested = gatt.requestMtu(REQUESTED_MTU)
        android.util.Log.i(TAG, "MTU request $REQUESTED_MTU started=$requested")
        if (requested) {
            handler.postDelayed(mtuRequestTimeoutRunnable, MTU_REQUEST_TIMEOUT_MS)
        } else {
            discoverServicesOnce(gatt)
        }
    }

    @SuppressLint("MissingPermission")
    private fun discoverServicesOnce(gatt: BluetoothGatt) {
        if (gatt != this.gatt || servicesDiscoveryStarted) return
        servicesDiscoveryStarted = true
        val started = gatt.discoverServices()
        android.util.Log.i(TAG, "Service discovery requested: started=$started")
        if (!started) {
            handler.post { transitionToReconnecting() }
        }
    }

    private val gattCallback = object : BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            if (gatt != this@BleService.gatt) return
            android.util.Log.i(TAG, "Connection state changed: status=$status newState=$newState")
            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    if (status == BluetoothGatt.GATT_SUCCESS) {
                        requestMtuThenDiscover(gatt)
                    } else {
                        handler.post { transitionToReconnecting() }
                    }
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    handler.post { transitionToReconnecting() }
                }
            }
        }

        @SuppressLint("MissingPermission")
        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            if (gatt != this@BleService.gatt) return
            android.util.Log.i(TAG, "Services discovered: status=$status services=${gatt.services.size}")
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
            android.util.Log.i(TAG, "Found RX/TX characteristics")

            // Enable notifications on RX characteristic
            val notificationSet = gatt.setCharacteristicNotification(rxChar, true)
            if (!notificationSet) {
                android.util.Log.e(TAG, "setCharacteristicNotification failed")
                handler.post { transitionToReconnecting() }
                return
            }
            val descriptor = rxChar.getDescriptor(CCCD_UUID)
            if (descriptor != null) {
                if (android.os.Build.VERSION.SDK_INT >= 33) {
                    val result = gatt.writeDescriptor(
                        descriptor,
                        BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    )
                    android.util.Log.i(TAG, "CCCD write requested: result=$result")
                } else {
                    @Suppress("DEPRECATION")
                    descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    @Suppress("DEPRECATION")
                    val started = gatt.writeDescriptor(descriptor)
                    android.util.Log.i(TAG, "CCCD write requested: started=$started")
                }
                handler.postDelayed(descriptorWriteTimeoutRunnable, CCCD_WRITE_TIMEOUT_MS)
            } else {
                android.util.Log.w(TAG, "CCCD descriptor missing; proceeding after local notification enable")
                handler.post { transitionToReading() }
            }
        }

        @SuppressLint("MissingPermission")
        override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
            if (gatt != this@BleService.gatt) return
            android.util.Log.i(TAG, "MTU changed: mtu=$mtu status=$status")
            handler.removeCallbacks(mtuRequestTimeoutRunnable)
            discoverServicesOnce(gatt)
        }

        override fun onDescriptorWrite(
            gatt: BluetoothGatt,
            descriptor: BluetoothGattDescriptor,
            status: Int
        ) {
            if (gatt != this@BleService.gatt) return
            if (descriptor.uuid == CCCD_UUID) {
                handler.post {
                    handler.removeCallbacks(descriptorWriteTimeoutRunnable)
                    android.util.Log.i(TAG, "CCCD write completed: status=$status")
                    if (state != BleState.CONNECTING) return@post
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
            if (gatt != this@BleService.gatt) return
            if (characteristic.uuid == RX_UUID) {
                handleNotificationData(characteristic.value)
            }
        }

        // API level 33+ override — delegate to the compat version above
        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray
        ) {
            if (gatt != this@BleService.gatt) return
            if (characteristic.uuid == RX_UUID) {
                handleNotificationData(value)
            }
        }
    }

    private fun onDescriptorWriteTimeout() {
        if (state == BleState.CONNECTING) {
            android.util.Log.w(TAG, "CCCD write callback timed out; proceeding to reading")
            transitionToReading()
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
            if (packet.status != 0) {
                android.util.Log.w(TAG, "Device response status=${packet.status}")
            }
        }
    }

    // ---- History sync ----

    private data class HistorySyncResult(
        val deviceResponded: Boolean = false,
        val insertedCount: Int = 0,
        val latestReading: OxiReading? = null,
        val currentBatteryLevel: Int? = null
    )

    private data class HistoryFileProgress(
        val recordCount: Int,
        val complete: Boolean
    )

    private fun syncHistory() {
        if (state != BleState.READING) return
        if (historySyncBusy) {
            android.util.Log.d(TAG, "History sync skipped; previous sync is still running")
            scheduleHistorySync(HISTORY_SYNC_INTERVAL_MS)
            return
        }

        val s = session
        if (s == null) {
            android.util.Log.w(TAG, "History sync skipped; no active session")
            transitionToReconnecting()
            return
        }
        val patientId = prefs.getString("patient_id", null)?.trim()
        if (patientId.isNullOrBlank()) {
            android.util.Log.w(TAG, "History sync skipped; no patient_id configured")
            scheduleHistorySync(HISTORY_SYNC_INTERVAL_MS)
            return
        }

        historySyncBusy = true
        val attemptStartedAtMs = System.currentTimeMillis()
        serviceScope.launch {
            var result = HistorySyncResult()
            var uploadOk = false
            var queueCount = 0
            try {
                // Live sensor read only — no history download for battery savings
                val liveReading = try { s.readSensors() } catch (_: Exception) { null }
                if (liveReading != null) {
                    repository.enqueue(patientId, liveReading)
                    result = HistorySyncResult(
                        deviceResponded = true,
                        latestReading = liveReading
                    )
                } else {
                    result = HistorySyncResult(deviceResponded = false)
                }

                uploadOk = repository.flushToCloud()
                queueCount = repository.pendingCount()
            } catch (e: Exception) {
                android.util.Log.w(TAG, "History sync failed: ${e.message}", e)
            } finally {
                historySyncBusy = false
            }

            handler.post {
                if (state == BleState.READING) {
                    onHistorySyncCompleted(result, queueCount, uploadOk)
                    scheduleNextHistorySync(result.deviceResponded, attemptStartedAtMs)
                }
            }
        }
    }

    private fun scheduleHistorySync(delayMs: Long) {
        if (state != BleState.READING) return
        handler.removeCallbacks(historySyncRunnable)
        handler.postDelayed(historySyncRunnable, delayMs)
    }

    private fun scheduleNextHistorySync(deviceResponded: Boolean, attemptStartedAtMs: Long) {
        if (!deviceResponded) {
            android.util.Log.w(TAG, "History sync: device did not respond; retrying in 5 minutes")
            transitionToReconnecting(SENSOR_UNRESPONSIVE_RETRY_MS)
            return
        }

        val elapsedMs = System.currentTimeMillis() - attemptStartedAtMs
        val delayMs = (HISTORY_SYNC_INTERVAL_MS - elapsedMs).coerceAtLeast(0L)
        scheduleHistorySync(delayMs)
    }

    private suspend fun downloadNewFiles(
        s: O2Session,
        patientId: String
    ): HistorySyncResult {
        ensureHistoryFileProgressLoaded(patientId)

        val info = s.getInfo()
        if (info == null) {
            android.util.Log.w(TAG, "History sync: no response to device info request")
            return HistorySyncResult()
        }

        val fileListRaw = info["FileList"].orEmpty()
        val filenames = VldParser.parseFileList(fileListRaw)
        val currentBatteryLevel = parseBatteryLevel(info["CurBAT"])
        if (filenames.isEmpty()) {
            android.util.Log.i(TAG, "History sync: device has no stored recordings")
            return HistorySyncResult(
                deviceResponded = true,
                currentBatteryLevel = currentBatteryLevel
            )
        }

        var insertedCount = 0
        var newestTimestampMs = Long.MIN_VALUE
        var newestReading: OxiReading? = null
        var inspectedFiles = 0

        val filesToInspect = filenames
            .filter { historyFileProgress[it]?.complete != true }
            .toMutableList()
        val newestFilename = filenames.maxOrNull()
        // The active recording can keep growing under the same filename, so always
        // inspect the newest file on each one-minute sync. Progress tracking below
        // prevents duplicate enqueues when the record count has not changed.
        if (newestFilename != null && newestFilename !in filesToInspect) {
            filesToInspect.add(newestFilename)
        }
        android.util.Log.i(
            TAG,
            "History sync: ${filesToInspect.size} file(s) to inspect (${filenames.size} listed)"
        )

        for (filename in filesToInspect) {
            val blob = s.downloadFile(filename)
            if (blob == null) {
                android.util.Log.w(TAG, "History sync: failed to download $filename")
                continue
            }

            val parsed = try {
                VldParser.parse(blob)
            } catch (e: Exception) {
                android.util.Log.w(TAG, "History sync: failed to parse $filename: ${e.message}")
                continue
            }

            val (header, records) = parsed
            val previousRecordCount = historyFileProgress[filename]?.recordCount ?: 0
            val firstNewRecordIndex = previousRecordCount.coerceIn(0, records.size)
            val startMs = Calendar.getInstance().apply {
                clear()
                set(
                    header.startYear,
                    header.startMonth - 1,
                    header.startDay,
                    header.startHour,
                    header.startMinute,
                    header.startSecond
                )
            }.timeInMillis

            var validRecords = 0
            for ((recordIndex, record) in records.withIndex()) {
                if (!record.isValid) continue
                val recordMs = startMs + (record.offsetSeconds * 1000).toLong()
                val reading = OxiReading(
                    spo2 = record.spo2,
                    heartRate = record.heartRate,
                    batteryLevel = currentBatteryLevel ?: 0,
                    movement = record.motion
                )
                if (recordMs > newestTimestampMs) {
                    newestTimestampMs = recordMs
                    newestReading = reading
                }
                if (recordIndex < firstNewRecordIndex) continue
                repository.enqueueAt(patientId, reading, recordMs)
                validRecords++
                insertedCount++
            }

            historyFileProgress[filename] = HistoryFileProgress(
                recordCount = records.size,
                complete = header.durationSeconds > 0
            )
            saveHistoryFileProgress(patientId)
            inspectedFiles++
            android.util.Log.i(
                TAG,
                "History sync: $filename downloaded (${blob.size} bytes, $validRecords new valid records)"
            )
        }

        android.util.Log.i(
            TAG,
            "History sync complete: $inspectedFiles file(s), $insertedCount reading(s)"
        )
        return HistorySyncResult(
            deviceResponded = true,
            insertedCount = insertedCount,
            latestReading = newestReading,
            currentBatteryLevel = currentBatteryLevel
        )
    }

    private fun onHistorySyncCompleted(
        result: HistorySyncResult,
        queueCount: Int,
        uploadOk: Boolean
    ) {
        if (result.deviceResponded) {
            lastReadingTimeMs = System.currentTimeMillis()
            scheduleStaleWatchdog()
        }
        if (result.insertedCount > 0) {
            readingCount += result.insertedCount
        }
        val reading = result.latestReading
        if (reading != null) {
            latestReading = reading
            android.util.Log.i(
                TAG,
                "Latest history reading: SpO2=${reading.spo2} HR=${reading.heartRate}"
            )
            // Always enqueue the latest reading so cloud has current data
            val patientId = prefs.getString("patient_id", null)
            if (patientId != null && result.insertedCount == 0) {
                serviceScope.launch {
                    repository.enqueue(patientId, reading)
                    repository.flushToCloud()
                }
            }
            sendReadingBroadcast(reading, queueCount, uploadOk)
        } else if (result.currentBatteryLevel != null && latestReading?.batteryLevel == 0) {
            latestReading = latestReading?.copy(batteryLevel = result.currentBatteryLevel)
            latestReading?.let { sendReadingBroadcast(it, queueCount, uploadOk) }
        }
        updateNotification()
    }

    private fun onReadingReceived(reading: OxiReading) {
        latestReading = reading
        lastReadingTimeMs = System.currentTimeMillis()
        readingCount++

        // Reset watchdog
        scheduleStaleWatchdog()

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

            sendReadingBroadcast(reading, queueCount, uploadOk)
        }

        // Update notification
        updateNotification()
    }

    private fun sendReadingBroadcast(reading: OxiReading, queueCount: Int, uploadOk: Boolean) {
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

    // ---- Notification ----

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            NOTIFICATION_CHANNEL_ID,
            "O2 Monitor",
            NotificationManager.IMPORTANCE_DEFAULT
        ).apply {
            description = "Live SpO2 and heart rate monitoring"
            lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
            setShowBadge(true)
        }
        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.createNotificationChannel(channel)
    }

    private fun buildNotification(text: String): android.app.Notification {
        val contentIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val r = latestReading
        val title: String
        val contentText: String
        val expandedText: String
        if (r != null && state == BleState.READING) {
            title = "SpO2 ${r.spo2}%  •  HR ${r.heartRate} bpm"
            if (r.batteryLevel > 0) {
                contentText = "Battery ${r.batteryLevel}%"
                expandedText = "SpO2  ${r.spo2}%\nHeart Rate  ${r.heartRate} bpm\nBattery  ${r.batteryLevel}%"
            } else {
                contentText = "History reading"
                expandedText = "SpO2  ${r.spo2}%\nHeart Rate  ${r.heartRate} bpm\nSource  History"
            }
        } else {
            title = "O2 Monitor"
            contentText = text
            expandedText = text
        }

        val publicNotification = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .setSilent(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setContentTitle(title)
            .setContentText(contentText)
            .setContentIntent(contentIntent)
            .build()

        val builder = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .setSilent(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setPublicVersion(publicNotification)
            .setContentIntent(contentIntent)
            .setContentTitle(title)
            .setContentText(contentText)

        if (r != null && state == BleState.READING) {
            builder.setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText(expandedText)
                    .setBigContentTitle("O2 Monitor — Live")
            )
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
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }

    // ---- Helpers ----

    private fun cancelAllRunnables() {
        handler.removeCallbacks(scanTimeoutRunnable)
        handler.removeCallbacks(mtuRequestTimeoutRunnable)
        handler.removeCallbacks(descriptorWriteTimeoutRunnable)
        handler.removeCallbacks(historySyncRunnable)
        handler.removeCallbacks(staleWatchdogRunnable)
        handler.removeCallbacks(reconnectRunnable)
    }

    private fun ensureHistoryFileProgressLoaded(patientId: String) {
        val key = historyFileProgressKey(patientId)
        if (loadedHistoryProgressKey == key) return
        historyFileProgress.clear()
        val entries = prefs.getStringSet(key, emptySet<String>()).orEmpty()
        for (entry in entries) {
            val parts = entry.split("\t")
            if (parts.size != 3) continue
            val recordCount = parts[1].toIntOrNull() ?: continue
            val complete = parts[2] == "1"
            historyFileProgress[parts[0]] = HistoryFileProgress(recordCount, complete)
        }
        loadedHistoryProgressKey = key
    }

    private fun saveHistoryFileProgress(patientId: String) {
        val entries = historyFileProgress.map { (filename, progress) ->
            "$filename\t${progress.recordCount}\t${if (progress.complete) "1" else "0"}"
        }.toMutableSet()
        prefs.edit()
            .putStringSet(historyFileProgressKey(patientId), entries)
            .apply()
    }

    private fun historyFileProgressKey(patientId: String): String {
        val deviceKey = prefs.getString("device_mac", null)
            ?.trim()
            ?.replace(":", "")
            ?.ifBlank { null }
            ?: "unknown_device"
        return "history_file_progress_${patientId}_$deviceKey"
    }

    private fun parseBatteryLevel(raw: String?): Int? =
        raw
            ?.filter { it.isDigit() }
            ?.toIntOrNull()
            ?.coerceIn(0, 100)

    private fun broadcastState(newState: BleState) {
        val intent = Intent(ACTION_STATE).apply {
            putExtra(EXTRA_STATE, newState.name)
        }
        LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
    }

    private fun ByteArray.toHexString(): String =
        joinToString(" ") { "%02X".format(it) }
}
