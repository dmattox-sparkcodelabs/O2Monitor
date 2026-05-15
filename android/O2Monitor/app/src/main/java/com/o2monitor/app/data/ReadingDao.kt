package com.o2monitor.app.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query

@Dao
interface ReadingDao {
    @Insert
    suspend fun insert(reading: ReadingEntity): Long

    @Query("SELECT * FROM reading_queue ORDER BY createdAt ASC LIMIT :limit")
    suspend fun peek(limit: Int = 100): List<ReadingEntity>

    @Query("DELETE FROM reading_queue WHERE id IN (:ids)")
    suspend fun deleteByIds(ids: List<Long>)

    @Query("SELECT COUNT(*) FROM reading_queue")
    suspend fun count(): Int

    @Query("DELETE FROM reading_queue WHERE createdAt < :cutoff")
    suspend fun pruneExpired(cutoff: Long)
}
