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

function durationCovered(readings: Reading[], durationSec: number): boolean {
  if (readings.length < 2) return false;
  const timestamps = readings.map((r) => new Date(r.timestamp).getTime()).sort((a, b) => a - b);
  const span = (timestamps[timestamps.length - 1] - timestamps[0]) / 1000;
  return span >= durationSec;
}

function evaluateDurationAlert(
  alertType: string,
  severity: string,
  current: Reading,
  recentReadings: Reading[],
  durationSec: number,
  unresolvedAlerts: Alert[],
  isViolating: (r: Reading) => boolean,
  createMessage: string,
  resolveMessage: string
): AlertAction | null {
  const existing = unresolvedOfType(unresolvedAlerts, alertType);

  if (!isViolating(current)) {
    if (existing) {
      return {
        action: "resolve", alertType, severity, message: resolveMessage,
        spo2: current.spo2, heartRate: current.heartRate, alertId: existing.id,
      };
    }
    return null;
  }

  if (existing) return null;

  const allViolating = recentReadings.length > 0 && recentReadings.every(isViolating);
  if (allViolating && durationCovered(recentReadings, durationSec)) {
    return {
      action: "create", alertType, severity, message: createMessage,
      spo2: current.spo2, heartRate: current.heartRate,
    };
  }

  return null;
}

function evaluateInstantAlert(
  alertType: string,
  severity: string,
  current: Reading,
  unresolvedAlerts: Alert[],
  isViolating: (r: Reading) => boolean,
  createMessage: string,
  resolveMessage: string
): AlertAction | null {
  const existing = unresolvedOfType(unresolvedAlerts, alertType);

  if (!isViolating(current)) {
    if (existing) {
      return {
        action: "resolve", alertType, severity, message: resolveMessage,
        spo2: current.spo2, heartRate: current.heartRate, alertId: existing.id,
      };
    }
    return null;
  }

  if (existing) return null;

  return {
    action: "create", alertType, severity, message: createMessage,
    spo2: current.spo2, heartRate: current.heartRate,
  };
}

export function evaluateSpo2Critical(
  current: Reading, recentReadings: Reading[], config: AlertConfig, unresolvedAlerts: Alert[]
): AlertAction | null {
  return evaluateDurationAlert(
    "spo2_critical", "critical", current, recentReadings,
    config.spo2CriticalDurationSec, unresolvedAlerts,
    (r) => r.spo2 < config.spo2CriticalThreshold,
    `SpO2 dropped to ${current.spo2}% for ${config.spo2CriticalDurationSec}s`,
    `SpO2 recovered to ${current.spo2}%`
  );
}

export function evaluateSpo2Warning(
  current: Reading, recentReadings: Reading[], config: AlertConfig, unresolvedAlerts: Alert[]
): AlertAction | null {
  return evaluateDurationAlert(
    "spo2_warning", "warning", current, recentReadings,
    config.spo2WarningDurationSec, unresolvedAlerts,
    (r) => r.spo2 < config.spo2WarningThreshold,
    `SpO2 at ${current.spo2}% for ${config.spo2WarningDurationSec}s`,
    `SpO2 recovered to ${current.spo2}%`
  );
}

export function evaluateHrHigh(
  current: Reading, recentReadings: Reading[], config: AlertConfig, unresolvedAlerts: Alert[]
): AlertAction | null {
  return evaluateDurationAlert(
    "hr_high", "high", current, recentReadings,
    config.hrDurationSec, unresolvedAlerts,
    (r) => r.heartRate > config.hrHighThreshold,
    `Heart rate elevated at ${current.heartRate} BPM for ${config.hrDurationSec}s`,
    `Heart rate recovered to ${current.heartRate} BPM`
  );
}

export function evaluateHrLow(
  current: Reading, recentReadings: Reading[], config: AlertConfig, unresolvedAlerts: Alert[]
): AlertAction | null {
  return evaluateDurationAlert(
    "hr_low", "high", current, recentReadings,
    config.hrDurationSec, unresolvedAlerts,
    (r) => r.heartRate < config.hrLowThreshold,
    `Heart rate low at ${current.heartRate} BPM for ${config.hrDurationSec}s`,
    `Heart rate recovered to ${current.heartRate} BPM`
  );
}

export function evaluateBatteryWarning(
  current: Reading, config: AlertConfig, unresolvedAlerts: Alert[]
): AlertAction | null {
  return evaluateInstantAlert(
    "battery_warning", "warning", current, unresolvedAlerts,
    (r) => r.batteryLevel <= config.batteryWarningThreshold,
    `Battery low at ${current.batteryLevel}%`,
    `Battery recovered to ${current.batteryLevel}%`
  );
}

export function evaluateBatteryCritical(
  current: Reading, config: AlertConfig, unresolvedAlerts: Alert[]
): AlertAction | null {
  return evaluateInstantAlert(
    "battery_critical", "critical", current, unresolvedAlerts,
    (r) => r.batteryLevel <= config.batteryCriticalThreshold,
    `Battery critical at ${current.batteryLevel}%`,
    `Battery recovered to ${current.batteryLevel}%`
  );
}

export function evaluateAllAlerts(
  current: Reading, recentReadings: Reading[], config: AlertConfig, unresolvedAlerts: Alert[]
): AlertAction[] {
  const actions: AlertAction[] = [];

  const checks = [
    evaluateSpo2Critical(current, recentReadings, config, unresolvedAlerts),
    evaluateSpo2Warning(current, recentReadings, config, unresolvedAlerts),
    evaluateHrHigh(current, recentReadings, config, unresolvedAlerts),
    evaluateHrLow(current, recentReadings, config, unresolvedAlerts),
    evaluateBatteryWarning(current, config, unresolvedAlerts),
    evaluateBatteryCritical(current, config, unresolvedAlerts),
  ];

  for (const action of checks) {
    if (action) actions.push(action);
  }

  return actions;
}
