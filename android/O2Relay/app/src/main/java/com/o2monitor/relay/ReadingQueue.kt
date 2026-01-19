package com.o2monitor.relay

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.util.Log
import java.time.Instant

/**
 * SQLite-backed queue for storing oximeter readings when Pi is unreachable.
 *
 * Readings are stored locally and flushed to the Pi when connectivity returns.
 * The queue is FIFO - oldest readings are sent first.
 */
class ReadingQueue(context: Context) : SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {

    companion object {
        private const val TAG = "ReadingQueue"
        private const val DATABASE_NAME = "o2relay.db"
        private const val DATABASE_VERSION = 1

        // Table and columns
        private const val TABLE_READINGS = "queued_readings"
        private const val COL_ID = "id"
        private const val COL_SPO2 = "spo2"
        private const val COL_HEART_RATE = "heart_rate"
        private const val COL_BATTERY = "battery"
        private const val COL_TIMESTAMP = "timestamp"
        private const val COL_CREATED_AT = "created_at"

        // Max age for readings (24 hours in milliseconds)
        private const val MAX_READING_AGE_MS = 24 * 60 * 60 * 1000L

        // Max queue size to prevent unbounded growth
        private const val MAX_QUEUE_SIZE = 10000
    }

    override fun onCreate(db: SQLiteDatabase) {
        val createTable = """
            CREATE TABLE $TABLE_READINGS (
                $COL_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                $COL_SPO2 INTEGER NOT NULL,
                $COL_HEART_RATE INTEGER NOT NULL,
                $COL_BATTERY INTEGER NOT NULL,
                $COL_TIMESTAMP TEXT NOT NULL,
                $COL_CREATED_AT INTEGER NOT NULL
            )
        """.trimIndent()

        db.execSQL(createTable)
        Log.i(TAG, "Database created")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // For now, just recreate. In production, handle migrations properly.
        Log.w(TAG, "Upgrading database from $oldVersion to $newVersion - dropping data")
        db.execSQL("DROP TABLE IF EXISTS $TABLE_READINGS")
        onCreate(db)
    }

    /**
     * Add a reading to the queue.
     *
     * @param reading The reading to queue
     * @return The row ID of the inserted reading, or -1 if failed
     */
    fun enqueue(reading: OxiReading): Long {
        // Check queue size limit
        val currentSize = count()
        if (currentSize >= MAX_QUEUE_SIZE) {
            Log.w(TAG, "Queue full ($currentSize readings), dropping oldest")
            pruneOldest(100) // Remove oldest 100 readings
        }

        val db = writableDatabase
        val values = ContentValues().apply {
            put(COL_SPO2, reading.spo2)
            put(COL_HEART_RATE, reading.heartRate)
            put(COL_BATTERY, reading.battery)
            put(COL_TIMESTAMP, reading.timestamp.toString())
            put(COL_CREATED_AT, System.currentTimeMillis())
        }

        val id = db.insert(TABLE_READINGS, null, values)
        if (id != -1L) {
            Log.d(TAG, "Queued reading: SpO2=${reading.spo2}, HR=${reading.heartRate} (id=$id)")
        } else {
            Log.e(TAG, "Failed to queue reading")
        }
        return id
    }

    /**
     * Peek at readings without removing them.
     *
     * @param limit Maximum number of readings to return
     * @param newestFirst If true, returns newest readings first (for prioritized flush)
     * @return List of queued readings
     */
    fun peek(limit: Int = 100, newestFirst: Boolean = false): List<QueuedReading> {
        val readings = mutableListOf<QueuedReading>()
        val db = readableDatabase

        val orderBy = if (newestFirst) "$COL_ID DESC" else "$COL_ID ASC"
        val cursor = db.query(
            TABLE_READINGS,
            arrayOf(COL_ID, COL_SPO2, COL_HEART_RATE, COL_BATTERY, COL_TIMESTAMP, COL_CREATED_AT),
            null, null, null, null,
            orderBy,
            limit.toString()
        )

        cursor.use {
            while (it.moveToNext()) {
                val id = it.getLong(it.getColumnIndexOrThrow(COL_ID))
                val spo2 = it.getInt(it.getColumnIndexOrThrow(COL_SPO2))
                val heartRate = it.getInt(it.getColumnIndexOrThrow(COL_HEART_RATE))
                val battery = it.getInt(it.getColumnIndexOrThrow(COL_BATTERY))
                val timestampStr = it.getString(it.getColumnIndexOrThrow(COL_TIMESTAMP))
                val createdAt = it.getLong(it.getColumnIndexOrThrow(COL_CREATED_AT))

                val timestamp = try {
                    Instant.parse(timestampStr)
                } catch (e: Exception) {
                    Instant.ofEpochMilli(createdAt)
                }

                readings.add(
                    QueuedReading(
                        id = id,
                        reading = OxiReading(
                            spo2 = spo2,
                            heartRate = heartRate,
                            battery = battery,
                            timestamp = timestamp
                        ),
                        createdAt = createdAt
                    )
                )
            }
        }

        return readings
    }

