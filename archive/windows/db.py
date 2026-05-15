# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""SQLite store for baseline oximetry data.

Schema:
    readings(id, timestamp, spo2, heart_rate, battery_level, movement, night_date)

Night labeling: each reading is tagged with the date you wake up. A reading
at 23:30 on May 14 and a reading at 03:00 on May 15 both belong to night
'2025-05-15'. The rule is `night_date = date(timestamp + 12 hours)`.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL UNIQUE,
    spo2 INTEGER NOT NULL,
    heart_rate INTEGER NOT NULL,
    battery_level INTEGER NOT NULL,
    movement INTEGER NOT NULL,
    night_date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'live'
);

CREATE INDEX IF NOT EXISTS idx_readings_night ON readings(night_date, timestamp);
CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp);

CREATE TABLE IF NOT EXISTS history_files (
    filename TEXT PRIMARY KEY,
    downloaded_at TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    record_count INTEGER NOT NULL
);
"""


def night_date_for(ts: datetime) -> str:
    """Return ISO date (YYYY-MM-DD) of the wake morning for a given reading time."""
    return (ts + timedelta(hours=12)).date().isoformat()


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def insert_reading(
    conn: sqlite3.Connection,
    timestamp: datetime,
    spo2: int,
    heart_rate: int,
    battery_level: int,
    movement: int,
    source: str = "live",
) -> bool:
    """Insert a reading. Returns True if inserted, False if duplicate timestamp."""
    try:
        conn.execute(
            "INSERT INTO readings (timestamp, spo2, heart_rate, battery_level, movement, night_date, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                timestamp.isoformat(timespec="seconds"),
                spo2,
                heart_rate,
                battery_level,
                movement,
                night_date_for(timestamp),
                source,
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def insert_readings_batch(
    conn: sqlite3.Connection,
    rows: list[tuple[datetime, int, int, int, int]],
    source: str,
) -> int:
    """Bulk-insert backfill readings. Returns count of new rows."""
    cur = conn.cursor()
    inserted = 0
    for ts, spo2, hr, battery, motion in rows:
        try:
            cur.execute(
                "INSERT INTO readings (timestamp, spo2, heart_rate, battery_level, movement, night_date, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    ts.isoformat(timespec="seconds"),
                    spo2, hr, battery, motion,
                    night_date_for(ts),
                    source,
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return inserted


def downloaded_filenames(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT filename FROM history_files").fetchall()
    return {r["filename"] for r in rows}


def mark_file_downloaded(
    conn: sqlite3.Connection,
    filename: str,
    bytes_count: int,
    record_count: int,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO history_files (filename, downloaded_at, bytes, record_count) "
        "VALUES (?, ?, ?, ?)",
        (filename, datetime.now().isoformat(timespec="seconds"), bytes_count, record_count),
    )
    conn.commit()


def list_nights(conn: sqlite3.Connection) -> list[dict]:
    """Return one row per night with reading count and time bounds."""
    rows = conn.execute(
        """
        SELECT
            night_date,
            COUNT(*) AS reading_count,
            MIN(timestamp) AS first_reading,
            MAX(timestamp) AS last_reading
        FROM readings
        GROUP BY night_date
        ORDER BY night_date DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_night_readings(conn: sqlite3.Connection, night_date: str) -> list[dict]:
    rows = conn.execute(
        "SELECT timestamp, spo2, heart_rate, battery_level, movement "
        "FROM readings WHERE night_date = ? ORDER BY timestamp",
        (night_date,),
    ).fetchall()
    return [dict(r) for r in rows]
