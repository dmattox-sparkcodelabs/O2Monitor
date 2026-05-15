package com.o2monitor.relay

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Broadcast receiver that starts the RelayService after device boot.
 *
 * The service will only be started if:
 * 1. autoStartOnBoot is enabled in settings (default: true)
 * 2. The service was running before the device was rebooted (serviceEnabled)
 *
 * This ensures the relay continues working even after power cycles.
 */
class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) {
            return
        }

        Log.i(TAG, "Boot completed - checking if service should start")

        val settings = SettingsManager(context)

        // Check if auto-start is enabled
        if (!settings.autoStartOnBoot) {
            Log.i(TAG, "Auto-start on boot is disabled")
            return
        }

        // Check if service was running before reboot
        if (!settings.serviceEnabled) {
            Log.i(TAG, "Service was not running before reboot")
            return
        }

        // Check if we have the required permissions
        if (!BlePermissions.hasRequiredPermissions(context)) {
            Log.w(TAG, "Missing BLE permissions - cannot auto-start service")
            return
        }

        // Start the service
        Log.i(TAG, "Starting RelayService after boot")
        val serviceIntent = Intent(context, RelayService::class.java).apply {
            action = RelayService.ACTION_START
        }

        try {
            ContextCompat.startForegroundService(context, serviceIntent)
            Log.i(TAG, "RelayService start requested")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start RelayService: ${e.message}")
        }
    }
}
