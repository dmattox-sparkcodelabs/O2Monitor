package com.o2monitor.app.data

import android.content.SharedPreferences
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
            deviceId = android.os.Build.MODEL
        )
        dao.insert(entity)
    }

    suspend fun flushToCloud(): Boolean {
        val baseUrl = prefs.getString("server_url", null) ?: return false
        val apiKey = prefs.getString("api_key", null) ?: return false
        val client = ApiClient(httpClient, baseUrl, apiKey)

        val readings = dao.peek(50)
        if (readings.isEmpty()) return true

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

        val result = if (readings.size == 1) {
            client.postReading(payloads[0]).map { Unit }
        } else {
            client.postBatch(payloads).map { Unit }
        }

        if (result.isSuccess) {
            dao.deleteByIds(readings.map { it.id })
            return true
        }
        return false
    }

    suspend fun pendingCount(): Int = dao.count()

    suspend fun pruneExpired() {
        val cutoff = System.currentTimeMillis() - 24 * 60 * 60 * 1000
        dao.pruneExpired(cutoff)
    }
}
