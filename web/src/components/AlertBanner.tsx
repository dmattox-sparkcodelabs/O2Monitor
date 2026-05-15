"use client";

interface AlertSummary {
  id: string;
  alertType: string;
  severity: string;
  message: string;
  timestamp: string;
}

interface AlertBannerProps {
  alerts: AlertSummary[];
}

function severityColor(severity: string): string {
  switch (severity) {
    case "critical": return "bg-red-700 border-red-500";
    case "high": return "bg-orange-700 border-orange-500";
    case "warning": return "bg-yellow-700 border-yellow-500";
    default: return "bg-blue-700 border-blue-500";
  }
}

function severityLabel(severity: string): string {
  return severity.charAt(0).toUpperCase() + severity.slice(1);
}

function formatTime(ts: string): string {
  return new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function AlertBanner({ alerts }: AlertBannerProps) {
  if (alerts.length === 0) return null;

  return (
    <div className="space-y-2 mb-6">
      {alerts.map((alert) => (
        <div
          key={alert.id}
          className={`${severityColor(alert.severity)} border rounded-lg px-4 py-3 text-white flex items-center justify-between`}
        >
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold uppercase tracking-wider opacity-80">
              {severityLabel(alert.severity)}
            </span>
            <span className="font-medium">{alert.message}</span>
          </div>
          <span className="text-xs opacity-70">{formatTime(alert.timestamp)}</span>
        </div>
      ))}
    </div>
  );
}
