import { Reading } from "./types";

export interface DailySummary {
  id: string;
  patientId: string;
  nightDate: string;
  readingCount: number;
  durationSeconds: number;
  spo2Avg: number;
  spo2Min: number;
  spo2Max: number;
  hrAvg: number;
  hrMin: number;
  hrMax: number;
  timeBelow90Seconds: number;
  timeBelow88Seconds: number;
  pctBelow90: number;
  pctBelow88: number;
  createdAt: string;
}

export function computeNightDate(timestamp: string): string {
  const d = new Date(timestamp);
  d.setUTCHours(d.getUTCHours() + 12);
  return d.toISOString().split("T")[0];
}

export function computeSummary(
  patientId: string,
  nightDate: string,
  readings: Reading[]
): DailySummary {
  const sorted = [...readings].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  const count = sorted.length;
  const firstTs = new Date(sorted[0].timestamp).getTime();
  const lastTs = new Date(sorted[count - 1].timestamp).getTime();
  const durationSeconds = Math.round((lastTs - firstTs) / 1000);

  const spo2Values = sorted.map((r) => r.spo2);
  const hrValues = sorted.filter((r) => r.heartRate > 0).map((r) => r.heartRate);

  const spo2Avg = spo2Values.reduce((a, b) => a + b, 0) / count;
  const spo2Min = Math.min(...spo2Values);
  const spo2Max = Math.max(...spo2Values);

  const hrAvg = hrValues.length > 0
    ? hrValues.reduce((a, b) => a + b, 0) / hrValues.length
    : 0;
  const hrMin = hrValues.length > 0 ? Math.min(...hrValues) : 0;
  const hrMax = hrValues.length > 0 ? Math.max(...hrValues) : 0;

  let timeBelow90 = 0;
  let timeBelow88 = 0;

  for (let i = 0; i < sorted.length - 1; i++) {
    const intervalSec = (new Date(sorted[i + 1].timestamp).getTime() - new Date(sorted[i].timestamp).getTime()) / 1000;

    if (sorted[i].spo2 < 90) timeBelow90 += intervalSec;
    if (sorted[i].spo2 < 88) timeBelow88 += intervalSec;
  }

  const pctBelow90 = durationSeconds > 0 ? timeBelow90 / durationSeconds : 0;
  const pctBelow88 = durationSeconds > 0 ? timeBelow88 / durationSeconds : 0;

  return {
    id: `${patientId}:${nightDate}`,
    patientId,
    nightDate,
    readingCount: count,
    durationSeconds,
    spo2Avg: Math.round(spo2Avg * 10) / 10,
    spo2Min,
    spo2Max,
    hrAvg: Math.round(hrAvg * 10) / 10,
    hrMin,
    hrMax,
    timeBelow90Seconds: Math.round(timeBelow90),
    timeBelow88Seconds: Math.round(timeBelow88),
    pctBelow90: Math.round(pctBelow90 * 100) / 100,
    pctBelow88: Math.round(pctBelow88 * 100) / 100,
    createdAt: new Date().toISOString(),
  };
}
