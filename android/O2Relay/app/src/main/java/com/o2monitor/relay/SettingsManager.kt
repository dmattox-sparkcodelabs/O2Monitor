package com.o2monitor.relay

import android.content.Context
import android.content.SharedPreferences
import java.util.UUID

class SettingsManager(context: Context) {

    companion object {
        private const val PREFS_NAME = "o2relay_settings"

        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_OXIMETER_MAC = "oximeter_mac"
        private const val KEY_CHECK_IN_INTERVAL = "check_in_interval_seconds"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_AUTO_START_ON_BOOT = "auto_start_on_boot"
        private const val KEY_SERVICE_ENABLED = "service_enabled"

        private const val DEFAULT_SERVER_URL = "http://192.168.4.100:5000"
        private const val DEFAULT_OXIMETER_MAC = "D4:30:77:4B:0F:C7"
        private const val DEFAULT_CHECK_IN_INTERVAL = 60
    }

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString(KEY_SERVER_URL, DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL
        set(value) = prefs.edit().putString(KEY_SERVER_URL, value).apply()

    var oximeterMac: String
        get() = prefs.getString(KEY_OXIMETER_MAC, DEFAULT_OXIMETER_MAC) ?: DEFAULT_OXIMETER_MAC
        set(value) = prefs.edit().putString(KEY_OXIMETER_MAC, value).apply()

    var checkInIntervalSeconds: Int
        get() = prefs.getInt(KEY_CHECK_IN_INTERVAL, DEFAULT_CHECK_IN_INTERVAL)
        set(value) = prefs.edit().putInt(KEY_CHECK_IN_INTERVAL, value).apply()

    var deviceId: String
        get() {
            val existing = prefs.getString(KEY_DEVICE_ID, null)
            if (existing != null) return existing
            val generated = UUID.randomUUID().toString()
            prefs.edit().putString(KEY_DEVICE_ID, generated).apply()
            return generated
        }
        set(value) = prefs.edit().putString(KEY_DEVICE_ID, value).apply()

    var autoStartOnBoot: Boolean
        get() = prefs.getBoolean(KEY_AUTO_START_ON_BOOT, true)
        set(value) = prefs.edit().putBoolean(KEY_AUTO_START_ON_BOOT, value).apply()

    var serviceEnabled: Boolean
        get() = prefs.getBoolean(KEY_SERVICE_ENABLED, false)
        set(value) = prefs.edit().putBoolean(KEY_SERVICE_ENABLED, value).apply()
}
