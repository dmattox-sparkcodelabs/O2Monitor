import { Reading, AlertConfig, Alert } from "./types";

export interface AlertAction {
  action: "create" | "resolve";
  alertType: string;
  severity: string;
  message: string;
  spo2: number | null;
  heartRate: number | null;
  alertId?: string;
}

function unresolvedOfType(alerts: Alert[], alertType: string): Alert | undefined {
  return alerts.find((a) => a.alertType === alertType && a.resolvedAt === null);
}

function allBelowThreshold(readings: Reading[], threshold: number, field: "spo2"): boolean {
  return readings.length > 0 && readings.every((r) => r[field] < threshold);
}

function durationCovered(readings: Reading[], durationSec: number): boolean {
  if (readings.length < 2) return false;
  const timestamps = readings.map((r) => new Date(r.timestamp).getTime()).sort((a, b) => a - b);
  const span = (timestamps[timestamps.length - 1] - timestamps[0]) / 1000;
  return span >= durationSec;
}

export function evaluateSpo2Critical(
  current: Reading,
  recentReadings: Reading[],
  config: AlertConfig,
  unresolvedAlerts: Alert[]
): AlertAction | null {
  const threshold = config.spo2CriticalThreshold;
  const existing = unresolvedOfType(unresolvedAlerts, "spo2_critical");

  if (current.spo2 >= threshold) {
    if (existing) {
      return {
        action: "resolve",
        alertType: "spo2_critical",
        severity: "critical",
        message: `SpO2 recovered to ${current.spo2}%`,
        spo2: current.spo2,
        heartRate: current.heartRate,
        alertId: existing.id,
      };
    }
    return null;
  }

  if (existing) return null;

  if (
    allBelowThreshold(recentReadings, threshold, "spo2") &&
    durationCovered(recentReadings, config.spo2CriticalDurationSec)
  ) {
    return {
      action: "create",
      alertType: "spo2_critical",
      severity: "critical",
      message: `SpO2 dropped to ${current.spo2}% for ${config.spo2CriticalDurationSec}s`,
      spo2: current.spo2,
      heartRate: current.heartRate,
    };
  }

  return null;
}
