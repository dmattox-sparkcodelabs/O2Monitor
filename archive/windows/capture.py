# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Continuous BLE capture for Checkme O2 Max on Windows.

Each session:
  1. Connect, subscribe to notifications.
  2. Set device clock (it drifts/ships wrong; backfilled timestamps depend on
     this being right).
  3. Fetch device info. If new recording files exist, download and ingest
     them so we recover any data missed during a disconnect.
  4. Live-poll the sensor every READ_INTERVAL_S, write readings to SQLite.
  5. If no reading arrives for READING_STALE_THRESHOLD_S seconds, force a
     reconnect — protects against the "connected but silent" failure mode.

Usage:
    python -m windows.capture
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from windows import db, history
from windows.session import O2Session, ProtocolError


READ_INTERVAL_S = 15.0
# Force a reconnect if no reading arrives in this many seconds. The Pi's
# BLE_GATT setup would hang silently after hours; the watchdog catches the
# "connected but no data" failure mode.
READING_STALE_THRESHOLD_S = READ_INTERVAL_S * 4
RECONNECT_DELAY_S = 10.0
SCAN_TIMEOUT_S = 15.0
DEVICE_NAME_HINTS = ("O2", "Checkme", "Viatom", "Wellue")
# Allow generous time for downloading large overnight recordings
FILE_BLOCK_TIMEOUT_S = 15.0
FILE_TOTAL_TIMEOUT_S = 600.0

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "o2_baseline.db"
CONFIG_PATH = PROJECT_ROOT / "o2_baseline.config.json"
LOG_PATH = PROJECT_ROOT / "capture.log"


def _setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("capture")


log = _setup_logging()


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


async def _discover_mac() -> str:
    log.info("Scanning for Checkme O2 Max (%.0fs)...", SCAN_TIMEOUT_S)
    found = await BleakScanner.discover(timeout=SCAN_TIMEOUT_S, return_adv=True)
    matches = []
    for device, adv in found.values():
        name = (device.name or adv.local_name or "").strip()
        if not name:
            continue
        if any(hint.lower() in name.lower() for hint in DEVICE_NAME_HINTS):
            rssi = adv.rssi
            matches.append((device, rssi))
            log.info("  candidate: %s (%s) RSSI=%s", name, device.address, rssi)

    if not matches:
        log.error("No Checkme/O2 devices found. Make sure the sensor is on a finger and advertising.")
        raise SystemExit(2)

    if len(matches) > 1:
        log.warning("Multiple candidates found; picking strongest RSSI.")
        matches.sort(key=lambda pair: pair[1] if pair[1] is not None else -999, reverse=True)

    chosen, _ = matches[0]
    log.info("Selected device: %s (%s)", chosen.name, chosen.address)
    return chosen.address


async def _sync_history(session: O2Session, info: dict) -> None:
    """Pull any stored recording files we haven't already downloaded."""
    filelist_raw = info.get("FileList", "") or ""
    available = history.parse_filelist(filelist_raw)
    if not available:
        log.info("History sync: device has no stored recordings.")
        return

    with db.connect(DB_PATH) as conn:
        already = db.downloaded_filenames(conn)

    new_files = [f for f in available if f not in already]
    if not new_files:
        log.info(
            "History sync: device has %d files, all already downloaded.",
            len(available),
        )
        return

    log.info(
        "History sync: %d new file(s) to download (of %d on device).",
        len(new_files), len(available),
    )
    for fname in new_files:
        try:
            log.info("Downloading %s ...", fname)
            blob = await session.download_file(
                fname,
                block_timeout=FILE_BLOCK_TIMEOUT_S,
                total_timeout=FILE_TOTAL_TIMEOUT_S,
            )
        except Exception as e:
            log.exception("Failed to download %s: %s", fname, e)
            continue

        try:
            header, records_iter = history.parse_vld_v3(blob)
        except Exception as e:
            log.exception("Failed to parse %s: %s", fname, e)
            continue

        # Build the rows; we don't have battery readings in the .vld so use 0
        rows = []
        for rec in records_iter:
            if not rec.is_valid:
                continue
            rows.append((rec.timestamp, rec.spo2, rec.heart_rate, 0, rec.motion))

        with db.connect(DB_PATH) as conn:
            inserted = db.insert_readings_batch(conn, rows, source="history")
            db.mark_file_downloaded(conn, fname, len(blob), header.record_count)

        log.info(
            "  %s: %d records (%s -> %.0fmin), %d new rows inserted "
            "(avg SpO2 %d, min %d).",
            fname,
            header.record_count,
            header.start.isoformat(timespec="seconds"),
            header.duration_seconds / 60.0,
            inserted,
            header.spo2_avg,
            header.spo2_min,
        )


