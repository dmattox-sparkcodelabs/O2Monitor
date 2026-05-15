export interface LatestReading {
  patientId?: string;
  spo2: number;
  heartRate: number;
  batteryLevel: number;
  timestamp: string;
  deviceId?: string;
}

export interface PatientSummary {
  id: string;
  name: string;
  deviceMac: string;
  deviceName?: string;
}

export interface PatientStatus {
  patientId: string;
  patientName: string;
  latestReading: LatestReading | null;
  secondsSinceReading: number | null;
  deviceOnline: boolean;
  activeAlerts: unknown[];
}
