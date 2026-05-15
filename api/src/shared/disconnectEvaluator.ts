import { AlertConfig, Alert } from "./types";
import { AlertAction } from "./alertEvaluator";

function unresolvedDisconnect(alerts: Alert[]): Alert | undefined {
  return alerts.find((a) => a.alertType === "disconnect" && a.resolvedAt === null);
}

export function evaluateDisconnect(
  latestReadingTimestamp: string | null,
  config: AlertConfig,
  unresolvedAlerts: Alert[]
): AlertAction | null {
  const existing = unresolvedDisconnect(unresolvedAlerts);

  if (!latestReadingTimestamp) {
    if (existing) return null;
    return {
      action: "create",
      alertType: "disconnect",
      severity: "warning",
      message: "Device disconnected — no readings received",
      spo2: null,
      heartRate: null,
    };
  }

  const ageSeconds = (Date.now() - new Date(latestReadingTimestamp).getTime()) / 1000;

  if (ageSeconds > config.disconnectAlertSec) {
    if (existing) return null;
    return {
      action: "create",
      alertType: "disconnect",
      severity: "warning",
      message: `Device disconnected — no readings for ${Math.round(ageSeconds)}s`,
      spo2: null,
      heartRate: null,
    };
  }

  return null;
}

export function evaluateReconnect(unresolvedAlerts: Alert[]): AlertAction | null {
  const existing = unresolvedDisconnect(unresolvedAlerts);
  if (!existing) return null;

  return {
    action: "resolve",
    alertType: "disconnect",
    severity: "warning",
    message: "Device reconnected",
    spo2: null,
    heartRate: null,
    alertId: existing.id,
  };
}
