import { PatientStatus } from "./types";

export async function fetchPatientStatus(patientId: string): Promise<PatientStatus> {
  const res = await fetch(`/api/patients/${patientId}/status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch status: ${res.status}`);
  }
  return res.json();
}
