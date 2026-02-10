package com.o2monitor.relay

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.content.ContextCompat

class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context?, intent: Intent?) {
        if (context == null || intent?.action != Intent.ACTION_BOOT_COMPLETED) {
            return
        }

        val settings = SettingsManager(context)

        if (!settings.autoStartOnBoot || !settings.serviceEnabled) {
            Log.d(TAG, "Boot start skipped: autoStart=${settings.autoStartOnBoot}, enabled=${settings.serviceEnabled}")
            return
        }

        Log.i(TAG, "Boot completed - starting RelayService")
        val serviceIntent = Intent(context, RelayService::class.java).apply {
            action = RelayService.ACTION_START
        }
        ContextCompat.startForegroundService(context, serviceIntent)
    }
}
