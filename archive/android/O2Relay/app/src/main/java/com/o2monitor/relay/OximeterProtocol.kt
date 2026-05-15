package com.o2monitor.relay

import java.time.Instant

/**
 * Viatom/Wellue Checkme O2 Max BLE protocol implementation.
 *
 * Protocol details from Pi implementation (src/ble_reader.py) and DESIGN.md:
 * - TX characteristic: 8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3 (send commands)
 * - RX characteristic: 0734594a-a8e7-4b1a-a6b1-cd5243059a57 (receive notifications)
 * - Command 0x17: Request current sensor values
 */
object OximeterProtocol {

    // BLE UUIDs
    const val SERVICE_UUID = "14839ac4-7d7e-415c-9a42-167340cf2339"
    const val TX_CHAR_UUID = "8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3"
    const val RX_CHAR_UUID = "0734594a-a8e7-4b1a-a6b1-cd5243059a57"

    // Protocol constants
    private const val CMD_HEADER: Byte = 0xAA.toByte()
    private const val RESPONSE_HEADER: Byte = 0x55
    private const val CMD_REQUEST_READING: Byte = 0x17

    // Validity flags
    private const val FLAG_SENSOR_OFF: Byte = 0xFF.toByte()

    /**
     * Calculate CRC-8 for Viatom protocol.
     * Matches Python implementation in src/ble_reader.py
     */
    fun calcCrc(data: ByteArray): Byte {
        var crc = 0x00
        for (b in data) {
            var chk = (crc xor (b.toInt() and 0xFF)) and 0xFF
            crc = 0x00
            if (chk and 0x01 != 0) crc = crc xor 0x07
            if (chk and 0x02 != 0) crc = crc xor 0x0e
            if (chk and 0x04 != 0) crc = crc xor 0x1c
            if (chk and 0x08 != 0) crc = crc xor 0x38
            if (chk and 0x10 != 0) crc = crc xor 0x70
            if (chk and 0x20 != 0) crc = crc xor 0xe0
            if (chk and 0x40 != 0) crc = crc xor 0xc7
            if (chk and 0x80 != 0) crc = crc xor 0x89
        }
        return crc.toByte()
    }

    /**
     * Build command packet to request sensor reading (command 0x17).
     *
     * Packet format:
     * - Byte 0: 0xAA (header)
     * - Byte 1: Command code (0x17)
     * - Byte 2: Command complement (0xFF ^ cmd)
     * - Bytes 3-6: 0x00 (padding/block ID/length)
     * - Byte 7: CRC
     */
    fun buildReadingCommand(): ByteArray {
        val cmd = CMD_REQUEST_READING
        val packet = ByteArray(8)
        packet[0] = CMD_HEADER
        packet[1] = cmd
        packet[2] = (0xFF xor cmd.toInt()).toByte()
        packet[3] = 0x00
        packet[4] = 0x00
        packet[5] = 0x00
        packet[6] = 0x00

        // Calculate CRC over bytes 0-6
        packet[7] = calcCrc(packet.copyOfRange(0, 7))

        return packet
    }

    /**
     * Parse a response packet from the oximeter.
     *
     * Response format:
     * - Byte 0: 0x55 (header)
     * - Byte 1: Response type
     * - Byte 2: Response complement
     * - Bytes 3-4: Block ID
     * - Bytes 5-6: Payload length (little-endian)
     * - Bytes 7+: Payload data
     * - Last byte: CRC
     *
     * @return ParseResult with the reading, or error information
     */
    fun parsePacket(data: ByteArray): ParseResult {
        // Need at least 7 bytes to read header and payload length
        if (data.size < 7) {
            return ParseResult.Error("Packet too short: ${data.size} bytes")
        }

        // Check header
        if (data[0] != RESPONSE_HEADER) {
            return ParseResult.Error("Invalid header: 0x${data[0].toHexString()}")
        }

        // Get payload length (little-endian, bytes 5-6)
        val payloadLength = (data[5].toInt() and 0xFF) or ((data[6].toInt() and 0xFF) shl 8)

        // Check total packet size
        val expectedSize = 7 + payloadLength + 1  // header + payload + CRC
        if (data.size < expectedSize) {
            return ParseResult.Incomplete(expectedSize)
        }

        // Verify CRC (over all bytes except the last one)
        val packetWithoutCrc = data.copyOfRange(0, expectedSize - 1)
        val expectedCrc = calcCrc(packetWithoutCrc)
        val actualCrc = data[expectedSize - 1]
        if (expectedCrc != actualCrc) {
            return ParseResult.Error("CRC mismatch: expected 0x${expectedCrc.toHexString()}, got 0x${actualCrc.toHexString()}")
        }

        // Extract payload
        val payload = data.copyOfRange(7, 7 + payloadLength)

        // Parse reading from payload (if it's a sensor reading response)
        return if (payloadLength == 13) {
            parseReading(payload)?.let { ParseResult.Success(it) }
                ?: ParseResult.Error("Failed to parse reading from payload")
        } else {
            ParseResult.Error("Unexpected payload length: $payloadLength (expected 13 for sensor reading)")
        }
    }

