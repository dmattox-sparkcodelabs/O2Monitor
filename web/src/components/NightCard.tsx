"use client";

import { useEffect, useRef, useMemo } from "react";
import { NightlySummary, ReadingRecord } from "@/lib/types";
import { countDesaturationEvents, timeBelow } from "@/lib/stats";
import type { NightOdi } from "@/app/history/page";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceArea,
  Tooltip,
} from "recharts";

interface NightCardProps {
  summary: NightlySummary;
  odi: NightOdi | null;
  onVisible: () => void;
  sleepOnly?: boolean;
  classifyMinSpo2: (v: number) => string;
  classifyPctBelow: (v: number) => string;
  classifyOdi: (v: number) => string;
}

function formatNightDate(dateStr: string): string {
  const evening = new Date(dateStr + "T12:00:00");
  evening.setDate(evening.getDate() - 1);
  const morning = new Date(dateStr + "T12:00:00");
  const fmt = (d: Date) => d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  return `${fmt(evening)} - ${fmt(morning)}`;
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function formatPct(pct: number): string {
  if (pct === 0) return "0%";
  return `${Math.round(pct * 10) / 10}%`;
}

interface Metric {
  label: string;
  value: string;
  colorClass?: string;
}

function downsampleByTime(readings: ReadingRecord[], maxPoints: number): ReadingRecord[] {
  if (readings.length <= maxPoints) return readings;
  const firstTs = new Date(readings[0].timestamp).getTime();
  const lastTs = new Date(readings[readings.length - 1].timestamp).getTime();
  const span = lastTs - firstTs;
  if (span <= 0) return readings.slice(0, maxPoints);
  const bucketMs = span / maxPoints;
  const result: ReadingRecord[] = [];
  let nextBucket = firstTs;
  let idx = 0;
  while (idx < readings.length && result.length < maxPoints) {
    const ts = new Date(readings[idx].timestamp).getTime();
    if (ts >= nextBucket) {
      result.push(readings[idx]);
      nextBucket = ts + bucketMs;
    }
    idx++;
  }
  if (result.length > 0 && result[result.length - 1] !== readings[readings.length - 1]) {
    result.push(readings[readings.length - 1]);
  }
  return result;
}

function formatTickTime(ts: unknown): string {
  return new Date(Number(ts)).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

const GAP_THRESHOLD_MS = 30 * 60 * 1000;
const TICK_INTERVAL_MS = 30 * 60 * 1000;

function insertGapBreaks(
  points: { ts: number; spo2: number; hr: number }[]
): { ts: number; spo2: number | null; hr: number | null }[] {
  if (points.length === 0) return [];
  const result: { ts: number; spo2: number | null; hr: number | null }[] = [];
  for (let i = 0; i < points.length; i++) {
    if (i > 0 && points[i].ts - points[i - 1].ts > GAP_THRESHOLD_MS) {
      result.push({ ts: points[i - 1].ts + 1, spo2: null, hr: null });
    }
    result.push(points[i]);
  }
  return result;
}

function CompactChart({ readings, nightDate }: { readings: ReadingRecord[]; nightDate: string }) {
  const nightStart = useMemo(() => {
    const [y, m, d] = nightDate.split("-").map(Number);
    const start = new Date(y, m - 1, d - 1, 12, 0, 0, 0);
    return start.getTime();
  }, [nightDate]);
  const nightEnd = useMemo(() => {
    const [y, m, d] = nightDate.split("-").map(Number);
    const end = new Date(y, m - 1, d, 12, 0, 0, 0);
    return end.getTime();
  }, [nightDate]);

  const ticks = useMemo(() => {
    const t: number[] = [];
    for (let ms = nightStart; ms <= nightEnd; ms += TICK_INTERVAL_MS) {
      t.push(ms);
    }
    return t;
  }, [nightStart, nightEnd]);

  const data = useMemo(() => {
    const withTs = readings.map((r) => ({ ...r, _ts: new Date(r.timestamp).getTime() }));
    const filtered = withTs
      .filter((r) => r._ts >= nightStart && r._ts <= nightEnd)
      .sort((a, b) => a._ts - b._ts);
    const deduped: typeof filtered = [];
    for (const r of filtered) {
      if (deduped.length === 0 || r._ts - deduped[deduped.length - 1]._ts >= 1000) {
        deduped.push(r);
      }
    }
    const sampled = downsampleByTime(deduped as ReadingRecord[], 1000);
    const points = sampled.map((r) => ({
      ts: new Date(r.timestamp).getTime(),
      spo2: r.spo2,
      hr: r.heartRate,
    }));
    return insertGapBreaks(points);
  }, [readings, nightStart, nightEnd]);

  if (data.length === 0) {
    return (
      <div className="h-[120px] flex items-center justify-center text-[#5a6a7a] text-xs">
        No chart data
      </div>
    );
  }

  const validSpo2 = data.filter((d) => d.spo2 != null).map((d) => d.spo2 as number);
  const minSpo2 = validSpo2.length > 0 ? Math.min(...validSpo2) : 80;
  const yMin = Math.min(80, minSpo2 - 2);

  const sleepStart = useMemo(() => {
    const [y, m, d] = nightDate.split("-").map(Number);
    return new Date(y, m - 1, d - 1, 22, 0, 0, 0).getTime();
  }, [nightDate]);
  const sleepEnd = useMemo(() => {
    const [y, m, d] = nightDate.split("-").map(Number);
    return new Date(y, m - 1, d, 6, 0, 0, 0).getTime();
  }, [nightDate]);

  return (
    <ResponsiveContainer width="100%" height={120}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" />
        <ReferenceArea x1={sleepStart} x2={sleepEnd} yAxisId="spo2" fill="#4dabf7" fillOpacity={0.06} />
        <ReferenceArea y1={yMin} y2={88} yAxisId="spo2" fill="#dc2626" fillOpacity={0.08} />
        <ReferenceArea y1={88} y2={90} yAxisId="spo2" fill="#eab308" fillOpacity={0.06} />
        <XAxis
          dataKey="ts"
          type="number"
          domain={[nightStart, nightEnd]}
          allowDataOverflow
          ticks={ticks}
          tickFormatter={formatTickTime}
          stroke="#3a4a5a"
          tick={{ fill: "#a0aec0", fontSize: 13 }}
          minTickGap={60}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          yAxisId="spo2"
          domain={[yMin, 100]}
          stroke="#3a4a5a"
          tick={{ fill: "#a0aec0", fontSize: 13 }}
          width={40}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          yAxisId="hr"
          orientation="right"
          domain={[40, 140]}
          stroke="#3a4a5a"
          tick={{ fill: "#a0aec0", fontSize: 13 }}
          width={40}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          labelFormatter={formatTickTime}
          contentStyle={{ backgroundColor: "#1a2332", border: "1px solid #2a3a52", borderRadius: "6px", fontSize: "11px" }}
          labelStyle={{ color: "#8a96a7" }}
          itemStyle={{ color: "#e4e6eb" }}
        />
        <Line yAxisId="spo2" type="monotone" dataKey="spo2" stroke="#51cf66" strokeWidth={1.5} dot={false} name="SpO2" connectNulls={false} isAnimationActive={false} />
        <Line yAxisId="hr" type="monotone" dataKey="hr" stroke="#4dabf7" strokeWidth={1} dot={false} name="HR" connectNulls={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function filterSleepWindow(readings: ReadingRecord[], nightDate: string): ReadingRecord[] {
  const [y, m, d] = nightDate.split("-").map(Number);
  const sleepStart = new Date(y, m - 1, d - 1, 22, 0, 0, 0).getTime();
  const sleepEnd = new Date(y, m - 1, d, 6, 0, 0, 0).getTime();
  return readings.filter((r) => {
    const ts = new Date(r.timestamp).getTime();
    return ts >= sleepStart && ts <= sleepEnd;
  });
}

function computeMetricsFromReadings(readings: ReadingRecord[]): {
  spo2Avg: number; spo2Min: number; hrAvg: number; hrMax: number;
  pctBelow90: number; pctBelow88: number; odi3: number; odi4: number;
  durationSeconds: number; readingCount: number;
} | null {
  if (readings.length < 2) return null;
  const spo2Values = readings.map((r) => r.spo2);
  const hrValues = readings.filter((r) => r.heartRate > 0).map((r) => r.heartRate);
  const firstTs = new Date(readings[0].timestamp).getTime();
  const lastTs = new Date(readings[readings.length - 1].timestamp).getTime();
  const durationSeconds = (lastTs - firstTs) / 1000;
  const durationHours = durationSeconds / 3600;

  const below90s = timeBelow(readings, 90);
  const below88s = timeBelow(readings, 88);

  const odi3Events = countDesaturationEvents(readings, 3);
  const odi4Events = countDesaturationEvents(readings, 4);

  return {
    spo2Avg: Math.round(spo2Values.reduce((a, b) => a + b, 0) / spo2Values.length * 10) / 10,
    spo2Min: Math.min(...spo2Values),
    hrAvg: hrValues.length > 0 ? Math.round(hrValues.reduce((a, b) => a + b, 0) / hrValues.length * 10) / 10 : 0,
    hrMax: hrValues.length > 0 ? Math.max(...hrValues) : 0,
    pctBelow90: durationSeconds > 0 ? Math.round(below90s / durationSeconds * 1000) / 10 : 0,
    pctBelow88: durationSeconds > 0 ? Math.round(below88s / durationSeconds * 1000) / 10 : 0,
    odi3: durationHours > 0 ? Math.round(odi3Events / durationHours * 10) / 10 : 0,
    odi4: durationHours > 0 ? Math.round(odi4Events / durationHours * 10) / 10 : 0,
    durationSeconds: Math.round(durationSeconds),
    readingCount: readings.length,
  };
}

export default function NightCard({ summary, odi, onVisible, sleepOnly, classifyMinSpo2, classifyPctBelow, classifyOdi }: NightCardProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          onVisible();
          observer.disconnect();
        }
      },
      { rootMargin: "200px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [onVisible]);

  const s = summary;

  const sleepStats = useMemo(() => {
    if (!sleepOnly || !odi?.readings?.length) return null;
    const filtered = filterSleepWindow(odi.readings, s.nightDate);
    return computeMetricsFromReadings(filtered);
  }, [sleepOnly, odi, s.nightDate]);

  const useSleep = sleepOnly && sleepStats != null;

  const spo2Avg = useSleep ? sleepStats.spo2Avg : s.spo2Avg;
  const spo2Min = useSleep ? sleepStats.spo2Min : s.spo2Min;
  const hrAvg = useSleep ? sleepStats.hrAvg : s.hrAvg;
  const hrMax = useSleep ? sleepStats.hrMax : s.hrMax;
  const pctBelow90 = useSleep ? sleepStats.pctBelow90 : (s.durationSeconds > 0 ? (s.timeBelow90Seconds / s.durationSeconds) * 100 : 0);
  const pctBelow88 = useSleep ? sleepStats.pctBelow88 : (s.durationSeconds > 0 ? (s.timeBelow88Seconds / s.durationSeconds) * 100 : 0);
  const odi3Val = useSleep ? sleepStats.odi3 : odi?.odi3;
  const odi4Val = useSleep ? sleepStats.odi4 : odi?.odi4;
  const durSec = useSleep ? sleepStats.durationSeconds : s.durationSeconds;
  const rCount = useSleep ? sleepStats.readingCount : s.readingCount;

  const metrics: Metric[] = [
    { label: "Mean SpO2", value: `${spo2Avg}%` },
    { label: "Min SpO2", value: `${spo2Min}%`, colorClass: classifyMinSpo2(spo2Min) },
    { label: "Mean HR", value: `${hrAvg}` },
    { label: "Max HR", value: `${hrMax}` },
    { label: "< 90%", value: formatPct(pctBelow90), colorClass: classifyPctBelow(pctBelow90) },
    { label: "< 88%", value: formatPct(pctBelow88), colorClass: classifyPctBelow(pctBelow88) },
    { label: "ODI-3", value: odi3Val != null ? `${odi3Val}` : "...", colorClass: odi3Val != null ? classifyOdi(odi3Val) : "text-[#5a6a7a]" },
    { label: "ODI-4", value: odi4Val != null ? `${odi4Val}` : "...", colorClass: odi4Val != null ? classifyOdi(odi4Val) : "text-[#5a6a7a]" },
  ];

  return (
    <div ref={ref} className="bg-[#1a2332] border border-[#2a3a52] rounded-lg overflow-hidden">
      {/* Night header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#2a3a52]/60">
        <span className="text-sm font-medium text-[#e4e6eb]">{formatNightDate(s.nightDate)}</span>
        <span className="text-xs text-[#5a6a7a]">
          {formatDuration(durSec)} &middot; {rCount.toLocaleString()} readings
        </span>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-4 sm:grid-cols-8 gap-px bg-[#2a3a52]/30">
        {metrics.map((m) => (
          <div key={m.label} className="bg-[#1a2332] px-3 py-4 text-center">
            <div className="text-sm text-[#a0aec0] uppercase tracking-wide font-medium">{m.label}</div>
            <div className={`text-2xl font-bold tabular-nums ${m.colorClass ?? "text-[#e4e6eb]"}`}>
              {m.value}
            </div>
          </div>
        ))}
      </div>

      {/* Compact chart */}
      <div className="px-2 pt-1 pb-2">
        {odi ? (
          <CompactChart readings={odi.readings} nightDate={s.nightDate} />
        ) : (
          <div className="h-[120px] flex items-center justify-center text-[#5a6a7a] text-xs">
            Loading chart...
          </div>
        )}
      </div>
    </div>
  );
}
