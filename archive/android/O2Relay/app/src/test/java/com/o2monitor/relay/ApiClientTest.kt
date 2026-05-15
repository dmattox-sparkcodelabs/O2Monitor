package com.o2monitor.relay

import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import java.time.Instant

/**
 * Unit tests for ApiClient using MockWebServer.
 */
class ApiClientTest {

    private lateinit var mockServer: MockWebServer
    private lateinit var apiClient: ApiClient

    @Before
    fun setUp() {
        mockServer = MockWebServer()
        mockServer.start()
        apiClient = ApiClient(
            baseUrl = mockServer.url("/").toString().removeSuffix("/"),
            deviceId = "test_device"
        )
    }

    @After
    fun tearDown() {
        mockServer.shutdown()
    }

    // ==================== getRelayStatus Tests ====================

    @Test
    fun `getRelayStatus returns status when Pi needs relay`() = runTest {
        val responseJson = """
            {
                "timestamp": "2024-01-15T10:30:00",
                "last_reading_age_seconds": 45,
                "source": "ble_direct",
                "needs_relay": true,
                "pi_ble_connected": false
            }
        """.trimIndent()

        mockServer.enqueue(MockResponse()
            .setResponseCode(200)
            .setBody(responseJson)
            .addHeader("Content-Type", "application/json"))

        val status = apiClient.getRelayStatus()

        assertNotNull(status)
        assertEquals("2024-01-15T10:30:00", status!!.timestamp)
        assertEquals(45, status.lastReadingAgeSeconds)
        assertEquals("ble_direct", status.source)
        assertTrue(status.needsRelay)
        assertFalse(status.piBleConnected)

        val request = mockServer.takeRequest()
        assertEquals("GET", request.method)
        assertEquals("/api/relay/status", request.path)
    }

    @Test
    fun `getRelayStatus returns status when Pi does not need relay`() = runTest {
        val responseJson = """
            {
                "timestamp": "2024-01-15T10:30:00",
                "last_reading_age_seconds": 5,
                "source": "ble_direct",
                "needs_relay": false,
                "pi_ble_connected": true
            }
        """.trimIndent()

        mockServer.enqueue(MockResponse()
            .setResponseCode(200)
            .setBody(responseJson))

        val status = apiClient.getRelayStatus()

        assertNotNull(status)
        assertEquals(5, status!!.lastReadingAgeSeconds)
        assertFalse(status.needsRelay)
        assertTrue(status.piBleConnected)
    }

    @Test
    fun `getRelayStatus returns null on server error`() = runTest {
        mockServer.enqueue(MockResponse().setResponseCode(500))

        val status = apiClient.getRelayStatus()

        assertNull(status)
    }

    @Test
    fun `getRelayStatus returns null on network error`() = runTest {
        mockServer.shutdown() // Simulate network failure

        val status = apiClient.getRelayStatus()

        assertNull(status)
    }

    // ==================== postReading Tests ====================

    @Test
    fun `postReading returns true on success`() = runTest {
        val responseJson = """
            {
                "status": "ok",
                "message": "Reading received"
            }
        """.trimIndent()

        mockServer.enqueue(MockResponse()
            .setResponseCode(200)
            .setBody(responseJson))

        val reading = OxiReading(
            spo2 = 97,
            heartRate = 72,
            battery = 85,
            timestamp = Instant.parse("2024-01-15T10:30:00Z")
        )

        val success = apiClient.postReading(reading)

        assertTrue(success)

        val request = mockServer.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/relay/reading", request.path)

        val body = request.body.readUtf8()
        assertTrue(body.contains("\"spo2\":97"))
        assertTrue(body.contains("\"heart_rate\":72"))
        assertTrue(body.contains("\"battery\":85"))
        assertTrue(body.contains("\"device_id\":\"test_device\""))
        assertTrue(body.contains("\"queued\":false"))
    }

    @Test
    fun `postReading sends queued flag when specified`() = runTest {
        mockServer.enqueue(MockResponse()
            .setResponseCode(200)
            .setBody("""{"status": "ok"}"""))

        val reading = OxiReading(spo2 = 97, heartRate = 72, battery = 85)
        apiClient.postReading(reading, queued = true)

        val request = mockServer.takeRequest()
        val body = request.body.readUtf8()
        assertTrue(body.contains("\"queued\":true"))
    }

