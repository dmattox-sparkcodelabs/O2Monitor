package com.o2monitor.relay

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.Bundle
import android.os.IBinder
import android.util.Log
import android.view.View
import android.widget.EditText
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.lifecycleScope
import com.o2monitor.relay.databinding.ActivityMainBinding
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity(), RelayService.StateListener {
    companion object {
        private const val TAG = "MainActivity"
        private const val UI_REFRESH_INTERVAL_MS = 1000L
    }

    private lateinit var binding: ActivityMainBinding
    private lateinit var settingsManager: SettingsManager

    // Service binding
    private var relayService: RelayService? = null
    private var bound = false

    // UI refresh timer
    private val handler = android.os.Handler(android.os.Looper.getMainLooper())
    private var uiRefreshRunnable: Runnable? = null

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, service: IBinder?) {
            val binder = service as RelayService.RelayBinder
            relayService = binder.getService()
            relayService?.stateListener = this@MainActivity
            bound = true

            // Update UI with current state
            updateUiForState(relayService?.state ?: RelayService.State.STOPPED)
            relayService?.getLastReading()?.let { updateReadingDisplay(it) }
            updateStats()
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            relayService?.stateListener = null
            relayService = null
            bound = false
        }
    }

    // Permission request launcher
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.values.all { it }
        if (allGranted) {
            startRelayService()
        } else {
            showError("Bluetooth permissions are required")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        ViewCompat.setOnApplyWindowInsetsListener(binding.root) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        // Initialize settings
        settingsManager = SettingsManager(this)

        setupUi()
    }

    override fun onStart() {
        super.onStart()
        // Bind to service if it's running
        bindToService()
    }

    override fun onResume() {
        super.onResume()
        startUiRefreshTimer()
    }

    override fun onPause() {
        super.onPause()
        stopUiRefreshTimer()
    }

    override fun onStop() {
        super.onStop()
        // Unbind from service
        if (bound) {
            relayService?.stateListener = null
            unbindService(serviceConnection)
            bound = false
        }
    }

    private fun startUiRefreshTimer() {
        stopUiRefreshTimer()
        uiRefreshRunnable = object : Runnable {
            override fun run() {
                updateStats()
                handler.postDelayed(this, UI_REFRESH_INTERVAL_MS)
            }
        }
        handler.postDelayed(uiRefreshRunnable!!, UI_REFRESH_INTERVAL_MS)
    }

    private fun stopUiRefreshTimer() {
        uiRefreshRunnable?.let { handler.removeCallbacks(it) }
        uiRefreshRunnable = null
    }

    private fun setupUi() {
        // Set initial status
        updateUiForState(RelayService.State.STOPPED)

        // Set version info
        binding.versionText.text = getString(R.string.version_format, BuildConfig.VERSION_NAME)

        // Display settings
        updateSettingsDisplay()

        // Setup settings buttons
        setupButtons()

        // Auto-start service if logged in
        if (settingsManager.hasValidToken()) {
            Log.d(TAG, "User is logged in, auto-starting service")
            checkPermissionsAndStart()
        } else {
            Log.d(TAG, "User not logged in, showing login prompt")
            // Show login dialog after a short delay to let UI settle
            binding.root.postDelayed({ showLoginDialog() }, 500)
        }
    }

    private fun updateSettingsDisplay() {
        // Server URL
        val serverUrl = settingsManager.getEffectiveServerUrl()
        binding.serverUrlText.text = "Server: $serverUrl"

        // Update buttons
        updateTestModeButton()
        updateLoginButton()
    }

    private fun setupButtons() {
        // Test mode button
        binding.testModeButton.setOnClickListener {
            toggleTestMode()
        }

        // Login button
        binding.loginButton.setOnClickListener {
            if (settingsManager.hasValidToken()) {
                showLogoutConfirmation()
            } else {
                showLoginDialog()
            }
        }
    }

    private fun updateTestModeButton() {
        val isTestMode = settingsManager.testMode
        binding.testModeButton.text = if (isTestMode) "Test Mode: ON" else "Test Mode: OFF"
    }

    private fun updateLoginButton() {
        if (settingsManager.hasValidToken()) {
            val username = settingsManager.authUsername ?: "User"
            binding.loginButton.text = "Logout ($username)"
        } else {
            binding.loginButton.text = "Login"
        }
    }

    private fun showLogoutConfirmation() {
        AlertDialog.Builder(this)
            .setTitle("Logout")
            .setMessage("Are you sure you want to logout?")
            .setPositiveButton("Logout") { _, _ ->
                settingsManager.clearAuth()
                updateLoginButton()
                android.widget.Toast.makeText(this, "Logged out", android.widget.Toast.LENGTH_SHORT).show()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun toggleTestMode() {
        val newTestMode = !settingsManager.testMode
        settingsManager.testMode = newTestMode

        val message = if (newTestMode) {
            "Test mode ON - using ${SettingsManager.TEST_SERVER_URL}"
        } else {
            "Test mode OFF - using production server"
        }
        android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_SHORT).show()

        // Update display
        updateSettingsDisplay()

        // Note: Service must be restarted for new URL to take effect
        if (relayService?.state != RelayService.State.STOPPED) {
            android.widget.Toast.makeText(this, "Restart service to apply", android.widget.Toast.LENGTH_SHORT).show()
        }
    }

    private fun bindToService() {
        val intent = Intent(this, RelayService::class.java)
        bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE)
    }

    private fun checkPermissionsAndStart() {
        Log.d(TAG, "checkPermissionsAndStart called, hasValidToken: ${settingsManager.hasValidToken()}")

        // First check if we have a valid auth token
        if (!settingsManager.hasValidToken()) {
            Log.d(TAG, "No valid token, showing login dialog")
            showLoginDialog()
            return
        }

        Log.d(TAG, "Has valid token, checking permissions")
        if (BlePermissions.hasRequiredPermissions(this)) {
            Log.d(TAG, "Has permissions, starting service")
            startRelayService()
        } else {
            Log.d(TAG, "Missing permissions, requesting")
            val permissions = BlePermissions.getRequiredPermissions()
            permissionLauncher.launch(permissions)
        }
    }

    private fun showLoginDialog() {
        Log.d(TAG, "showLoginDialog called")
        val dialogView = layoutInflater.inflate(R.layout.dialog_login, null)
        val usernameInput = dialogView.findViewById<EditText>(R.id.usernameInput)
        val passwordInput = dialogView.findViewById<EditText>(R.id.passwordInput)

        AlertDialog.Builder(this)
            .setTitle("Login Required")
            .setMessage("Enter your Pi server credentials")
            .setView(dialogView)
            .setPositiveButton("Login") { _, _ ->
                val username = usernameInput.text.toString().trim()
                val password = passwordInput.text.toString()
                Log.d(TAG, "Login button clicked, username: $username")

                if (username.isNotEmpty() && password.isNotEmpty()) {
                    performLogin(username, password)
                } else {
                    showError("Username and password are required")
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
        Log.d(TAG, "Login dialog shown")
    }

    private fun performLogin(username: String, password: String) {
        val serverUrl = settingsManager.getEffectiveServerUrl()
        Log.d(TAG, "performLogin called, connecting to: $serverUrl")

        // Create a temporary ApiClient for login
        val apiClient = ApiClient(
            baseUrl = serverUrl,
            deviceId = settingsManager.deviceId
        )

        lifecycleScope.launch {
            val response = apiClient.login(username, password)
            Log.d(TAG, "Login response: success=${response?.success}, error=${response?.error}")

            if (response != null && response.success && response.token != null) {
                // Save auth data
                settingsManager.saveAuth(
                    token = response.token,
                    expiresAt = response.expiresAt ?: "",
                    username = username
                )
                android.widget.Toast.makeText(this@MainActivity, "Login successful", android.widget.Toast.LENGTH_SHORT).show()
                updateSettingsDisplay()

                // Now start the service
                checkPermissionsAndStart()
            } else {
                val error = response?.error ?: "Login failed - check server URL"
                Log.e(TAG, "Login failed: $error")
                showError(error)
            }
        }
    }

    private fun startRelayService() {
        val intent = Intent(this, RelayService::class.java).apply {
            action = RelayService.ACTION_START
        }
        ContextCompat.startForegroundService(this, intent)

        // Bind to service
        if (!bound) {
            bindToService()
        }
    }

    private fun stopRelayService() {
        relayService?.stop()
    }

    // ==================== StateListener Implementation ====================

    override fun onStateChanged(state: RelayService.State) {
        runOnUiThread {
            updateUiForState(state)
            updateStats()
        }
    }

    override fun onReadingReceived(reading: OxiReading) {
        runOnUiThread {
            updateReadingDisplay(reading)
            updateStats()
        }
    }

    override fun onStatusUpdate(status: String) {
        runOnUiThread {
            updatePiStatus(status)
            updateStats()
        }
    }

    override fun onError(message: String) {
        runOnUiThread {
            showError(message)
        }
    }

    // ==================== UI Updates ====================

    private fun updateUiForState(state: RelayService.State) {
        // Source indicators are updated via updateSourcesFromPiStatus in updateStats
        // Just clear error when state changes
        hideError()
    }

    // Map of source name to its views (indicator and status)
    private data class SourceViews(val indicator: View, val statusText: android.widget.TextView)
    private val sourceViewsMap = mutableMapOf<String, SourceViews>()
    private var lastSourceNames: List<String>? = null

    private fun updateSourcesFromPiStatus(sources: List<SourceStatus>?) {
        // Only show sources if API returned them
        if (sources.isNullOrEmpty()) {
            return
        }

        // Check if we need to rebuild the views (source list changed)
        val sourceNames = sources.map { it.name }
        if (sourceNames != lastSourceNames) {
            rebuildSourceViews(sources)
            lastSourceNames = sourceNames
        }

        // Update each source's indicator
        sources.forEach { source ->
            val views = sourceViewsMap[source.name]
            if (views != null) {
                val indicatorRes = if (source.active) R.drawable.indicator_online else R.drawable.indicator_offline
                val statusText = if (source.active) "Active" else "--"
                views.indicator.setBackgroundResource(indicatorRes)
                views.statusText.text = statusText
            }
        }
    }

    private fun rebuildSourceViews(sources: List<SourceStatus>) {
        val container = binding.sourcesContainer
        container.removeAllViews()
        sourceViewsMap.clear()

        sources.forEach { source ->
            // Create container for this source
            val sourceLayout = android.widget.LinearLayout(this).apply {
                orientation = android.widget.LinearLayout.VERTICAL
                gravity = android.view.Gravity.CENTER
                layoutParams = android.widget.LinearLayout.LayoutParams(
                    0,
                    android.widget.LinearLayout.LayoutParams.WRAP_CONTENT,
                    1f
                )
                setPadding(dpToPx(8), dpToPx(8), dpToPx(8), dpToPx(8))
            }

            // Indicator dot
            val indicator = View(this).apply {
                layoutParams = android.widget.LinearLayout.LayoutParams(dpToPx(12), dpToPx(12))
                setBackgroundResource(R.drawable.indicator_offline)
            }
            sourceLayout.addView(indicator)

            // Source name label
            val nameLabel = android.widget.TextView(this).apply {
                text = if (source.name == "Mobile") "Phone" else source.name
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_secondary))
                textSize = 12f
                gravity = android.view.Gravity.CENTER
                layoutParams = android.widget.LinearLayout.LayoutParams(
                    android.widget.LinearLayout.LayoutParams.WRAP_CONTENT,
                    android.widget.LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    topMargin = dpToPx(4)
                }
            }
            sourceLayout.addView(nameLabel)

            // Status text
            val statusText = android.widget.TextView(this).apply {
                text = "--"
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_primary))
                textSize = 11f
                gravity = android.view.Gravity.CENTER
            }
            sourceLayout.addView(statusText)

            container.addView(sourceLayout)
            sourceViewsMap[source.name] = SourceViews(indicator, statusText)
        }
    }

    private fun dpToPx(dp: Int): Int {
        return (dp * resources.displayMetrics.density).toInt()
    }

    private fun updateReadingDisplay(reading: OxiReading) {
        // SpO2
        binding.spo2Value.text = reading.spo2.toString()
        val spo2Color = if (reading.spo2 >= 90) R.color.spo2_normal else R.color.spo2_low
        binding.spo2Value.setTextColor(ContextCompat.getColor(this, spo2Color))

        // Heart rate
        binding.heartRateValue.text = reading.heartRate.toString()
        binding.heartRateValue.setTextColor(ContextCompat.getColor(this, R.color.hr_normal))

        // Battery
        binding.batteryValue.text = reading.battery.toString()
        val batteryColor = when {
            reading.battery <= 20 -> R.color.danger
            reading.battery <= 40 -> R.color.warning
            else -> R.color.success
        }
        binding.batteryValue.setTextColor(ContextCompat.getColor(this, batteryColor))
        binding.batteryUnit.setTextColor(ContextCompat.getColor(this, batteryColor))
    }

    private fun updateStats() {
        val sent = relayService?.getReadingsSentCount() ?: 0
        val queued = relayService?.getReadingsQueuedCount() ?: 0

        if (sent > 0 || queued > 0) {
            binding.statsValue.text = "$sent sent, $queued queued"
            binding.statsRow.visibility = View.VISIBLE
        } else {
            binding.statsRow.visibility = View.GONE
        }

        // Update last check-in time
        val lastCheckIn = relayService?.getLastCheckInTime() ?: 0
        if (lastCheckIn > 0) {
            val ago = formatTimeAgo(System.currentTimeMillis() - lastCheckIn)
            binding.lastCheckInValue.text = ago
        } else {
            binding.lastCheckInValue.text = "Never"
        }

        // Update last reading time (for phone readings)
        val lastReading = relayService?.getLastReading()
        if (lastReading != null) {
            val readingAge = System.currentTimeMillis() - lastReading.timestamp.toEpochMilli()
            binding.lastReadingValue.text = formatTimeAgo(readingAge)
        } else {
            binding.lastReadingValue.text = "--"
        }

        // Update AVAPS status from Pi
        val piStatus = relayService?.getLastPiStatus()
        if (piStatus != null) {
            // AVAPS card
            binding.avapsValue.text = if (piStatus.therapyActive) "ON" else "OFF"
            binding.avapsValue.setTextColor(
                ContextCompat.getColor(this, if (piStatus.therapyActive) R.color.success else R.color.muted)
            )

            // Show power if available
            val power = piStatus.powerWatts
            if (piStatus.therapyActive && power != null && power > 0) {
                binding.avapsPower.text = "${power.toInt()}W"
                binding.avapsPower.visibility = View.VISIBLE
            } else {
                binding.avapsPower.visibility = View.GONE
            }

            // Battery from vitals
            val vitals = piStatus.currentVitals
            if (vitals != null && vitals.batteryLevel > 0) {
                binding.batteryValue.text = vitals.batteryLevel.toString()
                val batteryColor = when {
                    vitals.batteryLevel <= 20 -> R.color.danger
                    vitals.batteryLevel <= 40 -> R.color.warning
                    else -> R.color.success
                }
                binding.batteryValue.setTextColor(ContextCompat.getColor(this, batteryColor))
                binding.batteryUnit.setTextColor(ContextCompat.getColor(this, batteryColor))
            }

            // Update source indicators from Pi sources array
            updateSourcesFromPiStatus(piStatus.sources)
        } else {
            binding.avapsValue.text = "--"
            binding.avapsPower.visibility = View.GONE
        }
    }

    private fun updatePiStatus(status: String) {
        // Parse Pi status to update vitals display when in DORMANT state
        // Status format: "Pi: 97% SpO2, 72 HR (5s ago)" or "Pi reading: 10s ago"
        if (status.startsWith("Pi:")) {
            // Extract vitals from Pi status message
            val spo2Match = Regex("(\\d+)%\\s*SpO2").find(status)
            val hrMatch = Regex("(\\d+)\\s*HR").find(status)

            spo2Match?.groupValues?.getOrNull(1)?.toIntOrNull()?.let { spo2 ->
                binding.spo2Value.text = spo2.toString()
                val spo2Color = if (spo2 >= 90) R.color.spo2_normal else R.color.spo2_low
                binding.spo2Value.setTextColor(ContextCompat.getColor(this, spo2Color))
            }

            hrMatch?.groupValues?.getOrNull(1)?.toIntOrNull()?.let { hr ->
                binding.heartRateValue.text = hr.toString()
            }
        }
    }

    private fun showError(message: String) {
        binding.errorText.text = message
        binding.errorCard.visibility = View.VISIBLE
    }

    private fun hideError() {
        binding.errorCard.visibility = View.GONE
    }

    private fun formatTimeAgo(millis: Long): String {
        val seconds = millis / 1000
        return when {
            seconds < 60 -> "${seconds}s"
            seconds < 3600 -> "${seconds / 60}m"
            else -> "${seconds / 3600}h"
        }
    }
}
