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

export const DEFAULT_TTL = 7776000; // 90 days in seconds
