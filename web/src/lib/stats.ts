import { ReadingRecord } from "./types";

export function timeBelow(readings: ReadingRecord[], threshold: number): number {
  let total = 0;
  let prevTs: number | null = null;
  let prevBelow = false;
  for (const r of readings) {
    const ts = new Date(r.timestamp).getTime() / 1000;
    const below = r.spo2 < threshold;
    if (prevTs !== null) {
      const gap = Math.min(ts - prevTs, 30);
      if (below && prevBelow) total += gap;
      else if (below !== prevBelow) total += gap / 2;
    }
    prevTs = ts;
    prevBelow = below;
  }
  return total;
}

export function countDesaturationEvents(readings: ReadingRecord[], drop: number): number {
  if (readings.length === 0) return 0;
  const BASELINE_WINDOW_S = 100;
  const MIN_EVENT_DURATION_S = 10;

  let events = 0;
  const buffer: { ts: number; spo2: number }[] = [];
  let inEvent = false;
  let eventStartTs = 0;
  let eventBaseline = 0;

  for (const r of readings) {
    const ts = new Date(r.timestamp).getTime() / 1000;
    const spo2 = r.spo2;
    buffer.push({ ts, spo2 });
    const cutoff = ts - BASELINE_WINDOW_S;
    while (buffer.length > 0 && buffer[0].ts < cutoff) buffer.shift();
    if (buffer.length < 5) continue;

    const history = buffer.slice(0, -1);
    const baseline = history.reduce((s, v) => s + v.spo2, 0) / history.length;

    if (!inEvent) {
      if (spo2 <= baseline - drop) {
        inEvent = true;
        eventStartTs = ts;
        eventBaseline = baseline;
      }
    } else {
      if (spo2 >= eventBaseline - 1) {
        if (ts - eventStartTs >= MIN_EVENT_DURATION_S) events++;
        inEvent = false;
      }
    }
  }
  return events;
}
