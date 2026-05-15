"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchPatient, updatePatient } from "@/lib/api";
import { usePatient } from "@/hooks/usePatient";
import ThresholdEditor from "@/components/ThresholdEditor";
import Nav from "@/components/Nav";

interface PatientFull {
  id: string;
  name: string;
  deviceMac: string;
  deviceName?: string;
  alertConfig: {
    spo2CriticalThreshold: number;
    spo2CriticalDurationSec: number;
    spo2WarningThreshold: number;
    spo2WarningDurationSec: number;
    hrHighThreshold: number;
    hrLowThreshold: number;
    hrDurationSec: number;
    batteryWarningThreshold: number;
    batteryCriticalThreshold: number;
    disconnectAlertSec: number;
    pagerdutyRoutingKey: string;
    resendIntervalSec: number;
  };
}

export default function SettingsPage() {
  const { selectedId, loading: patientsLoading } = usePatient();
  const [patient, setPatient] = useState<PatientFull | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!selectedId) return;
    try {
      const data = await fetchPatient(selectedId) as PatientFull;
      setPatient(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }, [selectedId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async () => {
    if (!patient || !selectedId) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await updatePatient(selectedId, {
        name: patient.name,
        deviceMac: patient.deviceMac,
        deviceName: patient.deviceName,
        alertConfig: patient.alertConfig,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (patientsLoading || !patient) {
    return (
      <main className="flex-1 bg-gray-900 text-white flex items-center justify-center">
        <div className="text-gray-500">Loading...</div>
      </main>
    );
  }

  return (
    <main className="flex-1 bg-gray-900 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-xl font-semibold">Settings</h1>
            <Nav />
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto p-6 space-y-8">
        {error && (
          <div className="bg-red-900/50 border border-red-700 rounded-lg px-4 py-3 text-red-200">{error}</div>
        )}
        {saved && (
          <div className="bg-green-900/50 border border-green-700 rounded-lg px-4 py-3 text-green-200">Settings saved.</div>
        )}

        <section>
          <h2 className="text-lg font-medium mb-4">Patient Info</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Name</label>
              <input
                type="text"
                value={patient.name}
                onChange={(e) => setPatient({ ...patient, name: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Device MAC</label>
              <input
                type="text"
                value={patient.deviceMac}
                onChange={(e) => setPatient({ ...patient, deviceMac: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              />
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-lg font-medium mb-4">Alert Thresholds</h2>
          <ThresholdEditor
            config={patient.alertConfig}
            onChange={(alertConfig) => setPatient({ ...patient, alertConfig })}
          />
        </section>

        <section>
          <h2 className="text-lg font-medium mb-4">PagerDuty</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Routing Key</label>
              <input
                type="password"
                value={patient.alertConfig.pagerdutyRoutingKey}
                onChange={(e) => setPatient({
                  ...patient,
                  alertConfig: { ...patient.alertConfig, pagerdutyRoutingKey: e.target.value },
                })}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                placeholder="Enter PagerDuty routing key"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Resend Interval (seconds)</label>
              <input
                type="number"
                value={patient.alertConfig.resendIntervalSec}
                onChange={(e) => setPatient({
                  ...patient,
                  alertConfig: { ...patient.alertConfig, resendIntervalSec: parseInt(e.target.value) || 300 },
                })}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              />
            </div>
          </div>
        </section>

        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium px-6 py-2 rounded transition-colors"
          >
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>
      </div>
    </main>
  );
}
