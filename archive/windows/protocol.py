# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Wellue/Viatom Checkme O2 family BLE protocol.

Protocol shape (cross-checked against farolone/wellue-o2ring-protocol and
ericm301/O2Ring-DataFetcher and verified live against a Checkme O2 Max
model 1642):

    Request:  0xAA | cmd | cmd^0xFF | block(LE 2B) | len(LE 2B) | payload | crc
    Response: 0x55 | status | status^0xFF | block(LE 2B) | len(LE 2B) | payload | crc

    status == 0 means success; anything else is a failure code.

CRC is a CRC-8-CCITT variant with polynomial 0x07.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional


# Same UUIDs as the Pi's BLE_GATT code in src/ble_reader.py
RX_UUID = "0734594a-a8e7-4b1a-a6b1-cd5243059a57"  # device → host notifications
TX_UUID = "8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3"  # host → device writes

# Command codes
CMD_FILE_OPEN = 0x03
CMD_FILE_READ = 0x04
CMD_FILE_CLOSE = 0x05
CMD_INFO = 0x14
CMD_CONFIG = 0x16
CMD_READ_SENSORS = 0x17

# Time format the device's JSON config uses (date and time are comma-separated)
DEVICE_TIME_FORMAT = "%Y-%m-%d,%H:%M:%S"


@dataclass
class OxiReading:
    spo2: int
    heart_rate: int
    battery_level: int
    movement: int


@dataclass
class Packet:
    """Parsed response packet. `status` is 0 on success."""
    status: int
    block: int
    payload: bytes


def calc_crc(data: bytes) -> int:
    """CRC-8 variant used by the Checkme protocol."""
    crc = 0x00
    for b in data:
        chk = (crc ^ b) & 0xFF
        crc = 0x00
        if chk & 0x01: crc ^= 0x07
        if chk & 0x02: crc ^= 0x0e
        if chk & 0x04: crc ^= 0x1c
        if chk & 0x08: crc ^= 0x38
        if chk & 0x10: crc ^= 0x70
        if chk & 0x20: crc ^= 0xe0
        if chk & 0x40: crc ^= 0xc7
        if chk & 0x80: crc ^= 0x89
    return crc


def build_packet(cmd: int, block: int = 0, payload: bytes = b"") -> bytes:
    """Build a request packet ready to write to the TX characteristic."""
    header = struct.pack("<BBBHH", 0xAA, cmd, cmd ^ 0xFF, block, len(payload))
    body = header + payload
    return body + bytes([calc_crc(body)])


def build_command(cmd: int) -> bytes:
    """Backwards-compatible empty-payload command builder."""
    return build_packet(cmd)


class PacketParser:
    """Stateful parser that yields complete Packets as bytes arrive.

    Notifications arrive in chunks; a single response packet may span multiple
    notifications. The parser maintains a buffer and emits a Packet only when
    a full one is present.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Packet]:
        self._buf.extend(data)
        out: list[Packet] = []
        while True:
            # Drop leading bytes until we hit a 0x55 start marker
            while self._buf and self._buf[0] != 0x55:
                del self._buf[0]
            if len(self._buf) < 8:
                break
            status = self._buf[1]
            ncmd = self._buf[2]
            # Consistency check: status ^ 0xFF must equal ncmd
            if (status ^ 0xFF) != ncmd:
                # Out of sync; drop the start byte and resync
                del self._buf[0]
                continue
            block = self._buf[3] | (self._buf[4] << 8)
            pay_len = self._buf[5] | (self._buf[6] << 8)
            total = pay_len + 8
            if len(self._buf) < total:
                break
            packet = bytes(self._buf[:total])
            del self._buf[:total]
            if calc_crc(packet[:-1]) != packet[-1]:
                # bad CRC, drop and keep looking
                continue
            out.append(Packet(status=status, block=block, payload=packet[7:-1]))
        return out


def parse_oxi_reading(payload: bytes) -> Optional[OxiReading]:
    """Parse a CMD_READ_SENSORS response payload into an OxiReading."""
    if len(payload) < 10:
        return None
    spo2 = payload[0]
    hr = payload[1]
    flag = payload[2]
    battery = payload[7]
    movement = payload[9]
    if flag == 0xFF:
        return None  # sensor off
    if flag == 0x00 and spo2 == 0 and hr == 0:
        return None  # sensor idle
    return OxiReading(
        spo2=spo2, heart_rate=hr, battery_level=battery, movement=movement,
    )
