package com.o2monitor.app.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "reading_queue")
data class ReadingEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val patientId: String,
    val spo2: Int,
    val heartRate: Int,
    val batteryLevel: Int,
    val movement: Int,
    val timestamp: String,  // ISO 8601 UTC
    val source: String = "live",
    val deviceId: String,
    val createdAt: Long = System.currentTimeMillis()
)
