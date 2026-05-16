package com.o2monitor.app.util

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.o2monitor.app.ble.BleService

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            val prefs = context.getSharedPreferences("o2monitor_prefs", Context.MODE_PRIVATE)
            val patientId = prefs.getString("patient_id", null)
            if (patientId != null) {
                val serviceIntent = Intent(context, BleService::class.java)
                context.startForegroundService(serviceIntent)
            }
        }
    }
}
