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

export interface ActiveAlert {
  id: string;
  alertType: string;
  severity: string;
  message: string;
  timestamp: string;
}

export interface PatientStatus {
  patientId: string;
  patientName: string;
  latestReading: LatestReading | null;
  secondsSinceReading: number | null;
  deviceOnline: boolean;
  activeAlerts: ActiveAlert[];
}

export interface ReadingRecord {
  id: string;
  timestamp: string;
  spo2: number;
  heartRate: number;
  batteryLevel: number;
  movement: number;
  source: string;
  deviceId: string;
}

export interface ReadingsResponse {
  readings: ReadingRecord[];
  count: number;
}

export interface AlertRecord {
  id: string;
  alertType: string;
  severity: string;
  message: string;
  spo2: number | null;
  heartRate: number | null;
  timestamp: string;
  resolvedAt: string | null;
}

export interface AlertsResponse {
  alerts: AlertRecord[];
}

export interface NightlySummary {
  nightDate: string;
  readingCount: number;
  durationSeconds: number;
  spo2Avg: number;
  spo2Min: number;
  spo2Max: number;
  hrAvg: number;
  hrMin: number;
  hrMax: number;
  timeBelow90Seconds: number;
  timeBelow88Seconds: number;
  pctBelow90: number;
  pctBelow88: number;
}

export interface SummariesResponse {
  summaries: NightlySummary[];
}
