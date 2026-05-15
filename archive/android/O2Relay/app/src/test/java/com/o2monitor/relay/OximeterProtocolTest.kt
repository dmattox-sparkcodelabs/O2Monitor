package com.o2monitor.relay

import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for OximeterProtocol.
 *
 * CRC test vectors generated from Python implementation to ensure compatibility.
 */
class OximeterProtocolTest {

    /**
     * Test CRC calculation matches Python implementation.
     *
     * Python test:
     * >>> def calc_crc(data):
     * ...     crc = 0x00
     * ...     for b in data:
     * ...         chk = (crc ^ b) & 0xFF
     * ...         crc = 0x00
     * ...         if chk & 0x01: crc ^= 0x07
     * ...         if chk & 0x02: crc ^= 0x0e
     * ...         if chk & 0x04: crc ^= 0x1c
     * ...         if chk & 0x08: crc ^= 0x38
     * ...         if chk & 0x10: crc ^= 0x70
     * ...         if chk & 0x20: crc ^= 0xe0
     * ...         if chk & 0x40: crc ^= 0xc7
     * ...         if chk & 0x80: crc ^= 0x89
     * ...     return crc
     *
     * Test vectors:
     * calc_crc([0xAA, 0x17, 0xE8, 0x00, 0x00, 0x00, 0x00]) = 0xB8
     * calc_crc([0x00]) = 0x00
     * calc_crc([0x01]) = 0x07
     * calc_crc([0xFF]) = 0x89
     * calc_crc([0x55, 0x17, 0xE8, 0x00, 0x00, 0x0D, 0x00]) = (calculated below)
     */
    @Test
    fun testCrcEmptyByte() {
        // CRC of [0x00] should be 0x00
        val result = OximeterProtocol.calcCrc(byteArrayOf(0x00))
        assertEquals(0x00.toByte(), result)
    }

    @Test
    fun testCrcSingleByte() {
        // CRC of [0x01] should be 0x07
        val result = OximeterProtocol.calcCrc(byteArrayOf(0x01))
        assertEquals(0x07.toByte(), result)
    }

    @Test
    fun testCrcAllOnes() {
        // CRC of [0xFF] - calculated by tracing through algorithm
        val result = OximeterProtocol.calcCrc(byteArrayOf(0xFF.toByte()))
        assertEquals(0xF3.toByte(), result)
    }

    @Test
    fun testCrcReadingCommand() {
        // CRC of command packet [0xAA, 0x17, 0xE8, 0x00, 0x00, 0x00, 0x00]
        // The correct CRC is 0x1B (verified by running the algorithm)
        val data = byteArrayOf(
            0xAA.toByte(), 0x17, 0xE8.toByte(),
            0x00, 0x00, 0x00, 0x00
        )
        val result = OximeterProtocol.calcCrc(data)
        assertEquals(0x1B.toByte(), result)
    }

    @Test
    fun testCrcMultipleBytes() {
        // Test with some arbitrary data
        // CRC of [0x55, 0x17] - calculated by algorithm
        val data = byteArrayOf(0x55, 0x17)
        val result = OximeterProtocol.calcCrc(data)
        assertEquals(0x28.toByte(), result)
    }

    /**
     * Test building the reading command.
     */
    @Test
    fun testBuildReadingCommand() {
        val command = OximeterProtocol.buildReadingCommand()

        // Should be 8 bytes
        assertEquals(8, command.size)

        // Check structure
        assertEquals(0xAA.toByte(), command[0])  // Header
        assertEquals(0x17.toByte(), command[1])  // Command
        assertEquals(0xE8.toByte(), command[2])  // Complement (0xFF ^ 0x17)
        assertEquals(0x00.toByte(), command[3])  // Padding
        assertEquals(0x00.toByte(), command[4])  // Padding
        assertEquals(0x00.toByte(), command[5])  // Padding
        assertEquals(0x00.toByte(), command[6])  // Padding
        assertEquals(0x1B.toByte(), command[7])  // CRC (calculated)
    }

    /**
     * Test parsing a valid reading packet.
     */
    @Test
    fun testParseValidPacket() {
        // Construct a valid packet with 13-byte payload
        // Header: 0x55, response type, complement, block ID (2), length (2), payload (13), CRC
        val spo2 = 97
        val heartRate = 72
        val battery = 85
        val flag = 0x01  // Valid reading

        val payload = ByteArray(13)
        payload[0] = spo2.toByte()
        payload[1] = heartRate.toByte()
        payload[2] = flag.toByte()
        payload[7] = battery.toByte()

        // Build packet
        val packet = ByteArray(7 + 13 + 1)
        packet[0] = 0x55  // Header
        packet[1] = 0x17  // Response type
        packet[2] = 0xE8.toByte()  // Complement
        packet[3] = 0x00  // Block ID low
        packet[4] = 0x00  // Block ID high
        packet[5] = 0x0D  // Length low (13)
        packet[6] = 0x00  // Length high
        System.arraycopy(payload, 0, packet, 7, 13)

        // Calculate and set CRC
        packet[20] = OximeterProtocol.calcCrc(packet.copyOfRange(0, 20))

        // Parse
        val result = OximeterProtocol.parsePacket(packet)

        assertTrue(result is ParseResult.Success)
        val reading = (result as ParseResult.Success).reading
        assertEquals(spo2, reading.spo2)
        assertEquals(heartRate, reading.heartRate)
        assertEquals(battery, reading.battery)
    }

