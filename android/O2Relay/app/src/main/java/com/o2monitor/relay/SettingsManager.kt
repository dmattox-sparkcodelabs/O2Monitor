package com.o2monitor.relay

import android.content.Context
import android.content.SharedPreferences
import java.util.UUID

/**
 * Manages app settings using SharedPreferences.
 *
 * Settings stored:
 * - serverUrl: Pi server base URL
 * - oximeterMac: Target oximeter Bluetooth MAC address
 * - checkInIntervalSeconds: How often to check Pi status in DORMANT state
 * - deviceId: Unique identifier for this Android device (auto-generated)
 * - autoStartOnBoot: Whether to start service on device boot
 * - serviceEnabled: Whether the service was running (for restart after reboot)
 */
class SettingsManager(context: Context) {

    companion object {
        private const val PREFS_NAME = "o2relay_settings"

        // Keys
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_OXIMETER_MAC = "oximeter_mac"
        private const val KEY_CHECK_IN_INTERVAL = "check_in_interval_seconds"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_AUTO_START_ON_BOOT = "auto_start_on_boot"
        private const val KEY_SERVICE_ENABLED = "service_enabled"
        private const val KEY_TEST_MODE = "test_mode"
        private const val KEY_AUTH_TOKEN = "auth_token"
        private const val KEY_AUTH_TOKEN_EXPIRES = "auth_token_expires"
        private const val KEY_AUTH_USERNAME = "auth_username"

        // Defaults
        const val DEFAULT_SERVER_URL = "http://10.6.0.7:5000"  // Pi via WireGuard VPN
        const val TEST_SERVER_URL = "http://10.0.2.2:5000"     // Host localhost from Android emulator
        const val DEFAULT_OXIMETER_MAC = "C8:F1:6B:56:7B:F1"
        const val DEFAULT_CHECK_IN_INTERVAL_SECONDS = 60
        const val DEFAULT_AUTO_START_ON_BOOT = true
    }

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    /**
     * Test mode - when enabled, uses TEST_SERVER_URL (emulator localhost).
     * Useful for development and testing without a real Pi.
     */
    var testMode: Boolean
        get() = prefs.getBoolean(KEY_TEST_MODE, false)
        set(value) = prefs.edit().putBoolean(KEY_TEST_MODE, value).apply()

