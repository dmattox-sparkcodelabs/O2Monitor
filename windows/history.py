# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Parsing for Viatom/Wellue stored recording files (.vld v3 format).

The Checkme O2 device saves completed monitoring sessions in onboard flash.
Each saved file has:

  - 40-byte header with creation timestamp, summary stats, and recording
    duration / size.
  - N records of 5 bytes each: (spo2, heart_rate, oximetry_invalid, motion,
    vibration). Sample resolution is either 2 or 4 seconds — computed from
    `duration / record_count`.

Cross-checked against ericm301/O2Ring-DataFetcher's o2file.py.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator


log = logging.getLogger(__name__)

RECORD_SIZE_V3 = 5
HEADER_SIZE = 40

# 26-byte fixed header layout (the remaining 14 bytes are padding)
#   version  H  (file format version)
#   year     H  (full year, e.g. 2026)
#   month    B
#   day      B
#   hour     B
#   minute   B
#   second   B
#   filesize  H
#   filesize2 H
#   duration  H  (seconds)
#   duration2 H
#   spo2_avg  B
#   spo2_min  B
#   spo2_3pct B  (events with >=3% drop)
#   spo2_4pct B  (events with >=4% drop)
#   unknown1  B
#   time_under_90pct  H  (seconds below 90%)
#   events_under_90pct B
#   o2_score  B
_HEADER_STRUCT = "<HHBBBBBHHHHBBBBBHBB"


@dataclass
class VldHeader:
    version: int
    start: datetime
    duration_seconds: int
    record_count: int
    resolution_seconds: float
    spo2_avg: int
    spo2_min: int
    time_under_90pct_seconds: int
    events_under_90pct: int


@dataclass
class VldRecord:
    timestamp: datetime
    spo2: int
    heart_rate: int
    motion: int
    is_valid: bool


def parse_vld_v3(blob: bytes) -> tuple[VldHeader, Iterator[VldRecord]]:
    """Parse a .vld v3 file blob.

    Returns the header and a generator yielding one VldRecord per sample.
    The generator is lazy so we can stream into the DB without loading
    every sample into memory at once.

    Raises ValueError on malformed input.
    """
    if len(blob) < HEADER_SIZE:
        raise ValueError(f"file too short: {len(blob)} bytes")

    raw = blob[:26]
    fields = struct.unpack(_HEADER_STRUCT, raw)
    (version, year, month, day, hour, minute, second,
     filesize, _filesize2, duration, _duration2,
     spo2_avg, spo2_min, _spo2_3pct, _spo2_4pct, _unknown1,
     time_under_90, events_under_90, _o2_score) = fields

    if version != 3:
        raise ValueError(f"unsupported file version: {version}")

    try:
        start = datetime(year, month, day, hour, minute, second)
    except ValueError as e:
        raise ValueError(f"invalid header timestamp: {e}")

    data_len = len(blob) - HEADER_SIZE
    record_count = data_len // RECORD_SIZE_V3
    if record_count <= 0:
        raise ValueError("file contains no records")

    if duration <= 0:
        # Some files have duration=0 if the session was incomplete; fall
        # back to assuming 4s resolution which is the most common default.
        resolution = 4.0
        log.warning("file has zero duration, assuming 4s resolution")
    else:
        resolution = duration / record_count
        # The device only writes at 2.0s or 4.0s; round to nearest if close
        if abs(resolution - 2.0) < 0.1:
            resolution = 2.0
        elif abs(resolution - 4.0) < 0.1:
            resolution = 4.0
        else:
            log.warning(
                "unexpected resolution %.3fs (duration=%d, records=%d)",
                resolution, duration, record_count,
            )

    header = VldHeader(
        version=version,
        start=start,
        duration_seconds=duration,
        record_count=record_count,
        resolution_seconds=resolution,
        spo2_avg=spo2_avg,
        spo2_min=spo2_min,
        time_under_90pct_seconds=time_under_90,
        events_under_90pct=events_under_90,
    )

    def _records() -> Iterator[VldRecord]:
        offset = HEADER_SIZE
        for i in range(record_count):
            chunk = blob[offset:offset + RECORD_SIZE_V3]
            offset += RECORD_SIZE_V3
            if len(chunk) < RECORD_SIZE_V3:
                break
            spo2, hr, invalid_flag, motion, _vibration = struct.unpack("<BBBBB", chunk)
            # The reference treats spo2 < 10 or > 100 as invalid, in addition
            # to the device's invalid flag.
            is_valid = invalid_flag == 0 and 10 <= spo2 <= 100
            ts = start + timedelta(seconds=i * resolution)
            yield VldRecord(
                timestamp=ts,
                spo2=spo2,
                heart_rate=hr,
                motion=motion,
                is_valid=is_valid,
            )

    return header, _records()


def parse_filelist(filelist_field: str) -> list[str]:
    """Split the comma-separated FileList JSON field into clean filenames."""
    return [name for name in filelist_field.split(",") if name]
