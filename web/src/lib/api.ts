import { PatientStatus, PatientSummary, ReadingsResponse } from "./types";

const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

function authHeaders(): Record<string, string> {
  if (!API_KEY) return {};
  return { "x-api-key": API_KEY };
}

export function getApiKey(): string {
  return API_KEY;
}

export async function fetchPatientStatus(patientId: string): Promise<PatientStatus> {
  const res = await fetch(`/api/patients/${patientId}/status`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch status: ${res.status}`);
  }
  return res.json();
}

export async function fetchPatients(): Promise<PatientSummary[]> {
  const res = await fetch("/api/patients", {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch patients: ${res.status}`);
  }
  return res.json();
}

export async function fetchReadings(patientId: string, hours: number = 1): Promise<ReadingsResponse> {
  const res = await fetch(`/api/patients/${patientId}/readings?hours=${hours}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch readings: ${res.status}`);
  }
  return res.json();
}

export async function negotiateSignalR(): Promise<{ url: string; accessToken: string }> {
  const res = await fetch("/api/negotiate", {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Negotiate failed: ${res.status}`);
  }
  return res.json();
}
