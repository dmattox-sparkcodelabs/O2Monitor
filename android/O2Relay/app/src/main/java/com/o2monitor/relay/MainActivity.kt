package com.o2monitor.relay

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.util.Log
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.o2monitor.relay.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity(), RelayService.StateListener {

    companion object {
        private const val TAG = "MainActivity"
    }

    private lateinit var binding: ActivityMainBinding
    private lateinit var settings: SettingsManager

    private var relayService: RelayService? = null
    private var bound = false

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            val service = (binder as RelayService.RelayBinder).getService()
            relayService = service
            bound = true
            service.stateListener = this@MainActivity
            Log.d(TAG, "Bound to RelayService, state=${service.state}")
            updateUiForState(service.state)
            service.getLastReading()?.let { onReadingReceived(it) }
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            relayService?.stateListener = null
            relayService = null
            bound = false
            Log.d(TAG, "Unbound from RelayService")
        }
    }

    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            Log.d(TAG, "Notification permission granted")
        } else {
            Log.w(TAG, "Notification permission denied")
        }
    }

    // ==================== Lifecycle ====================

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        settings = SettingsManager(this)

        ViewCompat.setOnApplyWindowInsetsListener(binding.root) { v, insets ->
            val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom)
            insets
        }

        // Initial UI
        updateUiForState(RelayService.State.STOPPED)
        binding.serverUrlText.text = getString(R.string.server_format, settings.serverUrl)
        binding.deviceMacText.text = getString(R.string.device_mac_format, settings.oximeterMac)
        binding.versionText.text = getString(R.string.version_format, BuildConfig.VERSION_NAME)

        // Toggle button
        binding.toggleServiceButton.setOnClickListener {
            if (relayService?.state != null && relayService?.state != RelayService.State.STOPPED) {
                stopRelay()
            } else {
                startRelay()
            }
        }
    }

    override fun onStart() {
        super.onStart()
        // Bind to service if it's running (don't auto-create)
        val intent = Intent(this, RelayService::class.java)
        bindService(intent, connection, 0)
    }

    override fun onStop() {
        super.onStop()
        if (bound) {
            relayService?.stateListener = null
            unbindService(connection)
            bound = false
        }
    }

    // ==================== Service Control ====================

    private fun startRelay() {
        // Check permissions first
        if (!checkAndRequestPermissions()) {
            return
        }

        val intent = Intent(this, RelayService::class.java).apply {
            action = RelayService.ACTION_START
        }
        ContextCompat.startForegroundService(this, intent)

        // Bind to get state updates
        bindService(Intent(this, RelayService::class.java), connection, 0)
    }

    private fun stopRelay() {
        val intent = Intent(this, RelayService::class.java).apply {
            action = RelayService.ACTION_STOP
        }
        ContextCompat.startForegroundService(this, intent)
    }

    // ==================== Permissions ====================

    private fun checkAndRequestPermissions(): Boolean {
        // Request notification permission on Android 13+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }

        // Check BLE permissions
        if (!BlePermissions.hasRequiredPermissions(this)) {
            BlePermissions.requestPermissions(this)
            return false
        }

        return true
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)

        if (BlePermissions.onRequestPermissionsResult(requestCode, permissions, grantResults)) {
            // BLE permissions granted, start the service
            startRelay()
        } else if (requestCode == BlePermissions.REQUEST_CODE_BLE_PERMISSIONS) {
            onError(BlePermissions.getMissingPermissionsDescription(this))
        }
    }

    // ==================== StateListener ====================

    override fun onStateChanged(state: RelayService.State) {
        runOnUiThread { updateUiForState(state) }
    }

    override fun onReadingReceived(reading: OxiReading) {
        runOnUiThread {
            binding.statusDescription.text =
                "SpO2: ${reading.spo2}%  HR: ${reading.heartRate} bpm  Bat: ${reading.battery}%"
        }
    }

    override fun onStatusUpdate(status: String) {
        runOnUiThread {
            binding.lastCheckInText.text = status
        }
    }

    override fun onError(message: String) {
        runOnUiThread {
            binding.statusDescription.text = message
        }
    }

    // ==================== UI Updates ====================

    private fun updateUiForState(state: RelayService.State) {
        val (statusRes, descRes, colorRes) = when (state) {
            RelayService.State.STOPPED -> Triple(
                R.string.status_stopped, R.string.status_stopped_desc, R.color.status_dormant
            )
            RelayService.State.DORMANT -> Triple(
                R.string.status_dormant, R.string.status_dormant_desc, R.color.status_dormant
            )
            RelayService.State.SCANNING -> Triple(
                R.string.status_scanning, R.string.status_scanning_desc, R.color.status_scanning
            )
            RelayService.State.CONNECTED -> Triple(
                R.string.status_connected, R.string.status_connected_desc, R.color.status_connected
            )
            RelayService.State.QUEUING -> Triple(
                R.string.status_queuing, R.string.status_queuing_desc, R.color.status_queuing
            )
        }

        binding.statusText.text = getString(statusRes)
        binding.statusText.setTextColor(ContextCompat.getColor(this, colorRes))
        binding.statusDescription.text = getString(descRes)

        // Button text
        binding.toggleServiceButton.text = if (state == RelayService.State.STOPPED) {
            getString(R.string.start_service)
        } else {
            getString(R.string.stop_service)
        }

        // Update check-in display
        val service = relayService
        if (service != null && state != RelayService.State.STOPPED) {
            val lastCheckIn = service.getLastCheckInTime()
            if (lastCheckIn > 0) {
                val elapsedSec = (System.currentTimeMillis() - lastCheckIn) / 1000
                val agoText = when {
                    elapsedSec < 60 -> "${elapsedSec}s"
                    else -> "${elapsedSec / 60}m"
                }
                binding.lastCheckInText.text =
                    getString(R.string.last_check_in_format, agoText)
            }

            val piStatus = service.getLastPiStatus()
            if (piStatus != null) {
                binding.piStatusText.text =
                    getString(R.string.pi_status_format, "${piStatus.lastReadingAgeSeconds}s")
            }
        } else {
            binding.lastCheckInText.text = getString(R.string.last_check_in_never)
            binding.piStatusText.text = getString(R.string.pi_status_unknown)
        }
    }
}
