"use client";

/**
 * AlertBanner — Warning bars with red/orange/yellow left border accent.
 * Matches the Windows viewer disclaimer bar style.
 */

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

function severityStyles(severity: string): string {
  switch (severity) {
    case "critical": return "bg-[#2a1a1a] border-l-[#ff6b6b]";
    case "high": return "bg-[#2a2218] border-l-[#ffa94d]";
    case "warning": return "bg-[#2a2818] border-l-[#ffd43b]";
    default: return "bg-[#1a2332] border-l-[#4dabf7]";
  }
}

function severityTextColor(severity: string): string {
  switch (severity) {
    case "critical": return "text-[#ffa8a8]";
    case "high": return "text-[#ffd8a8]";
    case "warning": return "text-[#ffe066]";
    default: return "text-[#a5d8ff]";
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
          className={`${severityStyles(alert.severity)} border-l-[3px] border border-[#2a3a52] rounded-lg px-4 py-3 flex items-center justify-between`}
        >
          <div className="flex items-center gap-3">
            <span className={`text-[11px] font-bold uppercase tracking-wider ${severityTextColor(alert.severity)}`}>
              {severityLabel(alert.severity)}
            </span>
            <span className={`font-medium text-sm ${severityTextColor(alert.severity)}`}>
              {alert.message}
            </span>
          </div>
          <span className="text-xs text-[#8a96a7]">{formatTime(alert.timestamp)}</span>
        </div>
      ))}
    </div>
  );
}