    /**
     * Parse sensor reading from 13-byte payload.
     *
     * Payload format:
     * - Byte 0: SpO2 (0-100)
     * - Byte 1: Heart Rate (BPM)
     * - Byte 2: Status flag (0xFF = sensor off, 0x00 with zeros = idle)
     * - Bytes 3-6: Reserved
     * - Byte 7: Battery (0-100)
     * - Byte 8: Reserved
     * - Byte 9: Movement indicator
     * - Bytes 10-12: Reserved
     *
     * @return OxiReading if valid, null if sensor off or idle
     */
    fun parseReading(payload: ByteArray): OxiReading? {
        if (payload.size < 13) {
            return null
        }

        val spo2 = payload[0].toInt() and 0xFF
        val heartRate = payload[1].toInt() and 0xFF
        val flag = payload[2]
        val battery = payload[7].toInt() and 0xFF
        val movement = payload[9].toInt() and 0xFF

        // Check validity
        // Skip if sensor off (flag == 0xFF)
        if (flag == FLAG_SENSOR_OFF) {
            return null
        }

        // Skip if idle (flag == 0x00 && spo2 == 0 && hr == 0)
        if (flag == 0.toByte() && spo2 == 0 && heartRate == 0) {
            return null
        }

        return OxiReading(
            spo2 = spo2,
            heartRate = heartRate,
            battery = battery,
            movement = movement,
            timestamp = Instant.now()
        )
    }

    /**
     * Find a complete packet in a data buffer.
     * Returns the packet and remaining data, or null if no complete packet found.
     */
    fun findPacket(buffer: ByteArray): Pair<ByteArray, ByteArray>? {
        // Look for response header (0x55)
        val headerIndex = buffer.indexOf(RESPONSE_HEADER)
        if (headerIndex < 0) {
            return null
        }

        // Need at least 8 bytes from header to parse length
        if (buffer.size - headerIndex < 8) {
            return null
        }

        // Get payload length
        val payloadLength = (buffer[headerIndex + 5].toInt() and 0xFF) or
                ((buffer[headerIndex + 6].toInt() and 0xFF) shl 8)

        val packetSize = 7 + payloadLength + 1  // header + payload + CRC

        // Check if we have complete packet
        if (buffer.size - headerIndex < packetSize) {
            return null
        }

        // Extract packet and remaining buffer
        val packet = buffer.copyOfRange(headerIndex, headerIndex + packetSize)
        val remaining = buffer.copyOfRange(headerIndex + packetSize, buffer.size)

        return Pair(packet, remaining)
    }

    // Extension function for hex formatting
    private fun Byte.toHexString(): String = String.format("%02X", this)
}

/**
 * Result of parsing a packet.
 */
sealed class ParseResult {
    data class Success(val reading: OxiReading) : ParseResult()
    data class Incomplete(val expectedSize: Int) : ParseResult()
    data class Error(val message: String) : ParseResult()
}

/**
 * Oximeter reading data.
 */
data class OxiReading(
    val spo2: Int,
    val heartRate: Int,
    val battery: Int,
    val movement: Int = 0,
    val timestamp: Instant = Instant.now()
) {
    /**
     * Check if SpO2 value is in valid range.
     */
    fun isValidSpo2(): Boolean = spo2 in 1..100

    /**
     * Check if heart rate is in valid range.
     */
    fun isValidHeartRate(): Boolean = heartRate in 20..250
}
