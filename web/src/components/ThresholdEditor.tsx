"use client";

interface AlertConfig {
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
}

interface ThresholdEditorProps {
  config: AlertConfig;
  onChange: (config: AlertConfig) => void;
}

interface Row {
  label: string;
  field: keyof AlertConfig;
  unit: string;
  durationField?: keyof AlertConfig;
  severity: string;
}

const rows: Row[] = [
  { label: "SpO2 Critical", field: "spo2CriticalThreshold", unit: "% below", durationField: "spo2CriticalDurationSec", severity: "Critical" },
  { label: "SpO2 Warning", field: "spo2WarningThreshold", unit: "% below", durationField: "spo2WarningDurationSec", severity: "Warning" },
  { label: "HR High", field: "hrHighThreshold", unit: "BPM above", durationField: "hrDurationSec", severity: "High" },
  { label: "HR Low", field: "hrLowThreshold", unit: "BPM below", durationField: "hrDurationSec", severity: "High" },
  { label: "Battery Warning", field: "batteryWarningThreshold", unit: "% at or below", severity: "Warning" },
  { label: "Battery Critical", field: "batteryCriticalThreshold", unit: "% at or below", severity: "Critical" },
  { label: "Disconnect", field: "disconnectAlertSec", unit: "seconds no data", severity: "Warning" },
];

export default function ThresholdEditor({ config, onChange }: ThresholdEditorProps) {
  function update(field: keyof AlertConfig, value: number) {
    onChange({ ...config, [field]: value });
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead className="text-xs text-gray-400 uppercase border-b border-gray-700">
          <tr>
            <th className="px-4 py-3">Alert</th>
            <th className="px-4 py-3">Threshold</th>
            <th className="px-4 py-3">Duration (s)</th>
            <th className="px-4 py-3">Severity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.field} className="border-b border-gray-800">
              <td className="px-4 py-3 font-medium">{row.label}</td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={config[row.field] as number}
                    onChange={(e) => update(row.field, parseInt(e.target.value) || 0)}
                    className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
                  />
                  <span className="text-gray-500 text-xs">{row.unit}</span>
                </div>
              </td>
              <td className="px-4 py-3">
                {row.durationField ? (
                  <input
                    type="number"
                    value={config[row.durationField] as number}
                    onChange={(e) => update(row.durationField!, parseInt(e.target.value) || 0)}
                    className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
                  />
                ) : (
                  <span className="text-gray-500">instant</span>
                )}
              </td>
              <td className="px-4 py-3 text-gray-400">{row.severity}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
