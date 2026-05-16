"use client";

import { NightlySummary } from "@/lib/types";

interface NightlySummaryTableProps {
  summaries: NightlySummary[];
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00Z");
  return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

export default function NightlySummaryTable({ summaries }: NightlySummaryTableProps) {
  if (summaries.length === 0) {
    return <p className="text-gray-500 text-center py-8">No nightly summaries available yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead className="text-xs text-gray-400 uppercase border-b border-gray-700">
          <tr>
            <th className="px-4 py-3">Night</th>
            <th className="px-4 py-3">Avg SpO2</th>
            <th className="px-4 py-3">Min SpO2</th>
            <th className="px-4 py-3">Below 90%</th>
            <th className="px-4 py-3">Avg HR</th>
            <th className="px-4 py-3">Duration</th>
            <th className="px-4 py-3">Readings</th>
          </tr>
        </thead>
        <tbody>
          {summaries.map((s) => (
            <tr key={s.nightDate} className="border-b border-gray-800 hover:bg-gray-800/50">
              <td className="px-4 py-2 font-medium">{formatDate(s.nightDate)}</td>
              <td className={`px-4 py-2 ${s.spo2Avg < 92 ? "text-yellow-400" : ""}`}>
                {s.spo2Avg}%
              </td>
              <td className={`px-4 py-2 ${s.spo2Min < 90 ? "text-red-400" : s.spo2Min < 92 ? "text-yellow-400" : ""}`}>
                {s.spo2Min}%
              </td>
              <td className={`px-4 py-2 ${s.pctBelow90 > 0.1 ? "text-red-400" : s.pctBelow90 > 0 ? "text-yellow-400" : ""}`}>
                {s.timeBelow90Seconds > 0
                  ? `${formatDuration(s.timeBelow90Seconds)} (${Math.round(s.pctBelow90 * 100)}%)`
                  : "—"}
              </td>
              <td className="px-4 py-2">{s.hrAvg} bpm</td>
              <td className="px-4 py-2">{formatDuration(s.durationSeconds)}</td>
              <td className="px-4 py-2 text-gray-400">{s.readingCount.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
