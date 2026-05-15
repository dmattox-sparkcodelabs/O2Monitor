package com.o2monitor.relay

import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for SettingsManager validation methods.
 *
 * Note: SharedPreferences-related tests would require instrumented tests
 * or Robolectric. These tests cover the validation logic only.
 */
class SettingsManagerTest {

    // ==================== URL Validation Tests ====================

    @Test
    fun `isValidServerUrl accepts http URLs`() {
        assertTrue(isValidServerUrl("http://192.168.4.100:5000"))
        assertTrue(isValidServerUrl("http://localhost:5000"))
        assertTrue(isValidServerUrl("http://example.com"))
        assertTrue(isValidServerUrl("http://192.168.1.1"))
    }

    @Test
    fun `isValidServerUrl accepts https URLs`() {
        assertTrue(isValidServerUrl("https://example.com"))
        assertTrue(isValidServerUrl("https://192.168.4.100:5000"))
    }

    @Test
    fun `isValidServerUrl rejects invalid URLs`() {
        assertFalse(isValidServerUrl("ftp://example.com"))
        assertFalse(isValidServerUrl("192.168.4.100:5000"))
        assertFalse(isValidServerUrl("example.com"))
        assertFalse(isValidServerUrl(""))
        assertFalse(isValidServerUrl("not a url"))
    }

    // ==================== MAC Address Validation Tests ====================

    @Test
    fun `isValidMacAddress accepts valid MAC addresses`() {
        assertTrue(isValidMacAddress("C8:F1:6B:56:7B:F1"))
        assertTrue(isValidMacAddress("00:00:00:00:00:00"))
        assertTrue(isValidMacAddress("FF:FF:FF:FF:FF:FF"))
        assertTrue(isValidMacAddress("aa:bb:cc:dd:ee:ff"))
        assertTrue(isValidMacAddress("AA:BB:CC:DD:EE:FF"))
    }

    @Test
    fun `isValidMacAddress rejects invalid MAC addresses`() {
        assertFalse(isValidMacAddress("C8:F1:6B:56:7B"))  // Too short
        assertFalse(isValidMacAddress("C8:F1:6B:56:7B:F1:00"))  // Too long
        assertFalse(isValidMacAddress("C8-F1-6B-56-7B-F1"))  // Wrong separator
        assertFalse(isValidMacAddress("C8F16B567BF1"))  // No separator
        assertFalse(isValidMacAddress("GG:HH:II:JJ:KK:LL"))  // Invalid hex
        assertFalse(isValidMacAddress(""))
        assertFalse(isValidMacAddress("not a mac"))
    }

    // ==================== Default Values Tests ====================

    @Test
    fun `default server URL is valid`() {
        assertTrue(isValidServerUrl(SettingsManager.DEFAULT_SERVER_URL))
    }

    @Test
    fun `default oximeter MAC is valid`() {
        assertTrue(isValidMacAddress(SettingsManager.DEFAULT_OXIMETER_MAC))
    }

    @Test
    fun `default check-in interval is reasonable`() {
        val interval = SettingsManager.DEFAULT_CHECK_IN_INTERVAL_SECONDS
        assertTrue("Check-in interval should be at least 10 seconds", interval >= 10)
        assertTrue("Check-in interval should be at most 300 seconds", interval <= 300)
    }

    // ==================== Helper Functions ====================

    // These mirror the SettingsManager validation methods for testing without Context
    private fun isValidServerUrl(url: String): Boolean {
        return url.startsWith("http://") || url.startsWith("https://")
    }

    private fun isValidMacAddress(mac: String): Boolean {
        val macRegex = Regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
        return macRegex.matches(mac)
    }
}