async def _run_session(mac: str, stop_event: asyncio.Event) -> None:
    """Connect, sync history, then stream live readings until stop_event is set."""
    last_reading_at = time.monotonic()

    log.info("Connecting to %s...", mac)
    async with BleakClient(mac, timeout=30.0) as client:
        session = O2Session(client)
        await session.start()
        log.info("Connected. Subscribing to notifications.")

        # Set device clock so any subsequent recordings have correct timestamps.
        try:
            await session.set_time(datetime.now())
            log.info("Device time synced.")
        except Exception:
            log.exception("Failed to set device time (continuing)")

        # Inspect device info + sync any historical recordings.
        try:
            info = await session.get_info()
            log.info(
                "Device: model=%s sw=%s battery=%s mode=%s",
                info.get("Model"), info.get("SoftwareVer"),
                info.get("CurBAT"), info.get("CurMode"),
            )
            await _sync_history(session, info)
        except Exception:
            log.exception("History sync failed (continuing to live capture)")

        # Reset watchdog clock just before live loop
        last_reading_at = time.monotonic()

        # Live capture loop
        try:
            while not stop_event.is_set():
                try:
                    reading = await session.read_sensors(timeout=READ_INTERVAL_S)
                except asyncio.TimeoutError:
                    log.warning("read_sensors timed out — forcing reconnect")
                    break
                except BleakError as e:
                    log.warning("BLE error during read: %s", e)
                    break
                except ProtocolError as e:
                    log.warning("Protocol error: %s", e)
                    reading = None

                if reading is not None:
                    last_reading_at = time.monotonic()
                    ts = datetime.now()
                    with db.connect(DB_PATH) as conn:
                        inserted = db.insert_reading(
                            conn,
                            timestamp=ts,
                            spo2=reading.spo2,
                            heart_rate=reading.heart_rate,
                            battery_level=reading.battery_level,
                            movement=reading.movement,
                            source="live",
                        )
                    if inserted:
                        log.info(
                            "Reading: SpO2=%d%% HR=%d Battery=%d%%",
                            reading.spo2, reading.heart_rate, reading.battery_level,
                        )

                # Wait until the next polling interval, but exit early if asked to stop
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=READ_INTERVAL_S)
                except asyncio.TimeoutError:
                    pass

                # Watchdog: "connected but silent" — same failure mode the Pi had.
                silence = time.monotonic() - last_reading_at
                if silence > READING_STALE_THRESHOLD_S:
                    log.warning(
                        "No reading in %.0fs (threshold %.0fs) — forcing reconnect",
                        silence, READING_STALE_THRESHOLD_S,
                    )
                    break
        finally:
            await session.stop()
    log.info("Disconnected.")


async def _main() -> None:
    db.init(DB_PATH)
    log.info("Database: %s", DB_PATH)

    cfg = _load_config()
    mac = cfg.get("mac")
    if not mac:
        mac = await _discover_mac()
        cfg["mac"] = mac
        _save_config(cfg)
        log.info("Saved MAC to %s", CONFIG_PATH)
    else:
        log.info("Using saved MAC: %s", mac)

    stop_event = asyncio.Event()

    def _request_stop():
        log.info("Stop requested.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _request_stop)
        loop.add_signal_handler(signal.SIGTERM, _request_stop)
    except NotImplementedError:
        pass

    while not stop_event.is_set():
        try:
            await _run_session(mac, stop_event)
        except BleakError as e:
            log.warning("BLE error: %s", e)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Unexpected error in session")

        if stop_event.is_set():
            break

        log.info("Reconnecting in %.0fs...", RECONNECT_DELAY_S)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RECONNECT_DELAY_S)
        except asyncio.TimeoutError:
            pass

    log.info("Capture stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        log.info("Interrupted.")