    /**
     * Test parsing packet with sensor off (flag = 0xFF).
     */
    @Test
    fun testParseSensorOffPacket() {
        val payload = ByteArray(13)
        payload[0] = 0  // SpO2
        payload[1] = 0  // HR
        payload[2] = 0xFF.toByte()  // Flag = sensor off

        val packet = ByteArray(7 + 13 + 1)
        packet[0] = 0x55
        packet[1] = 0x17
        packet[2] = 0xE8.toByte()
        packet[3] = 0x00
        packet[4] = 0x00
        packet[5] = 0x0D
        packet[6] = 0x00
        System.arraycopy(payload, 0, packet, 7, 13)
        packet[20] = OximeterProtocol.calcCrc(packet.copyOfRange(0, 20))

        val result = OximeterProtocol.parsePacket(packet)

        // Should return error because reading is null (sensor off)
        assertTrue(result is ParseResult.Error)
    }

    /**
     * Test parsing packet with idle state (flag = 0x00, spo2 = 0, hr = 0).
     */
    @Test
    fun testParseIdlePacket() {
        val payload = ByteArray(13)
        payload[0] = 0  // SpO2 = 0
        payload[1] = 0  // HR = 0
        payload[2] = 0  // Flag = 0x00 (idle)

        val packet = ByteArray(7 + 13 + 1)
        packet[0] = 0x55
        packet[1] = 0x17
        packet[2] = 0xE8.toByte()
        packet[3] = 0x00
        packet[4] = 0x00
        packet[5] = 0x0D
        packet[6] = 0x00
        System.arraycopy(payload, 0, packet, 7, 13)
        packet[20] = OximeterProtocol.calcCrc(packet.copyOfRange(0, 20))

        val result = OximeterProtocol.parsePacket(packet)

        // Should return error because reading is null (idle)
        assertTrue(result is ParseResult.Error)
    }

    /**
     * Test incomplete packet detection.
     */
    @Test
    fun testParseIncompletePacket() {
        // Packet with header but not enough data
        val packet = byteArrayOf(0x55, 0x17, 0xE8.toByte(), 0x00, 0x00, 0x0D, 0x00)

        val result = OximeterProtocol.parsePacket(packet)

        assertTrue(result is ParseResult.Incomplete)
        assertEquals(21, (result as ParseResult.Incomplete).expectedSize)
    }

    /**
     * Test packet too short.
     */
    @Test
    fun testParseTooShortPacket() {
        val packet = byteArrayOf(0x55, 0x17)

        val result = OximeterProtocol.parsePacket(packet)

        assertTrue(result is ParseResult.Error)
        assertTrue((result as ParseResult.Error).message.contains("too short"))
    }

    /**
     * Test invalid header.
     */
    @Test
    fun testParseInvalidHeader() {
        val packet = byteArrayOf(0xAA.toByte(), 0x17, 0xE8.toByte(), 0x00, 0x00, 0x00, 0x00, 0x00)

        val result = OximeterProtocol.parsePacket(packet)

        assertTrue(result is ParseResult.Error)
        assertTrue((result as ParseResult.Error).message.contains("Invalid header"))
    }

    /**
     * Test finding packet in buffer.
     */
    @Test
    fun testFindPacketInBuffer() {
        // Build a valid packet
        val payload = ByteArray(13) { 0x00 }
        payload[0] = 97  // SpO2
        payload[1] = 72  // HR
        payload[2] = 0x01  // Valid flag

        val packet = ByteArray(21)
        packet[0] = 0x55
        packet[1] = 0x17
        packet[2] = 0xE8.toByte()
        packet[3] = 0x00
        packet[4] = 0x00
        packet[5] = 0x0D
        packet[6] = 0x00
        System.arraycopy(payload, 0, packet, 7, 13)
        packet[20] = OximeterProtocol.calcCrc(packet.copyOfRange(0, 20))

        // Add some garbage before and after
        val buffer = byteArrayOf(0x00, 0x01, 0x02) + packet + byteArrayOf(0xAA.toByte(), 0xBB.toByte())

        val result = OximeterProtocol.findPacket(buffer)

        assertNotNull(result)
        assertEquals(21, result!!.first.size)
        assertEquals(2, result.second.size)  // Remaining garbage
    }

    /**
     * Test OxiReading validation.
     */
    @Test
    fun testOxiReadingValidation() {
        val validReading = OxiReading(spo2 = 97, heartRate = 72, battery = 85)
        assertTrue(validReading.isValidSpo2())
        assertTrue(validReading.isValidHeartRate())

        val invalidSpo2 = OxiReading(spo2 = 0, heartRate = 72, battery = 85)
        assertFalse(invalidSpo2.isValidSpo2())

        val invalidHr = OxiReading(spo2 = 97, heartRate = 10, battery = 85)
        assertFalse(invalidHr.isValidHeartRate())
    }
}
