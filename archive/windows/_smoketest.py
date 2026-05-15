"""Throwaway smoke test for protocol/history/db wiring."""
import struct
import sys
from datetime import datetime
from pathlib import Path

from windows import db, history, protocol, session, capture  # noqa
print("imports ok")

# Build a valid .vld v3 blob: 40-byte header + 10 records at 4s resolution
header = struct.pack(
    "<HHBBBBBHHHHBBBBBHBB",
    3,                       # version
    2026, 5, 14, 23, 0, 0,   # year, month, day, hour, min, sec
    90, 90,                  # filesize x2 (40 + 50 = 90)
    40, 40,                  # duration x2 (40s @ 4s = 10 records)
    97, 92,                  # spo2_avg, spo2_min
    1, 0,                    # 3pct, 4pct events
    0,                       # unknown
    8,                       # time_under_90
    0, 95,                   # events_under_90, o2_score
)
header += b"\x00" * (40 - len(header))
assert len(header) == 40, len(header)

records = b""
for i in range(10):
    spo2 = 95 if i < 5 else 89
    records += struct.pack("<BBBBB", spo2, 70, 0, 0, 0)  # valid (flag=0)
blob = header + records
assert len(blob) == 90, len(blob)

hdr, recs = history.parse_vld_v3(blob)
recs_list = list(recs)
print(f"hdr: start={hdr.start.isoformat()} duration={hdr.duration_seconds}s "
      f"resolution={hdr.resolution_seconds}s n={hdr.record_count}")
print(f"records parsed: {len(recs_list)}")
for r in recs_list[:3]:
    print(f"  {r.timestamp.isoformat()}  SpO2={r.spo2} HR={r.heart_rate} valid={r.is_valid}")
for r in recs_list[-3:]:
    print(f"  {r.timestamp.isoformat()}  SpO2={r.spo2} HR={r.heart_rate} valid={r.is_valid}")

assert hdr.record_count == 10
assert hdr.resolution_seconds == 4.0
assert all(r.is_valid for r in recs_list)

# DB round-trip
test_db = Path("C:/Users/dmatt/AppData/Local/Temp/smoketest_o2_hist.db")
if test_db.exists():
    test_db.unlink()
db.init(test_db)

rows = [(r.timestamp, r.spo2, r.heart_rate, 0, r.motion) for r in recs_list]
with db.connect(test_db) as conn:
    n = db.insert_readings_batch(conn, rows, source="history")
    print(f"first batch inserted: {n} (expect 10)")
    assert n == 10
    # Re-insert same batch — all should be ignored due to UNIQUE timestamp
    n2 = db.insert_readings_batch(conn, rows, source="history")
    print(f"second batch inserted: {n2} (expect 0)")
    assert n2 == 0
    # Single duplicate insert
    inserted = db.insert_reading(
        conn, timestamp=hdr.start, spo2=99, heart_rate=99,
        battery_level=0, movement=0, source="live",
    )
    print(f"duplicate single insert: {inserted} (expect False)")
    assert inserted is False
    # New timestamp
    new_ts = datetime(2026, 5, 14, 23, 5, 0)
    inserted = db.insert_reading(
        conn, timestamp=new_ts, spo2=98, heart_rate=70,
        battery_level=80, movement=0, source="live",
    )
    print(f"fresh single insert: {inserted} (expect True)")
    assert inserted is True

    db.mark_file_downloaded(conn, "test.vld", len(blob), hdr.record_count)
    downloaded = db.downloaded_filenames(conn)
    print(f"downloaded files: {downloaded}")
    assert "test.vld" in downloaded

test_db.unlink()
print("ALL OK")
