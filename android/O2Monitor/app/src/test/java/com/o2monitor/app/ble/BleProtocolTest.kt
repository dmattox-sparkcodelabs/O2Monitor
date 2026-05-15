package com.o2monitor.app.ble

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
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
}
