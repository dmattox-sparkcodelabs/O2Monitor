package com.o2monitor.app.network

import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

class ApiClientTest {

    private lateinit var mockWebServer: MockWebServer
    private lateinit var httpClient: OkHttpClient
    private lateinit var apiClient: ApiClient

    companion object {
        private const val TEST_API_KEY = "test-api-key-12345"
    }

    @Before
    fun setup() {
        mockWebServer = MockWebServer()
        mockWebServer.start()
        httpClient = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .writeTimeout(5, TimeUnit.SECONDS)
            .build()
        apiClient = ApiClient(
            httpClient = httpClient,
            baseUrl = mockWebServer.url("/").toString(),
            apiKey = TEST_API_KEY
        )
    }

    @After
    fun tearDown() {
        mockWebServer.shutdown()
    }

    @Test
    fun `getPatients returns failure on network error`() = runTest {
        // Shut down server to simulate network error
        mockWebServer.shutdown()

        val result = apiClient.getPatients()

        assertTrue("Expected failure on network error", result.isFailure)
    }

    @Test
    fun `getPatients parses valid JSON response`() = runTest {
        val responseBody = """
            {
                "data": [
                    {"id": "patient-1", "name": "Dad", "deviceMac": "C8:F1:6B:56:7B:F1"},
                    {"id": "patient-2", "name": "Mom", "deviceMac": "AA:BB:CC:DD:EE:FF"}
                ]
            }
        """.trimIndent()
        mockWebServer.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(responseBody)
                .addHeader("Content-Type", "application/json")
        )

        val result = apiClient.getPatients()

        assertTrue("Expected success", result.isSuccess)
        val patients = result.getOrNull()!!
        assertEquals(2, patients.size)
        assertEquals("patient-1", patients[0].id)
        assertEquals("Dad", patients[0].name)
        assertEquals("C8:F1:6B:56:7B:F1", patients[0].deviceMac)
        assertEquals("patient-2", patients[1].id)
    }

    @Test
    fun `getPatients includes API key header in request`() = runTest {
        mockWebServer.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"data":[]}""")
                .addHeader("Content-Type", "application/json")
        )

        apiClient.getPatients()

        val recordedRequest = mockWebServer.takeRequest()
        assertEquals(TEST_API_KEY, recordedRequest.getHeader("x-api-key"))
    }

    @Test
    fun `getPatients returns failure on non-200 response`() = runTest {
        mockWebServer.enqueue(
            MockResponse()
                .setResponseCode(401)
                .setBody("""{"error": "Unauthorized"}""")
        )

        val result = apiClient.getPatients()

        assertTrue("Expected failure on 401 response", result.isFailure)
    }

    @Test
    fun `postReading includes API key header in request`() = runTest {
        mockWebServer.enqueue(
            MockResponse()
                .setResponseCode(201)
                .setBody("""{"id": "reading-uuid-123"}""")
                .addHeader("Content-Type", "application/json")
        )
        val reading = ReadingPayload(
            patientId = "patient-1",
            spo2 = 97,
            heartRate = 72,
            batteryLevel = 85,
            movement = 0,
            timestamp = "2026-05-15T09:30:00Z",
            source = "live",
            deviceId = "D4:30:77:4B:0F:C7"
        )

        val result = apiClient.postReading(reading)

        assertTrue("Expected success", result.isSuccess)
        val recordedRequest = mockWebServer.takeRequest()
        assertEquals(TEST_API_KEY, recordedRequest.getHeader("x-api-key"))
        assertEquals("reading-uuid-123", result.getOrNull()?.id)
    }
}
