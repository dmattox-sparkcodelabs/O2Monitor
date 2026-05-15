# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Overnight oximetry summary statistics.

Computes the readouts a sleep physician would expect from an overnight
pulse oximetry study:

  - mean / min / max SpO2
  - time below 88% and 90% (the standard clinical thresholds)
  - ODI3, ODI4 (Oxygen Desaturation Index): events per hour where SpO2
    drops 3% / 4% from a 100s rolling baseline, sustained at least 10s

The ODI algorithm here approximates the AASM definition. Real sleep-lab
software uses smoothed signals and additional artifact rejection; this is
a faithful "good enough for visual review" implementation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _valid_readings(readings: Sequence[dict]) -> list[dict]:
    """Filter out zero/sentinel SpO2 frames the device sometimes emits."""
    return [r for r in readings if 50 <= r["spo2"] <= 100]


def summarize(readings: Sequence[dict]) -> dict:
    """Compute summary stats for one night of readings.

    Args:
        readings: ordered list of {timestamp, spo2, heart_rate, ...} dicts.

    Returns:
        Dict of summary stats. All durations are in seconds. Returns zeros
        if the night has no valid readings.
    """
    valid = _valid_readings(readings)
    if not valid:
        return _empty_summary()

    spo2_values = [r["spo2"] for r in valid]
    hr_values = [r["heart_rate"] for r in valid if r["heart_rate"] > 0]

    first_ts = _parse_ts(valid[0]["timestamp"])
    last_ts = _parse_ts(valid[-1]["timestamp"])
    duration_seconds = max(0.0, (last_ts - first_ts).total_seconds())

    time_below_88 = _time_below(valid, 88)
    time_below_90 = _time_below(valid, 90)

    odi3_events = _count_desaturation_events(valid, drop=3)
    odi4_events = _count_desaturation_events(valid, drop=4)

    hours = duration_seconds / 3600.0 if duration_seconds > 0 else 0.0

    return {
        "reading_count": len(valid),
        "duration_seconds": duration_seconds,
        "first_reading": valid[0]["timestamp"],
        "last_reading": valid[-1]["timestamp"],
        "mean_spo2": round(sum(spo2_values) / len(spo2_values), 1),
        "min_spo2": min(spo2_values),
        "max_spo2": max(spo2_values),
        "mean_hr": round(sum(hr_values) / len(hr_values), 1) if hr_values else None,
        "min_hr": min(hr_values) if hr_values else None,
        "max_hr": max(hr_values) if hr_values else None,
        "time_below_88_seconds": time_below_88,
        "time_below_90_seconds": time_below_90,
        "pct_below_88": round(100.0 * time_below_88 / duration_seconds, 1) if duration_seconds else 0.0,
        "pct_below_90": round(100.0 * time_below_90 / duration_seconds, 1) if duration_seconds else 0.0,
        "odi3_events": odi3_events,
        "odi4_events": odi4_events,
        "odi3_per_hour": round(odi3_events / hours, 1) if hours > 0 else 0.0,
        "odi4_per_hour": round(odi4_events / hours, 1) if hours > 0 else 0.0,
    }


def _empty_summary() -> dict:
    return {
        "reading_count": 0,
        "duration_seconds": 0,
        "first_reading": None,
        "last_reading": None,
        "mean_spo2": None,
        "min_spo2": None,
        "max_spo2": None,
        "mean_hr": None,
        "min_hr": None,
        "max_hr": None,
        "time_below_88_seconds": 0,
        "time_below_90_seconds": 0,
        "pct_below_88": 0.0,
        "pct_below_90": 0.0,
        "odi3_events": 0,
        "odi4_events": 0,
        "odi3_per_hour": 0.0,
        "odi4_per_hour": 0.0,
    }


def _time_below(readings: list[dict], threshold: int) -> float:
    """Approximate seconds where SpO2 < threshold, integrating between samples.

    For each consecutive sample pair where both are below the threshold, add
    the gap. For mixed pairs, attribute half the gap. This is a reasonable
    approximation for ~5s sample intervals.
    """
    total = 0.0
    prev_ts: datetime | None = None
    prev_below = False
    for r in readings:
        ts = _parse_ts(r["timestamp"])
        below = r["spo2"] < threshold
        if prev_ts is not None:
            gap = (ts - prev_ts).total_seconds()
            # Cap gap to 30s to avoid attributing huge windows after a disconnect
            gap = min(gap, 30.0)
            if below and prev_below:
                total += gap
            elif below != prev_below:
                total += gap / 2.0
        prev_ts = ts
        prev_below = below
    return total


def _count_desaturation_events(readings: list[dict], *, drop: int) -> int:
    """Approximate AASM-style oxygen desaturation index.

    Event criteria:
      - SpO2 drops by `drop` or more from a 100-second rolling baseline
      - The drop is sustained for at least 10 seconds
      - Event ends when SpO2 returns to within 1 of baseline; only then can
        a new event begin (prevents double-counting plateau dips)
    """
    if not readings:
        return 0

    baseline_window_s = 100.0
    min_event_duration_s = 10.0

    events = 0
    baseline_buffer: list[tuple[datetime, int]] = []  # (timestamp, spo2)
    in_event = False
    event_start_ts: datetime | None = None
    event_baseline: float | None = None

    for r in readings:
        ts = _parse_ts(r["timestamp"])
        spo2 = r["spo2"]

        # Maintain rolling baseline buffer
        baseline_buffer.append((ts, spo2))
        cutoff = ts.timestamp() - baseline_window_s
        while baseline_buffer and baseline_buffer[0][0].timestamp() < cutoff:
            baseline_buffer.pop(0)

        # Need enough history before we can detect events
        if len(baseline_buffer) < 5:
            continue

        # Baseline = mean of recent window (exclude current sample to avoid
        # the dip dragging its own baseline down)
        history = baseline_buffer[:-1]
        baseline = sum(s for _, s in history) / len(history)

        if not in_event:
            if spo2 <= baseline - drop:
                in_event = True
                event_start_ts = ts
                event_baseline = baseline
        else:
            # Event ends when we recover within 1 of baseline
            if event_baseline is not None and spo2 >= event_baseline - 1:
                duration = (ts - event_start_ts).total_seconds() if event_start_ts else 0
                if duration >= min_event_duration_s:
                    events += 1
                in_event = False
                event_start_ts = None
                event_baseline = None

    return events
