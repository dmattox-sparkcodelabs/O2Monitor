# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Async request/response wrapper around a single BleakClient connection.

The Checkme O2 protocol is strictly request/response: we write a command,
the device responds with one or more BLE notifications that together form
a single response packet. This module owns the notification subscription
and exposes high-level coroutines (`get_info`, `set_time`, `download_file`,
`read_sensors`) so capture and history-sync code don't have to deal with
packet framing directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from datetime import datetime
from typing import Callable, Optional

from bleak import BleakClient

from windows.protocol import (
    CMD_CONFIG,
    CMD_FILE_CLOSE,
    CMD_FILE_OPEN,
    CMD_FILE_READ,
    CMD_INFO,
    CMD_READ_SENSORS,
    DEVICE_TIME_FORMAT,
    RX_UUID,
    TX_UUID,
    OxiReading,
    Packet,
    PacketParser,
    build_packet,
    parse_oxi_reading,
)


log = logging.getLogger(__name__)


class ProtocolError(RuntimeError):
    """Raised when the device returns a non-zero status byte."""


class O2Session:
    """Owns the BLE notification subscription and a packet inbox.

    Use as:
        async with BleakClient(mac) as client:
            session = O2Session(client)
            await session.start()
            info = await session.get_info()
            ...

    The session does NOT own the BleakClient — caller controls connection
    lifecycle. The session expects to be the sole consumer of notifications
    on RX_UUID.
    """

    def __init__(self, client: BleakClient) -> None:
        self.client = client
        self._parser = PacketParser()
        self._inbox: asyncio.Queue[Packet] = asyncio.Queue()
        # Optional callback for unsolicited live readings (notification path
        # for CMD_READ_SENSORS responses still flows through _inbox; this hook
        # is only used if the caller wants to bypass request/response and
        # consume readings as a stream — currently unused).
        self.on_packet: Optional[Callable[[Packet], None]] = None

    def _on_notify(self, _sender, data: bytearray) -> None:
        for pkt in self._parser.feed(bytes(data)):
            if self.on_packet:
                try:
                    self.on_packet(pkt)
                except Exception:
                    log.exception("on_packet callback raised")
            try:
                self._inbox.put_nowait(pkt)
            except asyncio.QueueFull:
                log.warning("Packet inbox full; dropping packet")

    async def start(self) -> None:
        await self.client.start_notify(RX_UUID, self._on_notify)

    async def stop(self) -> None:
        try:
            await self.client.stop_notify(RX_UUID)
        except Exception:
            pass

    def _drain_inbox(self) -> None:
        while not self._inbox.empty():
            try:
                self._inbox.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _request(
        self,
        cmd: int,
        block: int = 0,
        payload: bytes = b"",
        timeout: float = 10.0,
        drain: bool = True,
    ) -> Packet:
        """Send a command and await the next response packet."""
        if drain:
            self._drain_inbox()
        await self.client.write_gatt_char(TX_UUID, build_packet(cmd, block, payload), response=False)
        return await asyncio.wait_for(self._inbox.get(), timeout=timeout)

    # ---- High-level operations ----

    async def get_info(self, timeout: float = 10.0) -> dict:
        pkt = await self._request(CMD_INFO, timeout=timeout)
        if pkt.status != 0:
            raise ProtocolError(f"INFO failed: status={pkt.status:#x}")
        text = pkt.payload.decode("ascii", errors="replace").rstrip(" \t\r\n\0")
        return json.loads(text)

    async def set_time(self, when: datetime, timeout: float = 5.0) -> None:
        payload = json.dumps(
            {"SetTIME": when.strftime(DEVICE_TIME_FORMAT)}, separators=(",", ":")
        ).encode("ascii")
        pkt = await self._request(CMD_CONFIG, payload=payload, timeout=timeout)
        if pkt.status != 0:
            raise ProtocolError(f"SetTime failed: status={pkt.status:#x}")

    async def read_sensors(self, timeout: float = 5.0) -> Optional[OxiReading]:
        pkt = await self._request(CMD_READ_SENSORS, timeout=timeout)
        if pkt.status != 0:
            log.warning("READ_SENSORS returned status=%#x", pkt.status)
            return None
        return parse_oxi_reading(pkt.payload)

    async def download_file(
        self, filename: str, *, block_timeout: float = 15.0, total_timeout: float = 600.0
    ) -> bytes:
        """Download one stored recording file from the device."""
        deadline = asyncio.get_event_loop().time() + total_timeout

        # Open
        open_pkt = await self._request(
            CMD_FILE_OPEN,
            payload=(filename + "\x00").encode("ascii"),
            timeout=block_timeout,
        )
        if open_pkt.status != 0:
            raise ProtocolError(
                f"FILE_OPEN failed for {filename!r}: status={open_pkt.status:#x}"
            )
        if len(open_pkt.payload) < 4:
            raise ProtocolError(
                f"FILE_OPEN response too short ({len(open_pkt.payload)} bytes)"
            )
        size = struct.unpack("<I", open_pkt.payload[:4])[0]
        log.info("Opened %s (%d bytes)", filename, size)

        # Read blocks
        data = bytearray()
        block = 0
        while len(data) < size:
            if asyncio.get_event_loop().time() > deadline:
                raise ProtocolError(f"Download of {filename!r} exceeded {total_timeout}s")
            read_pkt = await self._request(
                CMD_FILE_READ, block=block, timeout=block_timeout
            )
            if read_pkt.status != 0:
                raise ProtocolError(
                    f"FILE_READ block {block} failed: status={read_pkt.status:#x}"
                )
            if not read_pkt.payload:
                break
            data.extend(read_pkt.payload)
            block += 1

        # Close — always try, even if read errored
        try:
            await self._request(CMD_FILE_CLOSE, timeout=block_timeout)
        except Exception:
            log.exception("FILE_CLOSE failed (continuing)")

        if len(data) < size:
            log.warning(
                "Downloaded %d bytes of %d expected for %s", len(data), size, filename
            )
        return bytes(data[:size])
