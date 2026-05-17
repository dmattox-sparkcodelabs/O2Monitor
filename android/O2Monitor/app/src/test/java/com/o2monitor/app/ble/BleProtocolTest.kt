package com.o2monitor.app.ble

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BleProtocolTest {

    // -------------------------------------------------------------------------
    // CRC tests — known vectors cross-checked against the Python implementation
    // -------------------------------------------------------------------------

    @Test
    fun `calcCrc of 0x00 returns 0x00`() {
        assertEquals(0x00.toByte(), BleProtocol.calcCrc(byteArrayOf(0x00)))
    }

    @Test
    fun `calcCrc of 0x01 returns 0x07`() {
        assertEquals(0x07.toByte(), BleProtocol.calcCrc(byteArrayOf(0x01)))
    }

    @Test
    fun `calcCrc of 0xFF returns 0xF3`() {
        // Confirmed by v1 test suite — NOT 0x89
        assertEquals(0xF3.toByte(), BleProtocol.calcCrc(byteArrayOf(0xFF.toByte())))
    }

    @Test
    fun `calcCrc of command header bytes returns 0x1B`() {
        val header = byteArrayOf(
            0xAA.toByte(), 0x17, 0xE8.toByte(),
            0x00, 0x00,
            0x00, 0x00
        )
        assertEquals(0x1B.toByte(), BleProtocol.calcCrc(header))
    }

    @Test
    fun `calcCrc of 0x55 0x17 returns 0x28`() {
        assertEquals(0x28.toByte(), BleProtocol.calcCrc(byteArrayOf(0x55, 0x17)))
    }

    // -------------------------------------------------------------------------
    // buildCommand tests
    // -------------------------------------------------------------------------

    @Test
    fun `buildCommand 0x17 produces exact 8-byte packet`() {
        val expected = byteArrayOf(
            0xAA.toByte(), 0x17, 0xE8.toByte(),
            0x00, 0x00,
            0x00, 0x00,
            0x1B
        )
        assertArrayEquals(expected, BleProtocol.buildCommand(0x17))
    }

    // -------------------------------------------------------------------------
    // parseReading tests
    // -------------------------------------------------------------------------

    private fun makePayload(
        spo2: Int, hr: Int, flag: Int,
        battery: Int = 85, movement: Int = 0,
        size: Int = 13
    ): ByteArray {
        val buf = ByteArray(size)
        buf[0] = spo2.toByte()
        buf[1] = hr.toByte()
        buf[2] = flag.toByte()
        if (size > 7) buf[7] = battery.toByte()
        if (size > 9) buf[9] = movement.toByte()
        return buf
    }

    @Test
    fun `parseReading returns correct values for valid payload`() {
        val payload = makePayload(spo2 = 97, hr = 72, flag = 0x01, battery = 85, movement = 3)
        val reading = BleProtocol.parseReading(payload)
        assertNotNull(reading)
        assertEquals(97, reading!!.spo2)
        assertEquals(72, reading.heartRate)
        assertEquals(85, reading.batteryLevel)
        assertEquals(3, reading.movement)
    }

    @Test
    fun `parseReading returns null when flag is 0xFF (sensor off)`() {
        val payload = makePayload(spo2 = 97, hr = 72, flag = 0xFF)
        assertNull(BleProtocol.parseReading(payload))
    }

    @Test
    fun `parseReading returns null when flag is 0x00 and spo2 and hr are zero (idle)`() {
        val payload = makePayload(spo2 = 0, hr = 0, flag = 0x00)
        assertNull(BleProtocol.parseReading(payload))
    }

    @Test
    fun `parseReading does not suppress idle when flag is 0x00 but values are nonzero`() {
        // flag=0x00 with valid readings should NOT be suppressed
        val payload = makePayload(spo2 = 95, hr = 68, flag = 0x00)
        val reading = BleProtocol.parseReading(payload)
        assertNotNull(reading)
        assertEquals(95, reading!!.spo2)
        assertEquals(68, reading.heartRate)
    }

    @Test
    fun `parseReading returns null when payload is too short`() {
        val shortPayload = makePayload(spo2 = 97, hr = 72, flag = 0x01, size = 9)
        assertNull(BleProtocol.parseReading(shortPayload))
    }

    // -------------------------------------------------------------------------
    // PacketParser tests
    // -------------------------------------------------------------------------

    /**
     * Build a valid 0x55 response packet for testing the parser.
     *
     * Layout:
     *   [0]    0x55
     *   [1]    status
     *   [2]    status ^ 0xFF
     *   [3-4]  block LE uint16
     *   [5-6]  payload length LE uint16
     *   [7..7+payLen-1]  payload
     *   [-1]   CRC of all preceding bytes
     */
    private fun buildResponsePacket(
        status: Int = 0,
        block: Int = 0,
        payload: ByteArray = ByteArray(0)
    ): ByteArray {
        val payLen = payload.size
        val header = byteArrayOf(
            0x55,
            status.toByte(),
            (status xor 0xFF).toByte(),
            (block and 0xFF).toByte(),
            ((block shr 8) and 0xFF).toByte(),
            (payLen and 0xFF).toByte(),
            ((payLen shr 8) and 0xFF).toByte()
        )
        val body = header + payload
        val crc = BleProtocol.calcCrc(body)
        return body + byteArrayOf(crc)
    }

    @Test
    fun `PacketParser feed returns one packet from complete valid input`() {
        val payload = makePayload(spo2 = 97, hr = 72, flag = 0x01, battery = 85, movement = 0)
        val raw = buildResponsePacket(status = 0, block = 0, payload = payload)

        val parser = PacketParser()
        val packets = parser.feed(raw)

        assertEquals(1, packets.size)
        assertEquals(0, packets[0].status)
        assertEquals(0, packets[0].block)
        assertArrayEquals(payload, packets[0].payload)
    }

    @Test
    fun `PacketParser feed assembles packet across two fragmented calls`() {
        val payload = makePayload(spo2 = 97, hr = 72, flag = 0x01)
        val raw = buildResponsePacket(payload = payload)
        val half = raw.size / 2
        val part1 = raw.copyOfRange(0, half)
        val part2 = raw.copyOfRange(half, raw.size)

        val parser = PacketParser()
        val first = parser.feed(part1)
        assertEquals("Should not emit before packet is complete", 0, first.size)

        val second = parser.feed(part2)
        assertEquals(1, second.size)
        assertArrayEquals(payload, second[0].payload)
    }

    @Test
    fun `PacketParser feed skips garbage prefix and finds valid packet`() {
        val payload = makePayload(spo2 = 95, hr = 60, flag = 0x01)
        val validPacket = buildResponsePacket(payload = payload)
        val garbage = byteArrayOf(0x01, 0x02, 0x03, 0xAA.toByte())
        val combined = garbage + validPacket

        val parser = PacketParser()
        val packets = parser.feed(combined)

        assertEquals(1, packets.size)
        assertArrayEquals(payload, packets[0].payload)
    }

    @Test
    fun `PacketParser feed drops packet with bad CRC`() {
        val payload = makePayload(spo2 = 97, hr = 72, flag = 0x01)
        val raw = buildResponsePacket(payload = payload).toMutableList()
        // Corrupt the CRC byte (last byte)
        raw[raw.size - 1] = (raw[raw.size - 1].toInt() xor 0xFF).toByte()

        val parser = PacketParser()
        val packets = parser.feed(raw.toByteArray())

        assertEquals(0, packets.size)
    }

    // -------------------------------------------------------------------------
    // buildPacket tests
    // -------------------------------------------------------------------------

    @Test
    fun `buildPacket CMD_INFO no payload produces correct 8-byte packet`() {
        // CMD_INFO = 0x14 → negate = 0xEB
        // block=0, payLen=0
        val cmdByte: Byte = 0x14
        val expected = byteArrayOf(
            0xAA.toByte(), 0x14, 0xEB.toByte(),
            0x00, 0x00,  // block LE
            0x00, 0x00   // payload length LE
        )
        val expectedCrc = BleProtocol.calcCrc(expected)
        val packet = BleProtocol.buildPacket(cmdByte)
        assertEquals("packet must be 8 bytes for empty payload", 8, packet.size)
        assertArrayEquals(expected + byteArrayOf(expectedCrc), packet)
    }

    @Test
    fun `buildPacket CMD_FILE_OPEN with payload produces correct packet`() {
        val cmdByte: Byte = 0x03
        val payload = "test.vld ".toByteArray(Charsets.US_ASCII)
        val packet = BleProtocol.buildPacket(cmdByte, block = 0, payload = payload)

        // Expected total: 7 (header) + payload.size + 1 (CRC) = 8 + payload.size
        assertEquals(8 + payload.size, packet.size)
        assertEquals(0xAA.toByte(), packet[0])
        assertEquals(cmdByte, packet[1])
        assertEquals((0x03 xor 0xFF).toByte(), packet[2])
        // payload length low byte
        assertEquals((payload.size and 0xFF).toByte(), packet[5])
        // payload content starts at index 7
        assertArrayEquals(payload, packet.copyOfRange(7, 7 + payload.size))
        // CRC covers all bytes except the last
        val expectedCrc = BleProtocol.calcCrc(packet.copyOfRange(0, packet.size - 1))
        assertEquals(expectedCrc, packet[packet.size - 1])
    }

    @Test
    fun `buildCommand delegates to buildPacket and produces same result as buildPacket`() {
        assertArrayEquals(
            BleProtocol.buildPacket(BleProtocol.CMD_READ_SENSORS),
            BleProtocol.buildCommand(BleProtocol.CMD_READ_SENSORS)
        )
    }

    @Test
    fun `buildPacket with non-zero block encodes block in LE bytes 3 and 4`() {
        val packet = BleProtocol.buildPacket(BleProtocol.CMD_FILE_READ, block = 0x0102)
        assertEquals(0x02.toByte(), packet[3])  // low byte
        assertEquals(0x01.toByte(), packet[4])  // high byte
    }

    // -------------------------------------------------------------------------
    // VldParser tests
    // -------------------------------------------------------------------------

    /**
     * Build a minimal valid v3 .vld blob.
     *
     * Header is 40 bytes (26 fixed + 14 padding), followed by [recordData].
     */
    private fun buildVldBlob(
        version: Int = 3,
        year: Int = 2026, month: Int = 1, day: Int = 15,
        hour: Int = 22, minute: Int = 0, second: Int = 0,
        duration: Int = 8,  // 2 records × 4s resolution
        spo2Avg: Int = 95, spo2Min: Int = 90,
        timeUnder90: Int = 0, eventsUnder90: Int = 0,
        recordData: ByteArray = byteArrayOf(
            // record 1: spo2=97 hr=72 invalid=0 motion=0 vibration=0
            97, 72, 0, 0, 0,
            // record 2: spo2=95 hr=70 invalid=0 motion=1 vibration=0
            95, 70, 0, 1, 0
        )
    ): ByteArray {
        val header = ByteArray(40)
        val buf = java.nio.ByteBuffer.wrap(header).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        buf.putShort(version.toShort())          // version
        buf.putShort(year.toShort())             // year
        buf.put(month.toByte())                  // month
        buf.put(day.toByte())                    // day
        buf.put(hour.toByte())                   // hour
        buf.put(minute.toByte())                 // minute
        buf.put(second.toByte())                 // second
        buf.putShort(0)                          // filesize
        buf.putShort(0)                          // filesize2
        buf.putShort(duration.toShort())         // duration
        buf.putShort(0)                          // duration2
        buf.put(spo2Avg.toByte())                // spo2_avg
        buf.put(spo2Min.toByte())                // spo2_min
        buf.put(0)                               // spo2_3pct
        buf.put(0)                               // spo2_4pct
        buf.put(0)                               // unknown1
        buf.putShort(timeUnder90.toShort())      // time_under_90pct
        buf.put(eventsUnder90.toByte())          // events_under_90pct
        buf.put(0)                               // o2_score
        // Remaining 14 bytes are already zero (padding)
        return header + recordData
    }

    private fun buildV5VldBlob(
        year: Int = 2026, month: Int = 5, day: Int = 17,
        hour: Int = 0, minute: Int = 5, second: Int = 38,
        duration: Int = 4,
        recordData: ByteArray = byteArrayOf(
            96, 102, 0, 22, 0,
            95, 102, 0, 0, 0
        )
    ): ByteArray {
        val header = ByteArray(40)
        val buf = java.nio.ByteBuffer.wrap(header).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        buf.putShort(5.toShort())                // version
        buf.putShort(year.toShort())             // year
        buf.put(month.toByte())                  // month
        buf.put(day.toByte())                    // day
        buf.put(hour.toByte())                   // hour
        buf.put(minute.toByte())                 // minute
        buf.put(second.toByte())                 // second
        buf.putInt(header.size + recordData.size)// filesize
        buf.putInt(duration)                     // duration seconds
        buf.put(96.toByte())                     // spo2_avg
        buf.put(88.toByte())                     // spo2_min
        buf.put(0)                               // spo2_3pct
        buf.put(0)                               // spo2_4pct
        buf.put(0)                               // unknown1
        buf.putShort(0)                          // time_under_90pct
        buf.put(0)                               // events_under_90pct
        buf.put(0)                               // o2_score
        return header + recordData
    }

    @Test
    fun `VldParser parse returns correct header for valid v3 blob`() {
        val blob = buildVldBlob()
        val (header, _) = VldParser.parse(blob)

        assertEquals(3, header.version)
        assertEquals(2026, header.startYear)
        assertEquals(1, header.startMonth)
        assertEquals(15, header.startDay)
        assertEquals(22, header.startHour)
        assertEquals(0, header.startMinute)
        assertEquals(0, header.startSecond)
        assertEquals(2, header.recordCount)
        assertEquals(95, header.spo2Avg)
        assertEquals(90, header.spo2Min)
    }

    @Test
    fun `VldParser parse returns correct records for valid v3 blob`() {
        val blob = buildVldBlob()
        val (_, records) = VldParser.parse(blob)

        assertEquals(2, records.size)
        assertEquals(97, records[0].spo2)
        assertEquals(72, records[0].heartRate)
        assertEquals(0, records[0].motion)
        assertTrue(records[0].isValid)
        assertEquals(0.0, records[0].offsetSeconds, 0.001)

        assertEquals(95, records[1].spo2)
        assertEquals(70, records[1].heartRate)
        assertEquals(1, records[1].motion)
        assertTrue(records[1].isValid)
        assertEquals(4.0, records[1].offsetSeconds, 0.001)
    }

    @Test
    fun `VldParser parse returns correct records for valid v5 blob`() {
        val blob = buildV5VldBlob()
        val (header, records) = VldParser.parse(blob)

        assertEquals(5, header.version)
        assertEquals(2026, header.startYear)
        assertEquals(5, header.startMonth)
        assertEquals(17, header.startDay)
        assertEquals(2.0, header.resolutionSeconds, 0.001)
        assertEquals(2, records.size)
        assertEquals(96, records[0].spo2)
        assertEquals(102, records[0].heartRate)
        assertEquals(22, records[0].motion)
        assertTrue(records[0].isValid)
        assertEquals(2.0, records[1].offsetSeconds, 0.001)
    }

    @Test
    fun `VldParser parse rejects unsupported file versions`() {
        val blob = buildVldBlob(version = 2)
        try {
            VldParser.parse(blob)
            throw AssertionError("Expected IllegalArgumentException")
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message?.contains("version") == true)
        }
    }

    @Test
    fun `VldParser parse rejects too-short blobs`() {
        val tooShort = ByteArray(20)
        try {
            VldParser.parse(tooShort)
            throw AssertionError("Expected IllegalArgumentException")
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message?.contains("short") == true)
        }
    }

    @Test
    fun `VldParser parse marks record with invalid_flag != 0 as invalid`() {
        val recordData = byteArrayOf(
            97, 72, 1, 0, 0  // invalid_flag = 1
        )
        val blob = buildVldBlob(duration = 4, recordData = recordData)
        val (_, records) = VldParser.parse(blob)

        assertEquals(1, records.size)
        assertFalse(records[0].isValid)
    }

    @Test
    fun `VldParser parse marks record with spo2 below 10 as invalid`() {
        val recordData = byteArrayOf(
            5, 72, 0, 0, 0   // spo2 = 5 < 10
        )
        val blob = buildVldBlob(duration = 4, recordData = recordData)
        val (_, records) = VldParser.parse(blob)

        assertEquals(1, records.size)
        assertFalse(records[0].isValid)
    }

    @Test
    fun `VldParser parse marks record with spo2 above 100 as invalid`() {
        val recordData = byteArrayOf(
            105.toByte(), 72, 0, 0, 0  // spo2 = 105 > 100
        )
        val blob = buildVldBlob(duration = 4, recordData = recordData)
        val (_, records) = VldParser.parse(blob)

        assertEquals(1, records.size)
        assertFalse(records[0].isValid)
    }

    @Test
    fun `VldParser parse snaps resolution to 2s when raw is close`() {
        // 2 records with duration=4 → raw=2.0
        val blob = buildVldBlob(duration = 4, recordData = byteArrayOf(95, 70, 0, 0, 0, 97, 72, 0, 0, 0))
        val (header, records) = VldParser.parse(blob)
        assertEquals(2.0, header.resolutionSeconds, 0.001)
        assertEquals(0.0, records[0].offsetSeconds, 0.001)
        assertEquals(2.0, records[1].offsetSeconds, 0.001)
    }
}
