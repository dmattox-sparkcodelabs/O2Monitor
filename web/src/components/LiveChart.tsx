"use client";

/**
 * LiveChart — Taller dual-axis chart matching Windows baseline viewer.
 * SpO2 on left axis (green line), HR on right axis (blue line).
 * 480px tall with threshold reference zones.
 * Background: #1a2332 card, #2a3a52 border.
 */

import { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceArea,
  Legend,
} from "recharts";
import { ReadingRecord, LatestReading } from "@/lib/types";

interface LiveChartProps {
  readings: ReadingRecord[];
  realtimeReadings: LatestReading[];
}

interface ChartPoint {
  time: string;
  timestamp: number;
  spo2: number;
  heartRate: number;
}

function formatTime(ts: string): string {
  const d = new Date(ts);
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  return `${h}:${m}`;
}

export default function LiveChart({ readings, realtimeReadings }: LiveChartProps) {
  const data = useMemo(() => {
    const historical: ChartPoint[] = readings
      .map((r) => ({
        time: formatTime(r.timestamp),
        timestamp: new Date(r.timestamp).getTime(),
        spo2: r.spo2,
        heartRate: r.heartRate,
      }))
      .sort((a, b) => a.timestamp - b.timestamp);

    const lastHistTs = historical.length > 0 ? historical[historical.length - 1].timestamp : 0;

    const realtime: ChartPoint[] = realtimeReadings
      .filter((r) => new Date(r.timestamp).getTime() > lastHistTs)
      .map((r) => ({
        time: formatTime(r.timestamp),
        timestamp: new Date(r.timestamp).getTime(),
        spo2: r.spo2,
        heartRate: r.heartRate,
      }));

    return [...historical, ...realtime];
  }, [readings, realtimeReadings]);

  if (data.length === 0) {
    return (
      <div className="bg-[#1a2332] border border-[#2a3a52] rounded-lg p-6 text-center text-[#8a96a7] h-[480px] flex items-center justify-center">
        No readings to display
      </div>
    );
  }

  return (
    <div className="bg-[#1a2332] border border-[#2a3a52] rounded-lg p-4">
      <ResponsiveContainer width="100%" height={480}>
        <ComposedChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(138, 150, 167, 0.1)" />

          {/* Threshold zones */}
          <ReferenceArea y1={70} y2={88} yAxisId="spo2" fill="#ff6b6b" fillOpacity={0.06} />
          <ReferenceArea y1={88} y2={90} yAxisId="spo2" fill="#ffd43b" fillOpacity={0.06} />

          <XAxis
            dataKey="time"
            stroke="#2a3a52"
            tick={{ fill: "#8a96a7", fontSize: 11 }}
            interval="preserveStartEnd"
            minTickGap={60}
          />
          <YAxis
            yAxisId="spo2"
            domain={[70, 100]}
            stroke="#2a3a52"
            tick={{ fill: "#4dabf7", fontSize: 11 }}
            label={{ value: "SpO2 (%)", angle: -90, position: "insideLeft", fill: "#4dabf7", fontSize: 11, dx: -4 }}
            tickFormatter={(v: number) => `${v}%`}
          />
          <YAxis
            yAxisId="hr"
            orientation="right"
            domain={[40, 140]}
            stroke="#2a3a52"
            tick={{ fill: "#ff6b6b", fontSize: 11 }}
            label={{ value: "HR (bpm)", angle: 90, position: "insideRight", fill: "#ff6b6b", fontSize: 11, dx: 4 }}
            tickFormatter={(v: number) => `${v}`}
          />

          <Tooltip
            contentStyle={{
              backgroundColor: "#1a2332",
              border: "1px solid #2a3a52",
              borderRadius: "8px",
              color: "#e4e6eb",
            }}
            labelStyle={{ color: "#8a96a7" }}
            itemStyle={{ color: "#e4e6eb" }}
          />

          <Legend
            wrapperStyle={{ color: "#e4e6eb", fontSize: 12 }}
          />

          <Line
            yAxisId="spo2"
            type="monotone"
            dataKey="spo2"
            stroke="#4dabf7"
            strokeWidth={2}
            dot={false}
            name="SpO2"
            activeDot={{ r: 4, fill: "#4dabf7" }}
          />
          <Line
            yAxisId="hr"
            type="monotone"
            dataKey="heartRate"
            stroke="#ff6b6b"
            strokeWidth={2}
            dot={false}
            name="Heart Rate"
            activeDot={{ r: 4, fill: "#ff6b6b" }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