    /**
     * Remove readings from the queue by their IDs.
     *
     * @param ids List of reading IDs to remove
     * @return Number of readings removed
     */
    fun remove(ids: List<Long>): Int {
        if (ids.isEmpty()) return 0

        val db = writableDatabase
        val placeholders = ids.joinToString(",") { "?" }
        val args = ids.map { it.toString() }.toTypedArray()

        val deleted = db.delete(TABLE_READINGS, "$COL_ID IN ($placeholders)", args)
        Log.d(TAG, "Removed $deleted readings from queue")
        return deleted
    }

    /**
     * Remove a single reading by ID.
     */
    fun remove(id: Long): Boolean {
        return remove(listOf(id)) > 0
    }

    /**
     * Get the number of readings in the queue.
     */
    fun count(): Int {
        val db = readableDatabase
        val cursor = db.rawQuery("SELECT COUNT(*) FROM $TABLE_READINGS", null)
        cursor.use {
            return if (it.moveToFirst()) it.getInt(0) else 0
        }
    }

    /**
     * Check if the queue is empty.
     */
    fun isEmpty(): Boolean = count() == 0

    /**
     * Clear all readings from the queue.
     *
     * @return Number of readings deleted
     */
    fun clear(): Int {
        val db = writableDatabase
        val deleted = db.delete(TABLE_READINGS, null, null)
        Log.i(TAG, "Cleared queue ($deleted readings)")
        return deleted
    }

    /**
     * Remove readings older than MAX_READING_AGE_MS.
     *
     * @return Number of readings pruned
     */
    fun pruneExpired(): Int {
        val cutoff = System.currentTimeMillis() - MAX_READING_AGE_MS
        val db = writableDatabase
        val deleted = db.delete(TABLE_READINGS, "$COL_CREATED_AT < ?", arrayOf(cutoff.toString()))
        if (deleted > 0) {
            Log.i(TAG, "Pruned $deleted expired readings")
        }
        return deleted
    }

    /**
     * Remove the oldest N readings.
     */
    private fun pruneOldest(count: Int): Int {
        val db = writableDatabase
        val deleted = db.delete(
            TABLE_READINGS,
            "$COL_ID IN (SELECT $COL_ID FROM $TABLE_READINGS ORDER BY $COL_ID ASC LIMIT ?)",
            arrayOf(count.toString())
        )
        if (deleted > 0) {
            Log.i(TAG, "Pruned $deleted oldest readings")
        }
        return deleted
    }

    /**
     * Get queue statistics.
     */
    fun getStats(): QueueStats {
        val db = readableDatabase

        var totalCount = 0
        var oldestTimestamp: Long? = null
        var newestTimestamp: Long? = null

        val cursor = db.rawQuery(
            """
            SELECT
                COUNT(*) as count,
                MIN($COL_CREATED_AT) as oldest,
                MAX($COL_CREATED_AT) as newest
            FROM $TABLE_READINGS
            """.trimIndent(),
            null
        )

        cursor.use {
            if (it.moveToFirst()) {
                totalCount = it.getInt(0)
                if (totalCount > 0) {
                    oldestTimestamp = it.getLong(1)
                    newestTimestamp = it.getLong(2)
                }
            }
        }

        return QueueStats(
            count = totalCount,
            oldestTimestamp = oldestTimestamp,
            newestTimestamp = newestTimestamp
        )
    }
}

/**
 * A reading stored in the queue with its database ID.
 */
data class QueuedReading(
    val id: Long,
    val reading: OxiReading,
    val createdAt: Long
)

/**
 * Queue statistics.
 */
data class QueueStats(
    val count: Int,
    val oldestTimestamp: Long?,
    val newestTimestamp: Long?
) {
    val isEmpty: Boolean get() = count == 0

    fun oldestAgeMs(): Long? {
        return oldestTimestamp?.let { System.currentTimeMillis() - it }
    }
}
