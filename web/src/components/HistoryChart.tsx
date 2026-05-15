"use client";

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
} from "recharts";
import { ReadingRecord } from "@/lib/types";

interface HistoryChartProps {
  readings: ReadingRecord[];
}

function formatTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleDateString([], { month: "short", day: "numeric" }) +
    " " + d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function HistoryChart({ readings }: HistoryChartProps) {
  const data = useMemo(() => {
    return readings
      .map((r) => ({
        time: formatTime(r.timestamp),
        timestamp: new Date(r.timestamp).getTime(),
        spo2: r.spo2,
        heartRate: r.heartRate,
      }))
      .sort((a, b) => a.timestamp - b.timestamp);
  }, [readings]);

  if (data.length === 0) {
    return (
      <div className="bg-gray-800 rounded-xl p-6 text-center text-gray-500 h-[300px] flex items-center justify-center">
        No readings for this time range
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-xl p-4">
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <ReferenceArea y1={0} y2={90} yAxisId="spo2" fill="#dc2626" fillOpacity={0.08} />
          <ReferenceArea y1={90} y2={92} yAxisId="spo2" fill="#eab308" fillOpacity={0.08} />
          <XAxis
            dataKey="time"
            stroke="#6b7280"
            tick={{ fill: "#9ca3af", fontSize: 10 }}
            interval="preserveStartEnd"
            minTickGap={80}
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
          <Line yAxisId="spo2" type="monotone" dataKey="spo2" stroke="#22c55e" strokeWidth={1.5} dot={false} name="SpO2" />
          <Line yAxisId="hr" type="monotone" dataKey="heartRate" stroke="#3b82f6" strokeWidth={1.5} dot={false} name="Heart Rate" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
