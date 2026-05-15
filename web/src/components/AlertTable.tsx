"use client";

import { AlertRecord } from "@/lib/types";

interface AlertTableProps {
  alerts: AlertRecord[];
}

function severityBadge(severity: string): string {
  switch (severity) {
    case "critical": return "bg-red-600 text-white";
    case "high": return "bg-orange-600 text-white";
    case "warning": return "bg-yellow-600 text-black";
    case "info": return "bg-blue-600 text-white";
    default: return "bg-gray-600 text-white";
  }
}

function formatTime(ts: string): string {
  return new Date(ts).toLocaleString([], {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function formatType(type: string): string {
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function AlertTable({ alerts }: AlertTableProps) {
  if (alerts.length === 0) {
    return <p className="text-gray-500 text-center py-8">No alerts found.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead className="text-xs text-gray-400 uppercase border-b border-gray-700">
          <tr>
            <th className="px-4 py-3">Time</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Severity</th>
            <th className="px-4 py-3">Message</th>
            <th className="px-4 py-3">SpO2</th>
            <th className="px-4 py-3">HR</th>
            <th className="px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
            <tr key={alert.id} className="border-b border-gray-800 hover:bg-gray-800/50">
              <td className="px-4 py-3 whitespace-nowrap">{formatTime(alert.timestamp)}</td>
              <td className="px-4 py-3 whitespace-nowrap">{formatType(alert.alertType)}</td>
              <td className="px-4 py-3">
                <span className={`${severityBadge(alert.severity)} px-2 py-0.5 rounded text-xs font-medium`}>
                  {alert.severity}
                </span>
              </td>
              <td className="px-4 py-3">{alert.message}</td>
              <td className="px-4 py-3">{alert.spo2 ?? "—"}</td>
              <td className="px-4 py-3">{alert.heartRate ?? "—"}</td>
              <td className="px-4 py-3">
                {alert.resolvedAt ? (
                  <span className="text-green-400 text-xs">Resolved {formatTime(alert.resolvedAt)}</span>
                ) : (
                  <span className="text-red-400 text-xs font-medium">Active</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
