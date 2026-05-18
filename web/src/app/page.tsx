"use client";

/**
 * O2 Monitor Dashboard — Windows Baseline Viewer style redesign.
 *
 * Design: Dark monitoring terminal (#0f1419 bg, #1a2332 cards, #2a3a52 borders).
 * Stats grid with uppercase labels, large tabular values, threshold color coding.
 * Tall dual-axis chart (480px). Compact header with connection status.
 *
 * Color tokens: --good: #51cf66, --warn: #ffd43b, --bad: #ff6b6b, --accent: #4dabf7
 *
 * States: loading-patients, no-patients, loading-vitals, error, populated, no-readings.
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import { fetchPatientStatus, fetchReadings, fetchSummaries } from "@/lib/api";
import { NightlySummary } from "@/lib/types";
import { PatientStatus, LatestReading, ReadingRecord } from "@/lib/types";
import { usePatient } from "@/hooks/usePatient";
import { useSignalR } from "@/hooks/useSignalR";
import VitalsCard, { spo2Color, hrColor, batteryColor, classifyMinSpo2, classifyPctBelow } from "@/components/VitalsCard";
import ConnectionStatus from "@/components/ConnectionStatus";
import PatientSelector from "@/components/PatientSelector";
import LiveChart from "@/components/LiveChart";
import TimeRangeToggle from "@/components/TimeRangeToggle";
import AlertBanner from "@/components/AlertBanner";
import Nav from "@/components/Nav";

const POLL_INTERVAL_MS = 15_000;

// --- Computed stats from readings ---

interface ComputedStats {
  meanSpo2: number | null;
  minSpo2: number | null;
  meanHr: number | null;
  timeBelow90Pct: number | null;
  readingCount: number;
}

function computeStats(readings: ReadingRecord[]): ComputedStats {
  if (readings.length === 0) {
    return { meanSpo2: null, minSpo2: null, meanHr: null, timeBelow90Pct: null, readingCount: 0 };
  }

  let spo2Sum = 0;
  let hrSum = 0;
  let minSpo2 = Infinity;
  let below90Count = 0;

  for (const r of readings) {
    spo2Sum += r.spo2;
    hrSum += r.heartRate;
    if (r.spo2 < minSpo2) minSpo2 = r.spo2;
    if (r.spo2 < 90) below90Count++;
  }

  const n = readings.length;
  const pctBelow90 = (below90Count / n) * 100;

  return {
    meanSpo2: Math.round((spo2Sum / n) * 10) / 10,
    minSpo2: minSpo2 === Infinity ? null : minSpo2,
    meanHr: Math.round(hrSum / n),
    timeBelow90Pct: Math.round(pctBelow90 * 10) / 10,
    readingCount: n,
  };
}

function fmtDuration(pct: number): string {
  if (pct === 0) return "0%";
  return `${pct}%`;
}

export default function Dashboard() {
  const { patients, selected, selectedId, selectPatient, loading: patientsLoading } = usePatient();
  const [status, setStatus] = useState<PatientStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [historicalReadings, setHistoricalReadings] = useState<ReadingRecord[]>([]);
  const [realtimeReadings, setRealtimeReadings] = useState<LatestReading[]>([]);
  const [zoomHours, setZoomHours] = useState(1);
  const [dataRangeHours, setDataRangeHours] = useState(24);
  const [availableNights, setAvailableNights] = useState<NightlySummary[]>([]);

  const poll = useCallback(async () => {
    if (!selectedId) return;
    try {
      const data = await fetchPatientStatus(selectedId);
      setStatus(data);
      setError(null);
      setLastUpdate(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch");
    }
  }, [selectedId]);

  useEffect(() => {
    setStatus(null);
    setError(null);
    setHistoricalReadings([]);
    setRealtimeReadings([]);
    if (!selectedId) return;

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [poll, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    setHistoricalReadings([]);
    setRealtimeReadings([]);
    fetchReadings(selectedId, dataRangeHours)
      .then((res) => setHistoricalReadings(res.readings))
      .catch(() => {});
  }, [selectedId, dataRangeHours]);

  useEffect(() => {
    if (!selectedId) return;
    fetchSummaries(selectedId, 90)
      .then((res) => setAvailableNights(res.summaries))
      .catch(() => setAvailableNights([]));
  }, [selectedId]);

  const handleNewReading = useCallback((reading: LatestReading) => {
    setStatus((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        latestReading: reading,
        secondsSinceReading: 0,
        deviceOnline: true,
      };
    });
    setRealtimeReadings((prev) => [...prev, reading]);
    setLastUpdate(new Date());
  }, []);

  const handleConnectionStatus = useCallback((event: { deviceOnline: boolean; secondsSinceReading: number | null }) => {
    setStatus((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        deviceOnline: event.deviceOnline,
        secondsSinceReading: event.secondsSinceReading,
      };
    });
  }, []);

  const handleAlertTriggered = useCallback((alert: { id: string; alertType: string; severity: string; message: string }) => {
    setStatus((prev) => {
      if (!prev) return prev;
      const exists = prev.activeAlerts.some((a) => a.id === alert.id);
      if (exists) return prev;
      return {
        ...prev,
        activeAlerts: [...prev.activeAlerts, { ...alert, timestamp: new Date().toISOString() }],
      };
    });
  }, []);

  const handleAlertResolved = useCallback((event: { id: string }) => {
    setStatus((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        activeAlerts: prev.activeAlerts.filter((a) => a.id !== event.id),
      };
    });
  }, []);

  const { connected: signalRConnected } = useSignalR({
    patientId: selectedId ?? "",
    onNewReading: handleNewReading,
    onConnectionStatus: handleConnectionStatus,
    onAlertTriggered: handleAlertTriggered,
    onAlertResolved: handleAlertResolved,
  });

  const reading = status?.latestReading ?? null;

  // Compute stats from readings for the stats grid
  const stats = useMemo(() => computeStats(historicalReadings), [historicalReadings]);

  // --- LOADING PATIENTS ---
  if (patientsLoading) {
    return (
      <main className="flex-1 bg-[#0f1419] text-[#e4e6eb] flex items-center justify-center">
        <div className="text-[#8a96a7]">Loading...</div>
      </main>
    );
  }

  // --- NO PATIENTS ---
  if (patients.length === 0) {
    return (
      <main className="flex-1 bg-[#0f1419] text-[#e4e6eb] flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-semibold mb-1">O2 Monitor</h1>
          <p className="text-[#8a96a7] text-sm mb-6">No patients yet -- create one to get started.</p>
          <p className="text-xs text-[#5a6a7a]">
            Use the API to create a patient:<br />
            <code className="text-[#4dabf7] font-mono">POST /api/patients {`{"name":"Dad","deviceMac":"..."}`}</code>
          </p>
        </div>
      </main>
    );
  }

  // --- MAIN DASHBOARD ---
  return (
    <main className="flex-1 bg-[#0f1419] text-[#e4e6eb]">
      {/* Header */}
      <header className="border-b border-[#2a3a52] px-6 py-4">
        <div className="w-full flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div>
              <h1 className="text-xl font-semibold text-[#e4e6eb]">O2 Monitor</h1>
              {selected && (
                <span className="text-sm text-[#8a96a7]">{selected.name}</span>
              )}
            </div>
            <Nav />
            <PatientSelector
              patients={patients}
              selectedId={selectedId}
              onSelect={selectPatient}
            />
          </div>
          <div className="flex items-center gap-4">
            {status && (
              <ConnectionStatus
                online={status.deviceOnline}
                secondsSinceReading={status.secondsSinceReading}
              />
            )}
            {lastUpdate && (
              <span className="text-xs text-[#8a96a7] hidden sm:inline">
                {lastUpdate.toLocaleTimeString()}
                {signalRConnected ? " (live)" : " (polling)"}
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Disclaimer bar */}
      <div className="w-full px-6 mt-4">
        <div className="bg-[#2a1a1a] border-l-[3px] border-l-[#ff6b6b] px-3 py-2 text-xs text-[#ffa8a8]">
          Not a medical device. Data here is for personal awareness only and is not a substitute for clinical evaluation.
        </div>
      </div>

      <div className="w-full px-6 py-6">
        {/* Alert banners */}
        {status && status.activeAlerts.length > 0 && (
          <AlertBanner alerts={status.activeAlerts} />
        )}

        {/* Error state */}
        {error && (
          <div className="bg-[#2a1a1a] border border-[#ff6b6b] rounded-lg px-4 py-3 mb-6 text-[#ffa8a8] text-sm">
            {error}
          </div>
        )}

        {/* Loading vitals */}
        {!status && !error && selectedId && (
          <div className="text-center text-[#8a96a7] py-20">Loading vitals...</div>
        )}

        {status && (
          <>
            {/* Stats grid — 8 cards in responsive grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-4 gap-3 mb-6">
              {/* Current SpO2 — large */}
              <VitalsCard
                label="Current SpO2"
                value={reading?.spo2 ?? null}
                unit="%"
                colorClass={reading?.spo2 != null ? spo2Color(reading.spo2) : undefined}
                large
              />
              {/* Current HR — large */}
              <VitalsCard
                label="Current HR"
                value={reading?.heartRate ?? null}
                unit="bpm"
                colorClass={reading?.heartRate != null ? hrColor(reading.heartRate) : undefined}
                large
              />
              {/* Battery */}
              <VitalsCard
                label="Battery"
                value={reading?.batteryLevel ?? null}
                unit="%"
                colorClass={reading?.batteryLevel != null ? batteryColor(reading.batteryLevel) : undefined}
              />
              {/* Mean SpO2 */}
              <VitalsCard
                label="Mean SpO2"
                value={stats.meanSpo2}
                unit="%"
              />
              {/* Min SpO2 */}
              <VitalsCard
                label="Min SpO2"
                value={stats.minSpo2}
                unit="%"
                colorClass={stats.minSpo2 != null ? classifyMinSpo2(stats.minSpo2) : undefined}
              />
              {/* Time <90% */}
              <VitalsCard
                label="Time < 90%"
                value={stats.timeBelow90Pct != null ? fmtDuration(stats.timeBelow90Pct) : null}
                colorClass={stats.timeBelow90Pct != null ? classifyPctBelow(stats.timeBelow90Pct) : undefined}
              />
              {/* Reading Count */}
              <VitalsCard
                label="Readings"
                value={stats.readingCount > 0 ? stats.readingCount : null}
              />
              {/* Connection Status */}
              <VitalsCard
                label="Connection"
                value={status.deviceOnline ? "Online" : "Offline"}
                colorClass={status.deviceOnline ? "text-[#51cf66]" : "text-[#ff6b6b]"}
              />
            </div>

            {/* Chart toolbar */}
            <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
              <div className="flex items-center gap-3">
                <span className="text-[#8a96a7] text-xs uppercase tracking-[0.5px] font-medium">Night</span>
                <select
                  className="bg-[#1a2332] border border-[#2a3a52] text-[#e4e6eb] rounded-md px-3 py-1.5 text-sm focus:border-[#4dabf7] focus:outline-none cursor-pointer"
                  defaultValue=""
                  onChange={(e) => {
                    if (e.target.value === "") {
                      setDataRangeHours(24);
                    } else {
                      const nightDate = new Date(e.target.value + "T12:00:00");
                      const now = new Date();
                      const diffHours = Math.max(1, (now.getTime() - nightDate.getTime()) / (1000 * 60 * 60));
                      setDataRangeHours(Math.min(Math.ceil(diffHours), 168));
                    }
                  }}
                >
                  <option value="">Live (recent)</option>
                  {availableNights.map((n) => (
                    <option key={n.nightDate} value={n.nightDate}>
                      {new Date(n.nightDate + "T12:00:00").toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })}
                      {" — "}SpO2 avg {n.spo2Avg}% min {n.spo2Min}%
                    </option>
                  ))}
                </select>
              </div>
              <TimeRangeToggle value={zoomHours} onChange={setZoomHours} />
            </div>

            {/* Chart */}
            <LiveChart
              readings={historicalReadings}
              realtimeReadings={realtimeReadings}
              windowHours={zoomHours}
            />



          </>
        )}

        {/* Last update timestamp for mobile (inline in header on desktop) */}
        {lastUpdate && (
          <p className="text-xs text-[#5a6a7a] text-center mt-6 sm:hidden">
            Last updated: {lastUpdate.toLocaleTimeString()}
            {signalRConnected ? " (live)" : " (polling)"}
          </p>
        )}
      </div>

      <footer className="text-center text-xs text-[#5a6a7a] py-4 pb-20 md:pb-4">
        NOT FOR MEDICAL USE -- Proof of concept only
      </footer>
    </main>
  );
}
