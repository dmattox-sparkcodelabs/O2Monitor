import { PatientStatus, PatientSummary, ReadingsResponse, AlertsResponse } from "./types";

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

export async function fetchPatient(patientId: string): Promise<unknown> {
  const res = await fetch(`/api/patients/${patientId}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch patient: ${res.status}`);
  return res.json();
}

export async function updatePatient(patientId: string, body: Record<string, unknown>): Promise<unknown> {
  const res = await fetch(`/api/patients/${patientId}`, {
    method: "PUT",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Failed to update patient: ${res.status}`);
  return res.json();
}

export async function fetchAlerts(patientId: string, days: number = 7, status?: string): Promise<AlertsResponse> {
  let url = `/api/patients/${patientId}/alerts?days=${days}`;
  if (status) url += `&status=${status}`;
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error(`Failed to fetch alerts: ${res.status}`);
  }
  return res.json();
}

export async function fetchAccess(patientId: string): Promise<{ id: string; email: string; role: string; createdAt: string }[]> {
  const res = await fetch(`/api/patients/${patientId}/access`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch access: ${res.status}`);
  return res.json();
}

export async function grantAccess(patientId: string, email: string, role: string): Promise<unknown> {
  const res = await fetch(`/api/patients/${patientId}/access`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ email, role }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: { message: `HTTP ${res.status}` } }));
    throw new Error(err.error?.message ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function revokeAccess(patientId: string, accessId: string): Promise<void> {
  const res = await fetch(`/api/patients/${patientId}/access/${accessId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok && res.status !== 204) throw new Error(`Failed to revoke: ${res.status}`);
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
