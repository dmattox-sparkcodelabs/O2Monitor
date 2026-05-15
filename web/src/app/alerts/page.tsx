"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchAlerts } from "@/lib/api";
import { AlertRecord } from "@/lib/types";
import { usePatient } from "@/hooks/usePatient";
import AlertTable from "@/components/AlertTable";

type TabValue = "all" | "active" | "resolved";

const SEVERITY_OPTIONS = ["all", "critical", "high", "warning", "info"] as const;

export default function AlertsPage() {
  const { selectedId, loading: patientsLoading } = usePatient();
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [tab, setTab] = useState<TabValue>("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      const statusParam = tab === "all" ? undefined : tab;
      const data = await fetchAlerts(selectedId, 30, statusParam);
      setAlerts(data.alerts);
    } catch {
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  }, [selectedId, tab]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = severityFilter === "all"
    ? alerts
    : alerts.filter((a) => a.severity === severityFilter);

  if (patientsLoading) {
    return <main className="flex-1 bg-gray-900 text-white flex items-center justify-center"><div className="text-gray-500">Loading...</div></main>;
  }

  return (
    <main className="flex-1 bg-gray-900 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <h1 className="text-xl font-semibold">Alert History</h1>
          <a href="/" className="text-sm text-gray-400 hover:text-white">← Dashboard</a>
        </div>
      </header>

      <div className="max-w-5xl mx-auto p-6">
        <div className="flex items-center gap-4 mb-6">
          <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
            {(["all", "active", "resolved"] as TabValue[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1 rounded text-sm font-medium capitalize transition-colors ${
                  tab === t ? "bg-gray-600 text-white" : "text-gray-400 hover:text-gray-200"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="bg-gray-800 text-white border border-gray-700 rounded px-2 py-1 text-sm"
          >
            {SEVERITY_OPTIONS.map((s) => (
              <option key={s} value={s}>{s === "all" ? "All Severities" : s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>

        {loading ? (
          <div className="text-center text-gray-500 py-8">Loading alerts...</div>
        ) : (
          <AlertTable alerts={filtered} />
        )}
      </div>
    </main>
  );
}
