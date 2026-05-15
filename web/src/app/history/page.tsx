"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { fetchReadings } from "@/lib/api";
import { ReadingRecord } from "@/lib/types";
import { usePatient } from "@/hooks/usePatient";
import HistoryChart from "@/components/HistoryChart";
import Nav from "@/components/Nav";

const RANGE_OPTIONS = [
  { label: "7d", hours: 7 * 24 },
  { label: "30d", hours: 30 * 24 },
  { label: "90d", hours: 90 * 24 },
];

const PAGE_SIZE = 50;

export default function HistoryPage() {
  const { selectedId, loading: patientsLoading } = usePatient();
  const [readings, setReadings] = useState<ReadingRecord[]>([]);
  const [rangeHours, setRangeHours] = useState(7 * 24);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);

  const load = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      const data = await fetchReadings(selectedId, rangeHours);
      setReadings(data.readings);
      setPage(0);
    } catch {
      setReadings([]);
    } finally {
      setLoading(false);
    }
  }, [selectedId, rangeHours]);

  useEffect(() => {
    load();
  }, [load]);

  const stats = useMemo(() => {
    if (readings.length === 0) return null;
    const spo2Values = readings.map((r) => r.spo2);
    const hrValues = readings.filter((r) => r.heartRate > 0).map((r) => r.heartRate);
    return {
      count: readings.length,
      spo2Avg: Math.round((spo2Values.reduce((a, b) => a + b, 0) / spo2Values.length) * 10) / 10,
      spo2Min: Math.min(...spo2Values),
      spo2Max: Math.max(...spo2Values),
      hrAvg: hrValues.length > 0 ? Math.round((hrValues.reduce((a, b) => a + b, 0) / hrValues.length) * 10) / 10 : 0,
    };
  }, [readings]);

  const sorted = useMemo(() => {
    return [...readings].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [readings]);

  const pageCount = Math.ceil(sorted.length / PAGE_SIZE);
  const pageReadings = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  if (patientsLoading) {
    return <main className="flex-1 bg-gray-900 text-white flex items-center justify-center"><div className="text-gray-500">Loading...</div></main>;
  }

  return (
    <main className="flex-1 bg-gray-900 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-xl font-semibold">History</h1>
            <Nav />
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.hours}
                onClick={() => setRangeHours(opt.hours)}
                className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                  rangeHours === opt.hours ? "bg-gray-600 text-white" : "text-gray-400 hover:text-gray-200"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {stats && (
            <div className="flex gap-6 text-sm">
              <div><span className="text-gray-400">Readings: </span><span className="font-medium">{stats.count.toLocaleString()}</span></div>
              <div><span className="text-gray-400">Avg SpO2: </span><span className="font-medium">{stats.spo2Avg}%</span></div>
              <div><span className="text-gray-400">Min SpO2: </span><span className="font-medium">{stats.spo2Min}%</span></div>
              <div><span className="text-gray-400">Avg HR: </span><span className="font-medium">{stats.hrAvg} bpm</span></div>
            </div>
          )}
        </div>

        {loading ? (
          <div className="text-center text-gray-500 py-8">Loading readings...</div>
        ) : (
          <>
            <HistoryChart readings={readings} />

            <div className="mt-6">
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="text-xs text-gray-400 uppercase border-b border-gray-700">
                    <tr>
                      <th className="px-4 py-3">Time</th>
                      <th className="px-4 py-3">SpO2</th>
                      <th className="px-4 py-3">HR</th>
                      <th className="px-4 py-3">Battery</th>
                      <th className="px-4 py-3">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageReadings.map((r) => (
                      <tr key={r.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                        <td className="px-4 py-2 whitespace-nowrap">{new Date(r.timestamp).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" })}</td>
                        <td className={`px-4 py-2 ${r.spo2 < 90 ? "text-red-400" : r.spo2 < 92 ? "text-yellow-400" : ""}`}>{r.spo2}%</td>
                        <td className={`px-4 py-2 ${r.heartRate > 120 || r.heartRate < 50 ? "text-red-400" : ""}`}>{r.heartRate}</td>
                        <td className="px-4 py-2">{r.batteryLevel}%</td>
                        <td className="px-4 py-2 text-gray-500">{r.source}</td>
                      </tr>
                    ))}
                    {pageReadings.length === 0 && (
                      <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">No readings found</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              {pageCount > 1 && (
                <div className="flex items-center justify-center gap-2 mt-4">
                  <button
                    onClick={() => setPage(Math.max(0, page - 1))}
                    disabled={page === 0}
                    className="px-3 py-1 rounded text-sm bg-gray-800 text-gray-300 disabled:opacity-30"
                  >
                    ← Prev
                  </button>
                  <span className="text-sm text-gray-400">
                    Page {page + 1} of {pageCount}
                  </span>
                  <button
                    onClick={() => setPage(Math.min(pageCount - 1, page + 1))}
                    disabled={page >= pageCount - 1}
                    className="px-3 py-1 rounded text-sm bg-gray-800 text-gray-300 disabled:opacity-30"
                  >
                    Next →
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </main>
  );
}
