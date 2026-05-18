"use client";

import { useEffect, useRef, useMemo } from "react";
import { NightlySummary, ReadingRecord } from "@/lib/types";
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
  classifyMinSpo2: (v: number) => string;
  classifyPctBelow: (v: number) => string;
  classifyOdi: (v: number) => string;
}

function formatNightDate(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
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

function CompactChart({ readings }: { readings: ReadingRecord[] }) {
  const data = useMemo(() => {
    return readings.map((r) => ({
      ts: new Date(r.timestamp).getTime(),
      time: new Date(r.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
      spo2: r.spo2,
      hr: r.heartRate,
    }));
  }, [readings]);

  if (data.length === 0) {
    return (
      <div className="h-[120px] flex items-center justify-center text-[#5a6a7a] text-xs">
        No chart data
      </div>
    );
  }

  const minSpo2 = Math.min(...data.map((d) => d.spo2));
  const yMin = Math.min(80, minSpo2 - 2);

  return (
    <ResponsiveContainer width="100%" height={120}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" />
        <ReferenceArea y1={yMin} y2={88} yAxisId="spo2" fill="#dc2626" fillOpacity={0.08} />
        <ReferenceArea y1={88} y2={90} yAxisId="spo2" fill="#eab308" fillOpacity={0.06} />
        <XAxis
          dataKey="time"
          stroke="#3a4a5a"
          tick={{ fill: "#5a6a7a", fontSize: 9 }}
          interval="preserveStartEnd"
          minTickGap={80}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          yAxisId="spo2"
          domain={[yMin, 100]}
          stroke="#3a4a5a"
          tick={{ fill: "#5a6a7a", fontSize: 9 }}
          width={30}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          yAxisId="hr"
          orientation="right"
          domain={[40, 140]}
          stroke="#3a4a5a"
          tick={{ fill: "#5a6a7a", fontSize: 9 }}
          width={30}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{ backgroundColor: "#1a2332", border: "1px solid #2a3a52", borderRadius: "6px", fontSize: "11px" }}
          labelStyle={{ color: "#8a96a7" }}
          itemStyle={{ color: "#e4e6eb" }}
        />
        <Line yAxisId="spo2" type="monotone" dataKey="spo2" stroke="#51cf66" strokeWidth={1.5} dot={false} name="SpO2" />
        <Line yAxisId="hr" type="monotone" dataKey="hr" stroke="#4dabf7" strokeWidth={1} dot={false} name="HR" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function NightCard({ summary, odi, onVisible, classifyMinSpo2, classifyPctBelow, classifyOdi }: NightCardProps) {
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
  const pctBelow90 = s.durationSeconds > 0 ? (s.timeBelow90Seconds / s.durationSeconds) * 100 : 0;
  const pctBelow88 = s.durationSeconds > 0 ? (s.timeBelow88Seconds / s.durationSeconds) * 100 : 0;

  const metrics: Metric[] = [
    { label: "Mean SpO2", value: `${s.spo2Avg}%` },
    { label: "Min SpO2", value: `${s.spo2Min}%`, colorClass: classifyMinSpo2(s.spo2Min) },
    { label: "Mean HR", value: `${s.hrAvg}` },
    { label: "Max HR", value: `${s.hrMax}` },
    { label: "< 90%", value: formatPct(pctBelow90), colorClass: classifyPctBelow(pctBelow90) },
    { label: "< 88%", value: formatPct(pctBelow88), colorClass: classifyPctBelow(pctBelow88) },
    { label: "ODI-3", value: odi?.odi3 != null ? `${odi.odi3}` : "...", colorClass: odi?.odi3 != null ? classifyOdi(odi.odi3) : "text-[#5a6a7a]" },
    { label: "ODI-4", value: odi?.odi4 != null ? `${odi.odi4}` : "...", colorClass: odi?.odi4 != null ? classifyOdi(odi.odi4) : "text-[#5a6a7a]" },
  ];

  return (
    <div ref={ref} className="bg-[#1a2332] border border-[#2a3a52] rounded-lg overflow-hidden">
      {/* Night header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#2a3a52]/60">
        <span className="text-sm font-medium text-[#e4e6eb]">{formatNightDate(s.nightDate)}</span>
        <span className="text-xs text-[#5a6a7a]">
          {formatDuration(s.durationSeconds)} &middot; {s.readingCount.toLocaleString()} readings
        </span>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-4 sm:grid-cols-8 gap-px bg-[#2a3a52]/30">
        {metrics.map((m) => (
          <div key={m.label} className="bg-[#1a2332] px-3 py-2 text-center">
            <div className="text-[10px] text-[#5a6a7a] uppercase tracking-wide">{m.label}</div>
            <div className={`text-sm font-semibold tabular-nums ${m.colorClass ?? "text-[#e4e6eb]"}`}>
              {m.value}
            </div>
          </div>
        ))}
      </div>

      {/* Compact chart */}
      <div className="px-2 pt-1 pb-2">
        {odi ? (
          <CompactChart readings={odi.readings} />
        ) : (
          <div className="h-[120px] flex items-center justify-center text-[#5a6a7a] text-xs">
            Loading chart...
          </div>
        )}
      </div>
    </div>
  );
}