    @Test
    fun `postReading returns false on server error`() = runTest {
        mockServer.enqueue(MockResponse().setResponseCode(500))

        val reading = OxiReading(spo2 = 97, heartRate = 72, battery = 85)
        val success = apiClient.postReading(reading)

        assertFalse(success)
    }

    @Test
    fun `postReading returns false on error status`() = runTest {
        mockServer.enqueue(MockResponse()
            .setResponseCode(200)
            .setBody("""{"status": "error", "message": "Invalid data"}"""))

        val reading = OxiReading(spo2 = 97, heartRate = 72, battery = 85)
        val success = apiClient.postReading(reading)

        assertFalse(success)
    }

    // ==================== postBatch Tests ====================

    @Test
    fun `postBatch returns response on success`() = runTest {
        val responseJson = """
            {
                "status": "ok",
                "accepted": 3,
                "rejected": 0
            }
        """.trimIndent()

        mockServer.enqueue(MockResponse()
            .setResponseCode(200)
            .setBody(responseJson))

        val readings = listOf(
            OxiReading(spo2 = 97, heartRate = 72, battery = 85),
            OxiReading(spo2 = 96, heartRate = 74, battery = 84),
            OxiReading(spo2 = 98, heartRate = 70, battery = 83)
        )

        val response = apiClient.postBatch(readings)

        assertNotNull(response)
        assertEquals("ok", response!!.status)
        assertEquals(3, response.accepted)
        assertEquals(0, response.rejected)

        val request = mockServer.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/relay/batch", request.path)
    }

    @Test
    fun `postBatch returns empty response for empty list`() = runTest {
        val response = apiClient.postBatch(emptyList())

        assertNotNull(response)
        assertEquals("ok", response!!.status)
        assertEquals(0, response.accepted)

        // No request should be made for empty list
        assertEquals(0, mockServer.requestCount)
    }

    @Test
    fun `postBatch returns null on server error`() = runTest {
        mockServer.enqueue(MockResponse().setResponseCode(500))

        val readings = listOf(OxiReading(spo2 = 97, heartRate = 72, battery = 85))
        val response = apiClient.postBatch(readings)

        assertNull(response)
    }

    // ==================== getAppVersion Tests ====================

    @Test
    fun `getAppVersion returns version info on success`() = runTest {
        val responseJson = """
            {
                "version": "1.2.0",
                "version_code": 3,
                "apk_url": "/static/app/o2relay-1.2.0.apk",
                "release_notes": "Bug fixes",
                "min_version_code": 1
            }
        """.trimIndent()

        mockServer.enqueue(MockResponse()
            .setResponseCode(200)
            .setBody(responseJson))

        val version = apiClient.getAppVersion()

        assertNotNull(version)
        assertEquals("1.2.0", version!!.version)
        assertEquals(3, version.versionCode)
        assertEquals("/static/app/o2relay-1.2.0.apk", version.apkUrl)
        assertEquals("Bug fixes", version.releaseNotes)
        assertEquals(1, version.minVersionCode)
    }

    @Test
    fun `getAppVersion returns null on 404`() = runTest {
        mockServer.enqueue(MockResponse().setResponseCode(404))

        val version = apiClient.getAppVersion()

        assertNull(version)
    }

    // ==================== isReachable Tests ====================

    @Test
    fun `isReachable returns true when Pi responds`() = runTest {
        mockServer.enqueue(MockResponse()
            .setResponseCode(200)
            .setBody("""{"timestamp": "now", "last_reading_age_seconds": 5, "source": "ble", "needs_relay": false, "pi_ble_connected": true}"""))

        val reachable = apiClient.isReachable()

        assertTrue(reachable)
    }

    @Test
    fun `isReachable returns false when Pi is down`() = runTest {
        mockServer.shutdown()

        val reachable = apiClient.isReachable()

        assertFalse(reachable)
    }
}
