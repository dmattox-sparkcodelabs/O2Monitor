export interface Reading {
  id: string;
  patientId: string;
  timestamp: string;
  spo2: number;
  heartRate: number;
  batteryLevel: number;
  movement: number;
  source: string;
  deviceId: string;
  ttl: number;
}

export interface IngestReadingRequest {
  patientId: string;
  spo2: number;
  heartRate: number;
  batteryLevel: number;
  movement?: number;
  timestamp: string;
  source?: string;
  deviceId?: string;
}

export interface Patient {
  id: string;
  name: string;
  deviceMac: string;
  deviceName?: string;
  alertConfig: AlertConfig;
  createdAt: string;
  createdBy: string;
}

export interface AlertConfig {
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

export interface ApiError {
  error: {
    code: string;
    message: string;
  };
}

export interface Alert {
  id: string;
  patientId: string;
  alertType: string;
  severity: string;
  message: string;
  spo2: number | null;
  heartRate: number | null;
  timestamp: string;
  resolvedAt: string | null;
  pagerdutyDedupKey: string;
  ttl: number;
}

export const DEFAULT_TTL = 7776000; // 90 days in seconds

export const DEFAULT_ALERT_CONFIG: AlertConfig = {
  spo2CriticalThreshold: 90,
  spo2CriticalDurationSec: 30,
  spo2WarningThreshold: 92,
  spo2WarningDurationSec: 60,
  hrHighThreshold: 120,
  hrLowThreshold: 50,
  hrDurationSec: 60,
  batteryWarningThreshold: 25,
  batteryCriticalThreshold: 10,
  disconnectAlertSec: 120,
  pagerdutyRoutingKey: "",
  resendIntervalSec: 300,
};
