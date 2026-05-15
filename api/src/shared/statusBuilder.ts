import { Reading, Patient, Alert } from "./types";

const ONLINE_THRESHOLD_SEC = 120;

export interface ActiveAlertSummary {
  id: string;
  alertType: string;
  severity: string;
  message: string;
  timestamp: string;
}

export interface StatusResponse {
  patientId: string;
  patientName: string;
  latestReading: {
    spo2: number;
    heartRate: number;
    batteryLevel: number;
    timestamp: string;
    deviceId: string;
  } | null;
  secondsSinceReading: number | null;
  deviceOnline: boolean;
  activeAlerts: ActiveAlertSummary[];
}

export function buildStatusResponse(
  patient: Patient,
  latestReading: Reading | null,
  unresolvedAlerts: Alert[],
  now: Date
): StatusResponse {
  const activeAlerts: ActiveAlertSummary[] = unresolvedAlerts.map((a) => ({
    id: a.id,
    alertType: a.alertType,
    severity: a.severity,
    message: a.message,
    timestamp: a.timestamp,
  }));

  if (!latestReading) {
    return {
      patientId: patient.id,
      patientName: patient.name,
      latestReading: null,
      secondsSinceReading: null,
      deviceOnline: false,
      activeAlerts,
    };
  }

  const readingTime = new Date(latestReading.timestamp).getTime();
  const secondsSinceReading = Math.round((now.getTime() - readingTime) / 1000);

  return {
    patientId: patient.id,
    patientName: patient.name,
    latestReading: {
      spo2: latestReading.spo2,
      heartRate: latestReading.heartRate,
      batteryLevel: latestReading.batteryLevel,
      timestamp: latestReading.timestamp,
      deviceId: latestReading.deviceId,
    },
    secondsSinceReading,
    deviceOnline: secondsSinceReading <= ONLINE_THRESHOLD_SEC,
    activeAlerts,
  };
}
