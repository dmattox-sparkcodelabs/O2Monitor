package com.o2monitor.app.network

import android.util.Log
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

@Serializable
data class ReadingRecord(
    val id: String = "",
    val timestamp: String,
    val spo2: Int,
    val heartRate: Int,
    val batteryLevel: Int = 0,
    val movement: Int = 0,
    val source: String = "",
    val deviceId: String = ""
)

@Serializable
data class ReadingsResponse(
    val readings: List<ReadingRecord>,
    val count: Int = 0
)

@Serializable
data class BatchRequest(val readings: List<ReadingPayload>)

@Serializable
data class BatchResponse(val accepted: Int, val rejected: Int)

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
                val body = response.body?.string()
                Log.w(TAG, "getPatients: HTTP ${response.code} — $body")
                error("HTTP ${response.code}: $body")
            }
            val body = response.body?.string() ?: error("Empty response body")
            json.decodeFromString<List<PatientSummary>>(body)
        }
    }

    suspend fun postReading(reading: ReadingPayload): Result<IngestResponse> = withContext(Dispatchers.IO) {
        runCatching {
            val url = "${baseUrl.trimEnd('/')}/api/readings"
            val body = json.encodeToString(reading).toRequestBody(JSON_MEDIA_TYPE)
            val request = Request.Builder()
                .url(url)
                .addHeader("x-api-key", apiKey)
                .post(body)
                .build()
            val response = httpClient.newCall(request).execute()
            if (!response.isSuccessful) {
                val respBody = response.body?.string()
                Log.w(TAG, "postReading: HTTP ${response.code} — $respBody")
                error("HTTP ${response.code}: $respBody")
            }
            Log.d(TAG, "postReading: HTTP ${response.code}")
            val responseBody = response.body?.string() ?: error("Empty response body")
            json.decodeFromString<IngestResponse>(responseBody)
        }
    }

    suspend fun getReadings(patientId: String, hours: Int = 1): Result<ReadingsResponse> = withContext(Dispatchers.IO) {
        runCatching {
            val request = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/api/patients/$patientId/readings?hours=$hours")
                .addHeader("x-api-key", apiKey)
                .get()
                .build()
            val response = httpClient.newCall(request).execute()
            if (!response.isSuccessful) {
                val body = response.body?.string()
                Log.w(TAG, "getReadings: HTTP ${response.code} — $body")
                error("HTTP ${response.code}: $body")
            }
            val body = response.body?.string() ?: error("Empty response body")
            json.decodeFromString<ReadingsResponse>(body)
        }
    }

    suspend fun postBatch(readings: List<ReadingPayload>): Result<BatchResponse> = withContext(Dispatchers.IO) {
        runCatching {
            val url = "${baseUrl.trimEnd('/')}/api/readings/batch"
            val body = json.encodeToString(BatchRequest(readings)).toRequestBody(JSON_MEDIA_TYPE)
            val request = Request.Builder()
                .url(url)
                .addHeader("x-api-key", apiKey)
                .post(body)
                .build()
            val response = httpClient.newCall(request).execute()
            if (!response.isSuccessful) {
                val respBody = response.body?.string()
                Log.w(TAG, "postBatch: HTTP ${response.code} — $respBody")
                error("HTTP ${response.code}: $respBody")
            }
            val responseBody = response.body?.string() ?: error("Empty response body")
            val result = json.decodeFromString<BatchResponse>(responseBody)
            Log.d(TAG, "postBatch: HTTP ${response.code}, accepted=${result.accepted} rejected=${result.rejected}")
            result
        }
    }

    companion object {
        private const val TAG = "ApiClient"
    }
}
