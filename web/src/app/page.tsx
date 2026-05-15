"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchPatientStatus } from "@/lib/api";
import { PatientStatus, LatestReading } from "@/lib/types";
import { useSignalR } from "@/hooks/useSignalR";
import VitalsCard, { spo2Color, hrColor, batteryColor } from "@/components/VitalsCard";
import ConnectionStatus from "@/components/ConnectionStatus";

const PATIENT_ID = "test-patient-1";
const POLL_INTERVAL_MS = 15_000;

export default function Dashboard() {
  const [status, setStatus] = useState<PatientStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const poll = useCallback(async () => {
    try {
      const data = await fetchPatientStatus(PATIENT_ID);
      setStatus(data);
      setError(null);
      setLastUpdate(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch");
    }
  }, []);

  useEffect(() => {
    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [poll]);

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
    setLastUpdate(new Date());
  }, []);

  const { connected: signalRConnected } = useSignalR({
    patientId: PATIENT_ID,
    onNewReading: handleNewReading,
  });

  const reading = status?.latestReading ?? null;

  return (
    <main className="flex-1 bg-gray-900 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">O2 Monitor</h1>
            {status && (
              <span className="text-sm text-gray-400">{status.patientName}</span>
            )}
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
        {error && (
          <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 mb-6 text-red-200">
            {error}
          </div>
        )}

        {!status && !error && (
          <div className="text-center text-gray-500 py-20">Loading...</div>
        )}

        {status && (
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
        )}

        {lastUpdate && (
          <p className="text-xs text-gray-600 text-center mt-6">
            Last updated: {lastUpdate.toLocaleTimeString()}
            {signalRConnected ? " (live)" : " (polling)"}
          </p>
        )}
      </div>

      <footer className="text-center text-xs text-gray-700 py-4">
        NOT FOR MEDICAL USE — Proof of concept only
      </footer>
    </main>
  );
}
