# Windows O2 Baseline Capture

Standalone capture + viewer for the Checkme O2 Max pulse oximeter, running
on Windows via [bleak](https://github.com/hbldh/bleak). Separate from the
Pi-based monitoring in `src/` — different sensor, different database, no
shared state.

> **Not a medical device.** This is for personal awareness only. Discuss
> the data with your clinician — don't make therapy decisions from it.

## What it does

- **`capture.py`** — Continuous BLE capture. Scans for the sensor on first
  run, saves the MAC, then reads every 5 seconds and writes to SQLite.
  Reconnects on disconnect.
- **`viewer.py`** — Simple Flask app at `http://localhost:5050`. Pick a
  night, see the SpO2 trend and the clinical readouts (mean/min SpO2,
  time below 88/90%, ODI3, ODI4).

A "night" runs noon-to-noon and is labeled by the wake morning (so
readings from May 14 evening + May 15 morning both belong to night
`2025-05-15`).

## First-time setup

From the project root:

```powershell
.\start-capture.ps1
```

On first run this creates a venv at `windows\.venv`, installs `bleak` and
`flask`, then starts scanning for the sensor. Have the sensor on your
finger (so it's advertising) when you launch.

After scan completes it saves the MAC to `windows\o2_baseline.config.json`
and starts capturing. Subsequent runs skip the scan.

## Running

```powershell
.\start-capture.ps1   # capture loop (leave running)
.\start-viewer.ps1    # in a separate terminal; opens at localhost:5050
```

Stop capture with Ctrl+C. The DB is flushed after each reading, so killing
the process won't lose data.

## Files

| Path | Purpose |
|---|---|
| `windows\protocol.py` | Checkme command/packet protocol (CRC, parsers) |
| `windows\db.py` | SQLite schema, insert, queries |
| `windows\stats.py` | Mean/min SpO2, time below thresholds, ODI3/ODI4 |
| `windows\capture.py` | bleak loop |
| `windows\viewer.py` | Flask viewer |
| `windows\templates\index.html` | Single-page UI |
| `windows\static\viewer.js` | Chart.js rendering |
| `windows\o2_baseline.db` | SQLite store (gitignored) |
| `windows\o2_baseline.config.json` | Saved sensor MAC (gitignored) |
| `windows\capture.log` | Capture log (gitignored) |

## Clinical metric definitions

- **Mean / Min / Max SpO2** — across all valid samples (50–100% range).
- **Time below 88% / 90%** — integrated below-threshold time, with gaps
  capped at 30s to avoid attributing disconnects.
- **ODI3 / ODI4** — events per hour where SpO2 drops 3 / 4 percentage
  points from a 100-second rolling baseline, sustained ≥10 seconds.
  Approximates the AASM definition; real sleep-lab software uses
  additional signal smoothing and artifact rejection.

If the numbers look off, check `windows\capture.log` for disconnect
events. Long gaps between readings will skew "time below" downward
(capped) and may miss desat events.
