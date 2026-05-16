// =============================================================================
// DISCLAIMER: This software is NOT a medical device and is NOT intended for
// medical monitoring, diagnosis, or treatment. This is a proof of concept for
// educational purposes only. Do not rely on this system for health decisions.
// =============================================================================
package com.o2monitor.app.ble

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Summary data from a .vld v3 file header.
 *
 * Port of Python VldHeader dataclass in history.py.
 */
data class VldHeader(
    val version: Int,
    val startYear: Int,
    val startMonth: Int,
    val startDay: Int,
    val startHour: Int,
    val startMinute: Int,
    val startSecond: Int,
    val durationSeconds: Int,
    val recordCount: Int,
    val resolutionSeconds: Double,
    val spo2Avg: Int,
    val spo2Min: Int,
    val timeUnder90Seconds: Int,
    val eventsUnder90: Int
)

/**
 * One 5-byte sample record from a .vld v3 file.
 *
 * [offsetSeconds] is the time from the session start for this record.
 */
data class VldRecord(
    val offsetSeconds: Double,
    val spo2: Int,
    val heartRate: Int,
    val motion: Int,
    val isValid: Boolean
)

/**
 * Parser for Viatom/Wellue stored recording files (.vld v3 format).
 *
 * File layout:
 *   - 40-byte header (26 fixed bytes + 14 bytes padding)
 *   - N records of 5 bytes each: (spo2, heart_rate, invalid_flag, motion, vibration)
 *
 * Port of Python parse_vld_v3() in history.py.
 * Cross-checked against ericm301/O2Ring-DataFetcher's o2file.py.
 */
object VldParser {
    private const val HEADER_SIZE = 40
    private const val RECORD_SIZE = 5

    // 26-byte fixed header struct (little-endian):
    //   version(H), year(H), month(B), day(B), hour(B), minute(B), second(B),
    //   filesize(H), filesize2(H), duration(H), duration2(H),
    //   spo2_avg(B), spo2_min(B), spo2_3pct(B), spo2_4pct(B), unknown1(B),
    //   time_under_90pct(H), events_under_90pct(B), o2_score(B)
    private const val FIXED_HEADER_SIZE = 26

    /**
     * Parse a .vld v3 file blob into a header and list of records.
     *
     * @throws IllegalArgumentException on malformed input (too short, wrong version,
     *   invalid timestamp, or no records)
     */
    fun parse(blob: ByteArray): Pair<VldHeader, List<VldRecord>> {
        require(blob.size >= HEADER_SIZE) {
            "file too short: ${blob.size} bytes"
        }

        val buf = ByteBuffer.wrap(blob, 0, FIXED_HEADER_SIZE).order(ByteOrder.LITTLE_ENDIAN)

        val version = buf.short.toInt() and 0xFFFF
        require(version == 3) { "unsupported file version: $version" }

        val year = buf.short.toInt() and 0xFFFF
        val month = buf.get().toInt() and 0xFF
        val day = buf.get().toInt() and 0xFF
        val hour = buf.get().toInt() and 0xFF
        val minute = buf.get().toInt() and 0xFF
        val second = buf.get().toInt() and 0xFF

        // Validate calendar fields loosely (same checks java.util.Calendar would do)
        require(month in 1..12) { "invalid header timestamp: month=$month" }
        require(day in 1..31) { "invalid header timestamp: day=$day" }
        require(hour in 0..23) { "invalid header timestamp: hour=$hour" }
        require(minute in 0..59) { "invalid header timestamp: minute=$minute" }
        require(second in 0..59) { "invalid header timestamp: second=$second" }

        /* filesize(H) */ buf.short
        /* filesize2(H) */ buf.short
        val duration = buf.short.toInt() and 0xFFFF
        /* duration2(H) */ buf.short
        val spo2Avg = buf.get().toInt() and 0xFF
        val spo2Min = buf.get().toInt() and 0xFF
        /* spo2_3pct(B) */ buf.get()
        /* spo2_4pct(B) */ buf.get()
        /* unknown1(B) */ buf.get()
        val timeUnder90 = buf.short.toInt() and 0xFFFF
        val eventsUnder90 = buf.get().toInt() and 0xFF
        /* o2_score(B) */ buf.get()

        val dataLen = blob.size - HEADER_SIZE
        val recordCount = dataLen / RECORD_SIZE
        require(recordCount > 0) { "file contains no records" }

        val resolution: Double = if (duration <= 0) {
            // Incomplete session — fall back to the most common default
            4.0
        } else {
            val raw = duration.toDouble() / recordCount
            when {
                Math.abs(raw - 2.0) < 0.1 -> 2.0
                Math.abs(raw - 4.0) < 0.1 -> 4.0
                else -> raw
            }
        }

        val header = VldHeader(
            version = version,
            startYear = year,
            startMonth = month,
            startDay = day,
            startHour = hour,
            startMinute = minute,
            startSecond = second,
            durationSeconds = duration,
            recordCount = recordCount,
            resolutionSeconds = resolution,
            spo2Avg = spo2Avg,
            spo2Min = spo2Min,
            timeUnder90Seconds = timeUnder90,
            eventsUnder90 = eventsUnder90
        )

        val records = buildList {
            var offset = HEADER_SIZE
            for (i in 0 until recordCount) {
                if (offset + RECORD_SIZE > blob.size) break
                val spo2 = blob[offset].toInt() and 0xFF
                val hr = blob[offset + 1].toInt() and 0xFF
                val invalidFlag = blob[offset + 2].toInt() and 0xFF
                val motion = blob[offset + 3].toInt() and 0xFF
                // blob[offset + 4] is vibration — unused
                offset += RECORD_SIZE

                val isValid = invalidFlag == 0 && spo2 in 10..100
                add(VldRecord(
                    offsetSeconds = i * resolution,
                    spo2 = spo2,
                    heartRate = hr,
                    motion = motion,
                    isValid = isValid
                ))
            }
        }

        return Pair(header, records)
    }

    /**
     * Split the comma-separated FileList field from a getInfo() response into
     * a list of clean filenames. Port of Python parse_filelist().
     */
    fun parseFileList(fileListField: String): List<String> =
        fileListField.split(",").filter { it.isNotEmpty() }
}
