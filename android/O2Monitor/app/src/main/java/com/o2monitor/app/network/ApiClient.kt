package com.o2monitor.app.network

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

@Serializable
data class PatientSummary(
    val id: String,
    val name: String,
    val deviceMac: String
)

@Serializable
data class ReadingPayload(
    val patientId: String,
    val spo2: Int,
    val heartRate: Int,
    val batteryLevel: Int,
    val movement: Int,
    val timestamp: String,
    val source: String,
    val deviceId: String
)

@Serializable
data class IngestResponse(val id: String)

private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()

private val json = Json { ignoreUnknownKeys = true }

class ApiClient(
    private val httpClient: OkHttpClient,
    private val baseUrl: String,
    private val apiKey: String
) {

    suspend fun getPatients(): Result<List<PatientSummary>> = withContext(Dispatchers.IO) {
        runCatching {
            val request = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/api/patients")
                .addHeader("x-api-key", apiKey)
                .get()
                .build()
            val response = httpClient.newCall(request).execute()
            if (!response.isSuccessful) {
                error("HTTP ${response.code}: ${response.body?.string()}")
            }
            val body = response.body?.string() ?: error("Empty response body")
            json.decodeFromString<List<PatientSummary>>(body)
        }
    }

    suspend fun postReading(reading: ReadingPayload): Result<IngestResponse> = withContext(Dispatchers.IO) {
        runCatching {
            val body = json.encodeToString(reading).toRequestBody(JSON_MEDIA_TYPE)
            val request = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/api/readings")
                .addHeader("x-api-key", apiKey)
                .post(body)
                .build()
            val response = httpClient.newCall(request).execute()
            if (!response.isSuccessful) {
                error("HTTP ${response.code}: ${response.body?.string()}")
            }
            val responseBody = response.body?.string() ?: error("Empty response body")
            json.decodeFromString<IngestResponse>(responseBody)
        }
    }
}
