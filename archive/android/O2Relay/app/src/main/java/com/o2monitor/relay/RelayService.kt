package com.o2monitor.relay

import android.annotation.SuppressLint
import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.bluetooth.BluetoothDevice
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Binder
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*

/**
 * Foreground service that manages the relay state machine.
 *
 * States:
 * - DORMANT: Pi is handling readings, phone checks in periodically
 * - SCANNING: Looking for oximeter via BLE
 * - CONNECTED: Reading from oximeter and relaying to Pi
 * - QUEUING: Connected to oximeter but Pi unreachable, storing locally
 */
class RelayService : Service() {

    companion object {
        private const val TAG = "RelayService"
        private const val NOTIFICATION_ID = 1

        // Timing constants
        private const val READING_INTERVAL_MS = 5_000L        // 5 seconds
        private const val SCAN_TIMEOUT_MS = 30_000L           // 30 seconds
        private const val PI_RETRY_INTERVAL_MS = 10_000L      // 10 seconds (QUEUING state)

        // BLE reconnect backoff constants
        private val RECONNECT_BACKOFF_MS = longArrayOf(5_000, 10_000, 20_000, 30_000)
        private const val MAX_RECONNECT_ATTEMPTS = 4

        // Network error tracking
        private const val MAX_NETWORK_FAILURES = 3

        // Intent actions
        const val ACTION_START = "com.o2monitor.relay.START"
        const val ACTION_STOP = "com.o2monitor.relay.STOP"
    }

    /**
     * Service states
     */
    enum class State {
        STOPPED,
        DORMANT,
        SCANNING,
        CONNECTED,
        QUEUING
    }

    // Current state
    var state: State = State.STOPPED
        private set

    // Service binder for MainActivity
    private val binder = RelayBinder()

    // Components
    private lateinit var settingsManager: SettingsManager
    private lateinit var bleManager: BleManager
    private lateinit var apiClient: ApiClient
    private lateinit var readingQueue: ReadingQueue

    // Coroutine scope for async operations
    private val serviceScope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    // Handler for timers
    private val handler = Handler(Looper.getMainLooper())

    // Timer runnables
    private var checkInRunnable: Runnable? = null
    private var readingRunnable: Runnable? = null
    private var piRetryRunnable: Runnable? = null
    private var reconnectRunnable: Runnable? = null

    // State tracking
    private var lastReading: OxiReading? = null
    private var readingsSentCount: Int = 0
    private var readingsQueuedCount: Int = 0
    private var lastCheckInTime: Long = 0
    private var lastPiStatus: RelayStatus? = null

    // Reconnect tracking
    private var reconnectAttempts: Int = 0
    private var consecutiveNetworkFailures: Int = 0

    // Listener for UI updates
    var stateListener: StateListener? = null

    interface StateListener {
        fun onStateChanged(state: State)
        fun onReadingReceived(reading: OxiReading)
        fun onStatusUpdate(status: String)
        fun onError(message: String)
    }