    /**
     * Pi server base URL.
     * Returns TEST_SERVER_URL if testMode is enabled.
     * Example: "http://10.6.0.7:5000"
     */
    var serverUrl: String
        get() = if (testMode) TEST_SERVER_URL else prefs.getString(KEY_SERVER_URL, DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL
        set(value) = prefs.edit().putString(KEY_SERVER_URL, value.trimEnd('/')).apply()

    /**
     * Get the effective server URL (respects test mode).
     */
    fun getEffectiveServerUrl(): String = if (testMode) TEST_SERVER_URL else serverUrl

    /**
     * Target oximeter Bluetooth MAC address.
     * Example: "C8:F1:6B:56:7B:F1"
     */
    var oximeterMac: String
        get() = prefs.getString(KEY_OXIMETER_MAC, DEFAULT_OXIMETER_MAC) ?: DEFAULT_OXIMETER_MAC
        set(value) = prefs.edit().putString(KEY_OXIMETER_MAC, value.uppercase()).apply()

    /**
     * Check-in interval in seconds (DORMANT state).
     * How often to poll Pi for relay status.
     */
    var checkInIntervalSeconds: Int
        get() = prefs.getInt(KEY_CHECK_IN_INTERVAL, DEFAULT_CHECK_IN_INTERVAL_SECONDS)
        set(value) = prefs.edit().putInt(KEY_CHECK_IN_INTERVAL, value.coerceIn(10, 300)).apply()

    /**
     * Unique device identifier for this Android device.
     * Auto-generated on first access, persisted thereafter.
     */
    val deviceId: String
        get() {
            var id = prefs.getString(KEY_DEVICE_ID, null)
            if (id == null) {
                id = "android_${UUID.randomUUID().toString().take(8)}"
                prefs.edit().putString(KEY_DEVICE_ID, id).apply()
            }
            return id
        }

    /**
     * Whether to automatically start the relay service on device boot.
     */
    var autoStartOnBoot: Boolean
        get() = prefs.getBoolean(KEY_AUTO_START_ON_BOOT, DEFAULT_AUTO_START_ON_BOOT)
        set(value) = prefs.edit().putBoolean(KEY_AUTO_START_ON_BOOT, value).apply()

    /**
     * Whether the service was enabled (running) before the app was closed.
     * Used to restore state after reboot or app restart.
     */
    var serviceEnabled: Boolean
        get() = prefs.getBoolean(KEY_SERVICE_ENABLED, false)
        set(value) = prefs.edit().putBoolean(KEY_SERVICE_ENABLED, value).apply()

    // ==================== Authentication ====================

    /**
     * API authentication token (valid for 30 days).
     */
    var authToken: String?
        get() = prefs.getString(KEY_AUTH_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_AUTH_TOKEN, value).apply()

    /**
     * Token expiration timestamp (ISO format).
     */
    var authTokenExpires: String?
        get() = prefs.getString(KEY_AUTH_TOKEN_EXPIRES, null)
        set(value) = prefs.edit().putString(KEY_AUTH_TOKEN_EXPIRES, value).apply()

    /**
     * Authenticated username.
     */
    var authUsername: String?
        get() = prefs.getString(KEY_AUTH_USERNAME, null)
        set(value) = prefs.edit().putString(KEY_AUTH_USERNAME, value).apply()

    /**
     * Check if we have a valid auth token.
     */
    fun hasValidToken(): Boolean {
        val token = authToken ?: return false
        if (token.isEmpty()) return false

        // Check expiration if set
        val expires = authTokenExpires
        if (expires != null) {
            try {
                val expiresInstant = java.time.Instant.parse(expires)
                if (java.time.Instant.now().isAfter(expiresInstant)) {
                    return false // Token expired
                }
            } catch (e: Exception) {
                // Can't parse expiration, assume valid
            }
        }
        return true
    }

    /**
     * Clear authentication data (logout).
     */
    fun clearAuth() {
        prefs.edit()
            .remove(KEY_AUTH_TOKEN)
            .remove(KEY_AUTH_TOKEN_EXPIRES)
            .remove(KEY_AUTH_USERNAME)
            .apply()
    }

    /**
     * Save authentication data after successful login.
     */
    fun saveAuth(token: String, expiresAt: String, username: String) {
        prefs.edit()
            .putString(KEY_AUTH_TOKEN, token)
            .putString(KEY_AUTH_TOKEN_EXPIRES, expiresAt)
            .putString(KEY_AUTH_USERNAME, username)
            .apply()
    }

    /**
     * Check if the server URL has been configured (changed from default).
     */
    fun isServerConfigured(): Boolean {
        return prefs.contains(KEY_SERVER_URL)
    }

    /**
     * Check if the oximeter MAC has been configured (changed from default).
     */
    fun isOximeterConfigured(): Boolean {
        return prefs.contains(KEY_OXIMETER_MAC)
    }

    /**
     * Validate server URL format.
     * Returns true if URL appears valid.
     */
    fun isValidServerUrl(url: String): Boolean {
        return url.startsWith("http://") || url.startsWith("https://")
    }

    /**
     * Validate MAC address format.
     * Returns true if MAC appears valid (XX:XX:XX:XX:XX:XX).
     */
    fun isValidMacAddress(mac: String): Boolean {
        val macRegex = Regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
        return macRegex.matches(mac)
    }

    /**
     * Reset all settings to defaults.
     */
    fun resetToDefaults() {
        prefs.edit()
            .remove(KEY_SERVER_URL)
            .remove(KEY_OXIMETER_MAC)
            .remove(KEY_CHECK_IN_INTERVAL)
            .remove(KEY_AUTO_START_ON_BOOT)
            .remove(KEY_SERVICE_ENABLED)
            // Note: deviceId is intentionally NOT reset
            .apply()
    }
}
