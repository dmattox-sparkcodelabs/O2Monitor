package com.o2monitor.app.data

import android.content.SharedPreferences
import android.util.Log
import com.o2monitor.app.ble.OxiReading
import com.o2monitor.app.network.ApiClient
import com.o2monitor.app.network.ReadingPayload
import okhttp3.OkHttpClient

class ReadingRepository(
    private val dao: ReadingDao,
    private val prefs: SharedPreferences,
    private val httpClient: OkHttpClient
) {
    suspend fun enqueue(patientId: String, reading: OxiReading) {
        val entity = ReadingEntity(
            patientId = patientId,
            spo2 = reading.spo2,
            heartRate = reading.heartRate,
            batteryLevel = reading.batteryLevel,
            movement = reading.movement,
            timestamp = java.time.Instant.now().toString(),
            source = "live",
            deviceId = android.os.Build.MODEL
        )
        dao.insert(entity)
    }

    /**
     * Enqueue a reading with a pre-computed timestamp (from a downloaded .vld history file).
     * Uses [timestampMs] as the reading time and marks source as "history".
     */
    suspend fun enqueueAt(patientId: String, reading: OxiReading, timestampMs: Long) {
        val isoTimestamp = java.time.Instant.ofEpochMilli(timestampMs).toString()
        val entity = ReadingEntity(
            patientId = patientId,
            spo2 = reading.spo2,
            heartRate = reading.heartRate,
            batteryLevel = reading.batteryLevel,
            movement = reading.movement,
            timestamp = isoTimestamp,
            source = "history",
            deviceId = android.os.Build.MODEL
        )
        dao.insert(entity)
    }

    suspend fun flushToCloud(): Boolean {
        val baseUrl = prefs.getString("server_url", null)
        if (baseUrl == null) {
            Log.w(TAG, "flushToCloud: server_url not configured")
            return false
        }
        val apiKey = prefs.getString("api_key", null)
        if (apiKey == null) {
            Log.w(TAG, "flushToCloud: api_key not configured")
            return false
        }
        val client = ApiClient(httpClient, baseUrl, apiKey)

        var totalFlushed = 0
        while (true) {
            val readings = dao.peek(200)
            if (readings.isEmpty()) break

            val mode = if (readings.size == 1) "single" else "batch"
            Log.i(TAG, "flushToCloud: sending $mode of ${readings.size} to $baseUrl")

            val payloads = readings.map { reading ->
                ReadingPayload(
                    patientId = reading.patientId,
                    spo2 = reading.spo2,
                    heartRate = reading.heartRate,
                    batteryLevel = reading.batteryLevel,
                    movement = reading.movement,
                    timestamp = reading.timestamp,
                    source = reading.source,
                    deviceId = reading.deviceId
                )
            }

            if (readings.size == 1) {
                val result = client.postReading(payloads[0])
                if (result.isSuccess) {
                    dao.deleteByIds(readings.map { it.id })
                    totalFlushed += 1
                    Log.i(TAG, "flushToCloud: single succeeded (total $totalFlushed)")
                } else {
                    val ex = result.exceptionOrNull()
                    Log.w(TAG, "flushToCloud: single failed — ${ex?.javaClass?.simpleName}: ${ex?.message}")
                    val pending = dao.count()
                    Log.i(TAG, "flushToCloud: $totalFlushed flushed this cycle, $pending still pending")
                    return totalFlushed > 0
                }
            } else {
                val result = client.postBatch(payloads)
                if (result.isSuccess) {
                    val batch = result.getOrThrow()
                    val rejectedIds = batch.rejectedIndices.map { readings[it].id }
                    val acceptedIds = readings.map { it.id }
                    dao.deleteByIds(acceptedIds)
                    totalFlushed += batch.accepted
                    if (rejectedIds.isNotEmpty()) {
                        Log.w(TAG, "flushToCloud: batch dropped ${rejectedIds.size} invalid rows")
                    }
                    Log.i(TAG, "flushToCloud: batch accepted=${batch.accepted} rejected=${batch.rejected} (total $totalFlushed)")
                } else {
                    val ex = result.exceptionOrNull()
                    Log.w(TAG, "flushToCloud: batch failed — ${ex?.javaClass?.simpleName}: ${ex?.message}")
                    val pending = dao.count()
                    Log.i(TAG, "flushToCloud: $totalFlushed flushed this cycle, $pending still pending")
                    return totalFlushed > 0
                }
            }
        }
        val pending = dao.count()
        Log.i(TAG, "flushToCloud: complete, $totalFlushed flushed, $pending pending")
        return true
    }

    suspend fun pendingCount(): Int = dao.count()

    suspend fun pruneExpired() {
        val cutoff = System.currentTimeMillis() - 24 * 60 * 60 * 1000
        dao.pruneExpired(cutoff)
    }

    companion object {
        private const val TAG = "ReadingRepo"
    }
}
