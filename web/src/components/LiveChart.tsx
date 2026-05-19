"use client";

import { useMemo, useState, useCallback, useRef, useEffect } from "react";
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
  windowHours?: number;
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

function formatTimeRange(ms: number): string {
  const d = new Date(ms);
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export default function LiveChart({ readings, realtimeReadings, windowHours }: LiveChartProps) {
  const allData = useMemo(() => {
    const historical: ChartPoint[] = readings
      .map((r) => ({
        time: formatTime(r.timestamp),
        timestamp: new Date(r.timestamp).getTime(),
        spo2: r.spo2,
        heartRate: r.heartRate,
      }))
      .sort((a, b) => a.timestamp - b.timestamp);

    // Dedup readings within 1 second (mixed Z/no-Z timestamp formats)
    const deduped: ChartPoint[] = [];
    for (const p of historical) {
      if (deduped.length === 0 || p.timestamp - deduped[deduped.length - 1].timestamp >= 1000) {
        deduped.push(p);
      }
    }

    const lastHistTs = deduped.length > 0 ? deduped[deduped.length - 1].timestamp : 0;

    const realtime: ChartPoint[] = realtimeReadings
      .filter((r) => new Date(r.timestamp).getTime() > lastHistTs)
      .map((r) => ({
        time: formatTime(r.timestamp),
        timestamp: new Date(r.timestamp).getTime(),
        spo2: r.spo2,
        heartRate: r.heartRate,
      }));

    return [...deduped, ...realtime];
  }, [readings, realtimeReadings]);

  // Scrollbar state: position is 0-1 representing where the window starts
  const [scrollPos, setScrollPos] = useState(1); // default: right-aligned (latest)
  const scrollbarRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  // Reset scroll to end when data changes
  useEffect(() => { setScrollPos(1); }, [readings]);

  // Compute windowed data
  const { visibleData, thumbWidth, dataMin, dataMax, windowStart, windowEnd } = useMemo(() => {
    if (allData.length === 0) {
      return { visibleData: [], thumbWidth: 1, dataMin: 0, dataMax: 0, windowStart: 0, windowEnd: 0 };
    }

    const dMin = allData[0].timestamp;
    const dMax = allData[allData.length - 1].timestamp;
    const totalSpan = dMax - dMin;

    if (!windowHours || totalSpan <= 0) {
      return { visibleData: allData, thumbWidth: 1, dataMin: dMin, dataMax: dMax, windowStart: dMin, windowEnd: dMax };
    }

    const windowMs = windowHours * 60 * 60 * 1000;
    const tw = Math.min(1, windowMs / totalSpan);
    const maxOffset = totalSpan - windowMs;
    const offset = scrollPos * maxOffset;
    const wStart = dMin + offset;
    const wEnd = wStart + windowMs;

    const filtered = allData.filter((p) => p.timestamp >= wStart && p.timestamp <= wEnd);

    return {
      visibleData: filtered.length > 0 ? filtered : allData,
      thumbWidth: tw,
      dataMin: dMin,
      dataMax: dMax,
      windowStart: wStart,
      windowEnd: wEnd,
    };
  }, [allData, windowHours, scrollPos]);

  // Scrollbar drag handlers
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true;
    e.preventDefault();
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!dragging.current || !scrollbarRef.current) return;
    const rect = scrollbarRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const maxPos = 1 - thumbWidth;
    setScrollPos(Math.max(0, Math.min(1, x / Math.max(0.01, 1 - thumbWidth))));
  }, [thumbWidth]);

  const handleMouseUp = useCallback(() => {
    dragging.current = false;
  }, []);

  useEffect(() => {
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  // Click on scrollbar track to jump
  const handleTrackClick = useCallback((e: React.MouseEvent) => {
    if (!scrollbarRef.current) return;
    const rect = scrollbarRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    setScrollPos(Math.max(0, Math.min(1, x / Math.max(0.01, 1 - thumbWidth))));
  }, [thumbWidth]);

  if (allData.length === 0) {
    return (
      <div className="bg-[#1a2332] border border-[#2a3a52] rounded-lg p-6 text-center text-[#8a96a7] h-[480px] flex items-center justify-center">
        No readings to display
      </div>
    );
  }

  const thumbLeft = scrollPos * (1 - thumbWidth);

  return (
    <div>
      <div className="bg-[#1a2332] border border-[#2a3a52] rounded-lg p-4">
        <ResponsiveContainer width="100%" height={480}>
          <ComposedChart data={visibleData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(138, 150, 167, 0.1)" />
            <ReferenceArea y1={50} y2={88} yAxisId="spo2" fill="#ff6b6b" fillOpacity={0.06} />
            <ReferenceArea y1={88} y2={90} yAxisId="spo2" fill="#ffd43b" fillOpacity={0.06} />
            <XAxis
              dataKey="timestamp"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(ts: number) => formatTime(new Date(ts).toISOString())}
              stroke="#2a3a52"
              tick={{ fill: "#8a96a7", fontSize: 11 }}
              minTickGap={60}
            />
            <YAxis
              yAxisId="spo2"
              domain={[(dataMin: number) => Math.min(80, dataMin - 2), 100]}
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
              labelFormatter={(ts: unknown) => new Date(Number(ts)).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}
              contentStyle={{ backgroundColor: "#1a2332", border: "1px solid #2a3a52", borderRadius: "8px", color: "#e4e6eb" }}
              labelStyle={{ color: "#8a96a7" }}
              itemStyle={{ color: "#e4e6eb" }}
            />
            <Legend wrapperStyle={{ color: "#e4e6eb", fontSize: 12 }} />
            <Line yAxisId="spo2" type="monotone" dataKey="spo2" stroke="#4dabf7" strokeWidth={2} dot={false} name="SpO2" activeDot={{ r: 4, fill: "#4dabf7" }} isAnimationActive={false} />
            <Line yAxisId="hr" type="monotone" dataKey="heartRate" stroke="#ff6b6b" strokeWidth={2} dot={false} name="Heart Rate" activeDot={{ r: 4, fill: "#ff6b6b" }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Scrollbar scrubber */}
      <div className="bg-[#1a2332] border border-[#2a3a52] rounded-lg mt-2 px-3 py-2">
        <div className="flex items-center gap-3">
          <span className="text-[#8a96a7] text-xs font-mono min-w-[130px]">
            {formatTimeRange(thumbWidth < 1 ? windowStart : dataMin)}
          </span>
          <div
            ref={scrollbarRef}
            className="flex-1 h-[18px] bg-[#2a3a52] rounded-[9px] relative cursor-pointer select-none"
            onClick={handleTrackClick}
          >
            <div
              className={`absolute top-[2px] bottom-[2px] bg-[#4dabf7] rounded-[7px] min-w-[20px] cursor-grab hover:bg-[#74c0fc] ${dragging.current ? "cursor-grabbing bg-[#74c0fc]" : ""}`}
              style={{
                left: `${thumbLeft * 100}%`,
                width: `${Math.max(thumbWidth * 100, 3)}%`,
              }}
              onMouseDown={handleMouseDown}
            />
          </div>
          <span className="text-[#8a96a7] text-xs font-mono min-w-[130px] text-right">
            {formatTimeRange(thumbWidth < 1 ? windowEnd : dataMax)}
          </span>
        </div>
      </div>
    </div>
  );
}
