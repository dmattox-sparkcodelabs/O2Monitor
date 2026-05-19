package com.o2monitor.app.ble

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class SyncAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == ACTION_SYNC_ALARM) {
            val serviceIntent = Intent(context, BleService::class.java).apply {
                action = BleService.ACTION_SYNC_NOW
            }
            context.startForegroundService(serviceIntent)
        }
    }

    companion object {
        const val ACTION_SYNC_ALARM = "com.o2monitor.SYNC_ALARM"
    }
}
