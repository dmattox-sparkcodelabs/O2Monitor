package com.o2monitor.app.ble

data class OxiReading(
    val spo2: Int,
    val heartRate: Int,
    val batteryLevel: Int,
    val movement: Int
)

data class Packet(
    val status: Int,
    val block: Int,
    val payload: ByteArray
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is Packet) return false
        return status == other.status && block == other.block && payload.contentEquals(other.payload)
    }

    override fun hashCode(): Int {
        var result = status
        result = 31 * result + block
        result = 31 * result + payload.contentHashCode()
        return result
    }
}

object BleProtocol {
    const val RX_UUID = "0734594a-a8e7-4b1a-a6b1-cd5243059a57"
    const val TX_UUID = "8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3"
    const val CMD_READ_SENSORS: Byte = 0x17.toByte()

    /**
     * CRC-8 variant used by the Checkme protocol.
     * Exact port of Python calc_crc() — polynomial 0x07.
     * Use & 0xFF throughout to avoid Kotlin signed-byte sign extension.
     */
    fun calcCrc(data: ByteArray): Byte {
        var crc = 0x00
        for (b in data) {
            val chk = (crc xor (b.toInt() and 0xFF)) and 0xFF
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
     * Build an empty-payload command packet ready to write to the TX characteristic.
     *
     * Packet layout (8 bytes for empty payload):
     *   [0]    0xAA  — start marker
     *   [1]    cmd
     *   [2]    cmd ^ 0xFF  — negate byte
     *   [3–4]  block as LE uint16 (0, 0)
     *   [5–6]  payload length as LE uint16 (0, 0)
     *   [7]    CRC of bytes [0..6]
     */
    fun buildCommand(cmd: Byte): ByteArray {
        val cmdInt = cmd.toInt() and 0xFF
        val header = byteArrayOf(
            0xAA.toByte(),
            cmd,
            (cmdInt xor 0xFF).toByte(),
            0x00, 0x00,  // block LE uint16
            0x00, 0x00   // payload length LE uint16
        )
        val crc = calcCrc(header)
        return header + byteArrayOf(crc)
    }

    /**
     * Parse a CMD_READ_SENSORS response payload into an OxiReading.
     *
     * Payload layout (minimum 10 bytes):
     *   [0]  SpO2
     *   [1]  heart rate
     *   [2]  flag — 0xFF = sensor off, 0x00 with spo2=0/hr=0 = idle
     *   [7]  battery level
     *   [9]  movement
     *
     * Returns null for sensor-off, idle, or undersized payload.
     */
    fun parseReading(payload: ByteArray): OxiReading? {
        if (payload.size < 10) return null
        val spo2 = payload[0].toInt() and 0xFF
        val hr = payload[1].toInt() and 0xFF
        val flag = payload[2].toInt() and 0xFF
        val battery = payload[7].toInt() and 0xFF
        val movement = payload[9].toInt() and 0xFF
        if (flag == 0xFF) return null          // sensor off
        if (flag == 0x00 && spo2 == 0 && hr == 0) return null  // sensor idle
        return OxiReading(
            spo2 = spo2,
            heartRate = hr,
            batteryLevel = battery,
            movement = movement
        )
    }
}

/**
 * Stateful parser that accumulates BLE notification bytes and emits complete Packets.
 *
 * Response packet layout:
 *   [0]    0x55  — start marker
 *   [1]    status (0 = success)
 *   [2]    status ^ 0xFF  — consistency byte
 *   [3–4]  block as LE uint16
 *   [5–6]  payload length as LE uint16
 *   [7..7+pay_len-1]  payload
 *   [-1]   CRC of all bytes except the last
 *
 * Exact port of Python PacketParser.feed().
 */
class PacketParser {
    private val buf = mutableListOf<Byte>()

    fun feed(data: ByteArray): List<Packet> {
        buf.addAll(data.asList())
        val out = mutableListOf<Packet>()
        while (true) {
            // Drop leading bytes until we find the 0x55 start marker.
            while (buf.isNotEmpty() && (buf[0].toInt() and 0xFF) != 0x55) {
                buf.removeAt(0)
            }
            if (buf.size < 8) break

            val status = buf[1].toInt() and 0xFF
            val ncmd = buf[2].toInt() and 0xFF
            // Consistency check: status ^ 0xFF must equal ncmd.
            if ((status xor 0xFF) != ncmd) {
                // Out of sync — drop the start byte and resync.
                buf.removeAt(0)
                continue
            }

            val block = (buf[3].toInt() and 0xFF) or ((buf[4].toInt() and 0xFF) shl 8)
            val payLen = (buf[5].toInt() and 0xFF) or ((buf[6].toInt() and 0xFF) shl 8)
            val total = payLen + 8

            if (buf.size < total) break

            val packet = ByteArray(total) { buf[it] }
            repeat(total) { buf.removeAt(0) }

            if (BleProtocol.calcCrc(packet.copyOfRange(0, total - 1)) != packet[total - 1]) {
                // Bad CRC — drop this packet and keep looking.
                continue
            }

            out.add(Packet(
                status = status,
                block = block,
                payload = packet.copyOfRange(7, total - 1)
            ))
        }
        return out
    }
}
