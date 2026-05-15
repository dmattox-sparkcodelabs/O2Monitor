"use client";

import { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceArea,
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
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
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
      <div className="bg-gray-800 rounded-xl p-6 text-center text-gray-500 h-[300px] flex items-center justify-center">
        No readings to display
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-xl p-4 mt-6">
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />

          <ReferenceArea y1={0} y2={90} yAxisId="spo2" fill="#dc2626" fillOpacity={0.08} />
          <ReferenceArea y1={90} y2={92} yAxisId="spo2" fill="#eab308" fillOpacity={0.08} />

          <XAxis
            dataKey="time"
            stroke="#6b7280"
            tick={{ fill: "#9ca3af", fontSize: 11 }}
            interval="preserveStartEnd"
            minTickGap={60}
          />
          <YAxis
            yAxisId="spo2"
            domain={[80, 100]}
            stroke="#6b7280"
            tick={{ fill: "#9ca3af", fontSize: 11 }}
            label={{ value: "SpO2 %", angle: -90, position: "insideLeft", fill: "#9ca3af", fontSize: 11 }}
          />
          <YAxis
            yAxisId="hr"
            orientation="right"
            domain={[40, 140]}
            stroke="#6b7280"
            tick={{ fill: "#9ca3af", fontSize: 11 }}
            label={{ value: "HR bpm", angle: 90, position: "insideRight", fill: "#9ca3af", fontSize: 11 }}
          />

          <Tooltip
            contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }}
            labelStyle={{ color: "#9ca3af" }}
            itemStyle={{ color: "#e5e7eb" }}
          />

          <Line
            yAxisId="spo2"
            type="monotone"
            dataKey="spo2"
            stroke="#22c55e"
            strokeWidth={2}
            dot={false}
            name="SpO2"
          />
          <Line
            yAxisId="hr"
            type="monotone"
            dataKey="heartRate"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            name="Heart Rate"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