    // ==================== Service Lifecycle ====================

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "RelayService onCreate")

        // Initialize settings
        settingsManager = SettingsManager(this)

        // Initialize components with settings
        bleManager = BleManager(this).apply {
            targetMac = settingsManager.oximeterMac
            callback = bleCallback
        }

        apiClient = ApiClient(
            baseUrl = settingsManager.serverUrl,
            deviceId = settingsManager.deviceId
        )

        // Load auth token from settings
        if (settingsManager.hasValidToken()) {
            apiClient.authToken = settingsManager.authToken
            Log.i(TAG, "Loaded auth token for user: ${settingsManager.authUsername}")
        } else {
            Log.w(TAG, "No valid auth token - API calls may fail")
        }

        readingQueue = ReadingQueue(this)

        Log.i(TAG, "Settings: server=${settingsManager.serverUrl}, mac=${settingsManager.oximeterMac}, deviceId=${settingsManager.deviceId}")
        Log.i(TAG, "Queue status: ${readingQueue.count()} readings queued")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "RelayService onStartCommand: ${intent?.action}")

        when (intent?.action) {
            ACTION_STOP -> {
                stopRelayService()
                return START_NOT_STICKY
            }
            ACTION_START, null -> {
                startRelayService()
            }
        }

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder {
        return binder
    }

    override fun onDestroy() {
        Log.i(TAG, "RelayService onDestroy")
        stopRelayService()
        serviceScope.cancel()
        readingQueue.close()
        super.onDestroy()
    }

    // ==================== Binder ====================

    inner class RelayBinder : Binder() {
        fun getService(): RelayService = this@RelayService
    }

    // ==================== Service Control ====================

    private fun startRelayService() {
        if (state != State.STOPPED) {
            Log.w(TAG, "Service already running in state: $state")
            return
        }

        Log.i(TAG, "Starting relay service")

        // Reload auth token (may have been set after onCreate)
        reloadAuthToken()

        // Mark service as enabled for restart after reboot
        settingsManager.serviceEnabled = true

        // Start as foreground service
        startForeground()

        // Transition to DORMANT state
        transitionTo(State.DORMANT)
    }

    /**
     * Reload auth token from settings. Called on service start in case
     * token was obtained after onCreate (e.g., user logged in).
     */
    private fun reloadAuthToken() {
        if (settingsManager.hasValidToken()) {
            apiClient.authToken = settingsManager.authToken
            Log.i(TAG, "Auth token loaded for user: ${settingsManager.authUsername}")
        } else {
            apiClient.authToken = null
            Log.w(TAG, "No valid auth token available")
        }
    }

    private fun stopRelayService() {
        Log.i(TAG, "Stopping relay service")

        // Mark service as disabled
        settingsManager.serviceEnabled = false

        // Cancel all timers
        cancelAllTimers()

        // Disconnect BLE
        bleManager.cleanup()

        // Update state
        state = State.STOPPED
        notifyStateChanged()

        // Stop foreground
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }

        stopSelf()
    }

    fun stop() {
        stopRelayService()
    }

    // ==================== State Machine ====================

    private fun transitionTo(newState: State) {
        if (state == newState) {
            Log.d(TAG, "Already in state: $newState")
            return
        }

        val oldState = state
        Log.i(TAG, "State transition: $oldState -> $newState")

        // Exit old state
        exitState(oldState)

        // Update state
        state = newState

        // Enter new state
        enterState(newState)

        // Update notification
        updateNotification()

        // Notify listener
        notifyStateChanged()
    }

    private fun exitState(state: State) {
        when (state) {
            State.DORMANT -> {
                cancelCheckInTimer()
            }
            State.SCANNING -> {
                bleManager.stopScan()
            }
            State.CONNECTED -> {
                cancelReadingTimer()
            }
            State.QUEUING -> {
                cancelPiRetryTimer()
            }
            State.STOPPED -> {
                // Nothing to clean up
            }
        }
    }

    private fun enterState(state: State) {
        when (state) {
            State.DORMANT -> {
                // Start check-in timer
                startCheckInTimer()
                // Do initial check-in
                performCheckIn()
            }
            State.SCANNING -> {
                // Start BLE scan
                startBleScanning()
            }
            State.CONNECTED -> {
                // Start reading timer
                startReadingTimer()
                // Request first reading immediately
                requestReading()
            }
            State.QUEUING -> {
                // Start Pi retry timer
                startPiRetryTimer()
            }
            State.STOPPED -> {
                // Nothing to do
            }
        }
    }

    // ==================== DORMANT State ====================

    private fun startCheckInTimer() {
        cancelCheckInTimer()

        val intervalMs = settingsManager.checkInIntervalSeconds * 1000L

        checkInRunnable = object : Runnable {
            override fun run() {
                performCheckIn()
                handler.postDelayed(this, intervalMs)
            }
        }
        handler.postDelayed(checkInRunnable!!, intervalMs)
        Log.d(TAG, "Check-in timer started (${intervalMs}ms interval)")
    }

    private fun cancelCheckInTimer() {
        checkInRunnable?.let { handler.removeCallbacks(it) }
        checkInRunnable = null
    }

    private fun performCheckIn() {
        Log.d(TAG, "Performing check-in...")
        lastCheckInTime = System.currentTimeMillis()

        serviceScope.launch {
            val status = apiClient.getRelayStatus()

            if (status == null) {
                Log.w(TAG, "Check-in failed - Pi unreachable")
                stateListener?.onStatusUpdate("Pi unreachable")
                return@launch
            }

            lastPiStatus = status
            Log.d(TAG, "Check-in result: needsRelay=${status.needsRelay}, readingAge=${status.secondsSinceReading}s, bleConnected=${status.bleConnected}")

            // Build status message with vitals if available
            val vitals = status.currentVitals
            val statusMsg = if (vitals != null && vitals.spo2 > 0) {
                "Pi: ${vitals.spo2}% SpO2, ${vitals.heartRate} HR (${status.secondsSinceReading}s ago)"
            } else {
                "Pi reading: ${status.secondsSinceReading}s ago"
            }
            stateListener?.onStatusUpdate(statusMsg)

            if (status.needsRelay && state == State.DORMANT) {
                Log.i(TAG, "Pi needs relay - transitioning to SCANNING")
                transitionTo(State.SCANNING)
            }
        }
    }

    // ==================== SCANNING State ====================

    private fun startBleScanning() {
        if (!BlePermissions.hasRequiredPermissions(this)) {
            Log.e(TAG, "Missing BLE permissions")
            stateListener?.onError("Missing Bluetooth permissions")
            transitionTo(State.DORMANT)
            return
        }

        if (!bleManager.isBluetoothEnabled()) {
            Log.e(TAG, "Bluetooth not enabled")
            stateListener?.onError("Bluetooth is not enabled")
            transitionTo(State.DORMANT)
            return
        }

        Log.i(TAG, "Starting BLE scan for oximeter")
        stateListener?.onStatusUpdate("Scanning for oximeter...")
        bleManager.startScan(SCAN_TIMEOUT_MS)
    }

    // ==================== CONNECTED State ====================

    private fun startReadingTimer() {
        cancelReadingTimer()

        readingRunnable = object : Runnable {
            override fun run() {
                requestReading()
                handler.postDelayed(this, READING_INTERVAL_MS)
            }
        }
        handler.postDelayed(readingRunnable!!, READING_INTERVAL_MS)
        Log.d(TAG, "Reading timer started (${READING_INTERVAL_MS}ms interval)")
    }

    private fun cancelReadingTimer() {
        readingRunnable?.let { handler.removeCallbacks(it) }
        readingRunnable = null
    }

    private fun requestReading() {
        if (state != State.CONNECTED && state != State.QUEUING) {
            return
        }
        bleManager.requestReading()
    }

    private fun onReadingReceived(reading: OxiReading) {
        Log.i(TAG, "Reading received: SpO2=${reading.spo2}, HR=${reading.heartRate}, Battery=${reading.battery}")
        lastReading = reading
        stateListener?.onReadingReceived(reading)
        updateNotification()

        // Post to Pi
        serviceScope.launch {
            val success = apiClient.postReading(reading, queued = false)

            if (success) {
                // Reset failure tracking on success
                consecutiveNetworkFailures = 0

                readingsSentCount++
                Log.d(TAG, "Reading posted successfully (total sent: $readingsSentCount)")

                // If we were queuing and Pi is now reachable, transition back to CONNECTED
                if (state == State.QUEUING) {
                    Log.i(TAG, "Pi reachable again - transitioning to CONNECTED")
                    transitionTo(State.CONNECTED)
                }
            } else {
                consecutiveNetworkFailures++
                Log.w(TAG, "Failed to post reading to Pi (consecutive failures: $consecutiveNetworkFailures)")

                // Queue reading locally
                val queueId = readingQueue.enqueue(reading)
                if (queueId != -1L) {
                    readingsQueuedCount = readingQueue.count()
                    Log.d(TAG, "Reading queued locally (queue size: $readingsQueuedCount)")
                    stateListener?.onStatusUpdate("Queued: $readingsQueuedCount readings")
                }

                // If we're CONNECTED and Pi becomes unreachable, transition to QUEUING
                if (state == State.CONNECTED) {
                    Log.i(TAG, "Pi unreachable - transitioning to QUEUING")
                    transitionTo(State.QUEUING)
                }
            }
        }
    }

    // ==================== QUEUING State ====================

    private fun startPiRetryTimer() {
        cancelPiRetryTimer()

        piRetryRunnable = object : Runnable {
            override fun run() {
                checkPiAndFlushQueue()
                handler.postDelayed(this, PI_RETRY_INTERVAL_MS)
            }
        }
        handler.postDelayed(piRetryRunnable!!, PI_RETRY_INTERVAL_MS)
        Log.d(TAG, "Pi retry timer started (${PI_RETRY_INTERVAL_MS}ms interval)")
    }

    private fun cancelPiRetryTimer() {
        piRetryRunnable?.let { handler.removeCallbacks(it) }
        piRetryRunnable = null
    }

    private fun checkPiAndFlushQueue() {
        Log.d(TAG, "Checking if Pi is reachable...")

        serviceScope.launch {
            val reachable = apiClient.isReachable()

            if (reachable) {
                Log.i(TAG, "Pi is reachable again - flushing queue")
                flushQueue()
                transitionTo(State.CONNECTED)
            } else {
                Log.d(TAG, "Pi still unreachable")
                val queueSize = readingQueue.count()
                stateListener?.onStatusUpdate("Pi unreachable - $queueSize queued")
            }
        }
    }

    /**
     * Flush queued readings to the Pi using batch upload.
     * Throttled to avoid overwhelming the Pi.
     */
    private suspend fun flushQueue() {
        // Prune expired readings first
        readingQueue.pruneExpired()

        val queueSize = readingQueue.count()
        if (queueSize == 0) {
            Log.d(TAG, "Queue is empty, nothing to flush")
            return
        }

        Log.i(TAG, "Flushing $queueSize queued readings...")
        stateListener?.onStatusUpdate("Uploading $queueSize queued readings...")

        // Process in batches of 100 with throttling
        // Newest first - recent readings are more valuable for monitoring
        var totalSent = 0
        var totalFailed = 0
        var batchCount = 0

        while (true) {
            val batch = readingQueue.peek(limit = 100, newestFirst = true)
            if (batch.isEmpty()) break

            val readings = batch.map { it.reading }
            val response = apiClient.postBatch(readings)

            if (response != null && response.status == "ok") {
                // Remove successfully sent readings
                val ids = batch.map { it.id }
                readingQueue.remove(ids)
                totalSent += response.accepted
                totalFailed += response.rejected
                batchCount++
                Log.d(TAG, "Batch $batchCount uploaded: ${response.accepted} accepted, ${response.rejected} rejected")

                // Throttle: 500ms delay between batches to avoid overwhelming Pi
                val remaining = readingQueue.count()
                if (remaining > 0) {
                    stateListener?.onStatusUpdate("Uploading... $remaining remaining")
                    delay(500)
                }
            } else {
                // Stop flushing on error
                Log.w(TAG, "Batch upload failed, stopping flush")
                break
            }
        }

        readingsQueuedCount = readingQueue.count()
        readingsSentCount += totalSent

        if (totalSent > 0) {
            Log.i(TAG, "Queue flush complete: $totalSent sent, $totalFailed rejected, $readingsQueuedCount remaining")
            stateListener?.onStatusUpdate("Uploaded $totalSent readings")
        }
    }

    // ==================== BLE Callbacks ====================

    private val bleCallback = object : BleManager.Callback {
        override fun onConnected() {
            Log.i(TAG, "BLE connected to oximeter")
            handler.post {
                // Reset reconnect tracking on successful connection
                resetReconnectTracking()

                if (state == State.SCANNING) {
                    transitionTo(State.CONNECTED)
                }
            }
        }

        override fun onDisconnected() {
            Log.i(TAG, "BLE disconnected from oximeter")
            handler.post {
                handleBleDisconnect()
            }
        }

        override fun onReading(reading: OxiReading) {
            handler.post {
                onReadingReceived(reading)
            }
        }

        override fun onError(message: String) {
            Log.e(TAG, "BLE error: $message")
            handler.post {
                stateListener?.onError(message)

                // On scan failure, go back to dormant
                if (state == State.SCANNING) {
                    transitionTo(State.DORMANT)
                }
            }
        }

        override fun onScanResult(device: BluetoothDevice) {
            Log.i(TAG, "Found oximeter: ${device.address}")
            stateListener?.onStatusUpdate("Found device, connecting...")
        }

        override fun onScanFailed(errorCode: Int) {
            Log.e(TAG, "BLE scan failed: $errorCode")
            handler.post {
                stateListener?.onError("Scan failed (error $errorCode)")
                transitionTo(State.DORMANT)
            }
        }
    }

    private fun handleBleDisconnect() {
        if (state != State.CONNECTED && state != State.QUEUING) {
            return
        }

        reconnectAttempts++
        Log.i(TAG, "BLE disconnect - reconnect attempt $reconnectAttempts of $MAX_RECONNECT_ATTEMPTS")

        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            // Max attempts reached - check if Pi needs us before continuing
            Log.i(TAG, "Max reconnect attempts reached - checking Pi status")
            checkPiStatusAfterDisconnect()
        } else {
            // Schedule reconnect with exponential backoff
            scheduleReconnect()
        }
    }

    private fun scheduleReconnect() {
        cancelReconnectTimer()

        val backoffIndex = (reconnectAttempts - 1).coerceIn(0, RECONNECT_BACKOFF_MS.size - 1)
        val delayMs = RECONNECT_BACKOFF_MS[backoffIndex]

        Log.d(TAG, "Scheduling reconnect in ${delayMs}ms (attempt $reconnectAttempts)")
        stateListener?.onStatusUpdate("Reconnecting in ${delayMs / 1000}s...")

        reconnectRunnable = Runnable {
            if (state == State.CONNECTED || state == State.QUEUING) {
                Log.i(TAG, "Attempting BLE reconnect...")
                stateListener?.onStatusUpdate("Reconnecting...")
                transitionTo(State.SCANNING)
            }
        }
        handler.postDelayed(reconnectRunnable!!, delayMs)
    }

    private fun cancelReconnectTimer() {
        reconnectRunnable?.let { handler.removeCallbacks(it) }
        reconnectRunnable = null
    }

    private fun checkPiStatusAfterDisconnect() {
        serviceScope.launch {
            val status = apiClient.getRelayStatus()

            if (status != null && !status.needsRelay) {
                // Pi is getting readings, we can go dormant
                Log.i(TAG, "Pi has recent readings - going DORMANT")
                resetReconnectTracking()
                transitionTo(State.DORMANT)
            } else {
                // Pi still needs help - continue trying with max backoff
                Log.i(TAG, "Pi still needs relay - continuing reconnect attempts")
                scheduleReconnect()
            }
        }
    }

    private fun resetReconnectTracking() {
        reconnectAttempts = 0
        consecutiveNetworkFailures = 0
        cancelReconnectTimer()
    }

    // ==================== Notification ====================

    @SuppressLint("ForegroundServiceType")
    private fun startForeground() {
        val notification = buildNotification()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun updateNotification() {
        val notification = buildNotification()
        val notificationManager = getSystemService(NOTIFICATION_SERVICE) as android.app.NotificationManager
        notificationManager.notify(NOTIFICATION_ID, notification)
    }

    private fun buildNotification(): Notification {
        // Intent to open MainActivity
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pendingOpenIntent = PendingIntent.getActivity(
            this, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Intent to stop service
        val stopIntent = Intent(this, RelayService::class.java).apply {
            action = ACTION_STOP
        }
        val pendingStopIntent = PendingIntent.getService(
            this, 0, stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val (title, text) = getNotificationContent()

        return NotificationCompat.Builder(this, O2RelayApplication.CHANNEL_ID_RELAY_SERVICE)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(pendingOpenIntent)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", pendingStopIntent)
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }

    private fun getNotificationContent(): Pair<String, String> {
        return when (state) {
            State.STOPPED -> "O2 Relay" to "Stopped"
            State.DORMANT -> "O2 Relay - Dormant" to "Pi is reading directly"
            State.SCANNING -> "O2 Relay - Scanning" to "Looking for oximeter..."
            State.CONNECTED -> {
                val reading = lastReading
                if (reading != null) {
                    "O2 Relay - Active" to "SpO2: ${reading.spo2}% HR: ${reading.heartRate} bpm"
                } else {
                    "O2 Relay - Connected" to "Waiting for reading..."
                }
            }
            State.QUEUING -> {
                val reading = lastReading
                if (reading != null) {
                    "O2 Relay - Queuing" to "SpO2: ${reading.spo2}% (Pi offline)"
                } else {
                    "O2 Relay - Queuing" to "Pi offline - storing locally"
                }
            }
        }
    }

    // ==================== Helpers ====================

    private fun cancelAllTimers() {
        cancelCheckInTimer()
        cancelReadingTimer()
        cancelPiRetryTimer()
        cancelReconnectTimer()
    }

    private fun notifyStateChanged() {
        stateListener?.onStateChanged(state)
    }

    // ==================== Public Accessors ====================

    fun getLastReading(): OxiReading? = lastReading
    fun getReadingsSentCount(): Int = readingsSentCount
    fun getReadingsQueuedCount(): Int = readingsQueuedCount
    fun getLastCheckInTime(): Long = lastCheckInTime
    fun getLastPiStatus(): RelayStatus? = lastPiStatus
    fun getSettings(): SettingsManager = settingsManager
    fun getQueueStats(): QueueStats = readingQueue.getStats()
}
