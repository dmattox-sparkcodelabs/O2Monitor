"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchPatientStatus, fetchReadings } from "@/lib/api";
import { PatientStatus, LatestReading, ReadingRecord } from "@/lib/types";
import { usePatient } from "@/hooks/usePatient";
import { useSignalR } from "@/hooks/useSignalR";
import VitalsCard, { spo2Color, hrColor, batteryColor } from "@/components/VitalsCard";
import ConnectionStatus from "@/components/ConnectionStatus";
import PatientSelector from "@/components/PatientSelector";
import LiveChart from "@/components/LiveChart";
import TimeRangeToggle from "@/components/TimeRangeToggle";
import AlertBanner from "@/components/AlertBanner";
import Nav from "@/components/Nav";

const POLL_INTERVAL_MS = 15_000;

export default function Dashboard() {
  const { patients, selected, selectedId, selectPatient, loading: patientsLoading } = usePatient();
  const [status, setStatus] = useState<PatientStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [historicalReadings, setHistoricalReadings] = useState<ReadingRecord[]>([]);
  const [realtimeReadings, setRealtimeReadings] = useState<LatestReading[]>([]);
  const [chartHours, setChartHours] = useState(1);

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
    fetchReadings(selectedId, chartHours)
      .then((res) => setHistoricalReadings(res.readings))
      .catch(() => {});
  }, [selectedId, chartHours]);

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

  if (patientsLoading) {
    return (
      <main className="flex-1 bg-gray-900 text-white flex items-center justify-center">
        <div className="text-gray-500">Loading...</div>
      </main>
    );
  }

  if (patients.length === 0) {
    return (
      <main className="flex-1 bg-gray-900 text-white flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-semibold mb-4">O2 Monitor</h1>
          <p className="text-gray-400 mb-6">No patients yet — create one to get started.</p>
          <p className="text-sm text-gray-600">
            Use the API to create a patient:<br />
            <code className="text-gray-500">POST /api/patients {`{"name":"Dad","deviceMac":"..."}`}</code>
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1 bg-gray-900 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div>
              <h1 className="text-xl font-semibold">O2 Monitor</h1>
              {selected && (
                <span className="text-sm text-gray-400">{selected.name}</span>
              )}
            </div>
            <Nav />
            <PatientSelector
              patients={patients}
              selectedId={selectedId}
              onSelect={selectPatient}
            />
          </div>
          {status && (
            <ConnectionStatus
              online={status.deviceOnline}
              secondsSinceReading={status.secondsSinceReading}
            />
          )}
        </div>
      </header>

      <div className="max-w-4xl mx-auto p-6">
        {status && status.activeAlerts.length > 0 && (
          <AlertBanner alerts={status.activeAlerts} />
        )}

        {error && (
          <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 mb-6 text-red-200">
            {error}
          </div>
        )}

        {!status && !error && selectedId && (
          <div className="text-center text-gray-500 py-20">Loading vitals...</div>
        )}

        {status && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <VitalsCard
                label="SpO2"
                value={reading?.spo2 ?? null}
                unit="%"
                colorFn={spo2Color}
                large
              />
              <VitalsCard
                label="Heart Rate"
                value={reading?.heartRate ?? null}
                unit="bpm"
                colorFn={hrColor}
              />
              <VitalsCard
                label="Battery"
                value={reading?.batteryLevel ?? null}
                unit="%"
                colorFn={batteryColor}
              />
            </div>

            <div className="flex justify-end mt-6 mb-2">
              <TimeRangeToggle value={chartHours} onChange={setChartHours} />
            </div>
            <LiveChart
              readings={historicalReadings}
              realtimeReadings={realtimeReadings}
            />
          </>
        )}

        {lastUpdate && (
          <p className="text-xs text-gray-600 text-center mt-6">
            Last updated: {lastUpdate.toLocaleTimeString()}
            {signalRConnected ? " (live)" : " (polling)"}
          </p>
        )}
      </div>

      <footer className="text-center text-xs text-gray-700 py-4 pb-20 md:pb-4">
        NOT FOR MEDICAL USE — Proof of concept only
      </footer>
    </main>
  );
}
