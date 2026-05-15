interface ValidationError {
  code: string;
  message: string;
}

export function validateIngestRequest(body: unknown): ValidationError | null {
  if (!body || typeof body !== "object") {
    return { code: "INVALID_REQUEST", message: "Request body is required" };
  }

  const b = body as Record<string, unknown>;

  if (typeof b.patientId !== "string" || b.patientId.length === 0) {
    return { code: "INVALID_REQUEST", message: "patientId is required and must be a non-empty string" };
  }

  if (typeof b.spo2 !== "number" || b.spo2 < 0 || b.spo2 > 100) {
    return { code: "INVALID_REQUEST", message: "spo2 is required and must be 0-100" };
  }

  if (typeof b.heartRate !== "number" || b.heartRate < 0 || b.heartRate > 300) {
    return { code: "INVALID_REQUEST", message: "heartRate is required and must be 0-300" };
  }

  if (typeof b.batteryLevel !== "number" || b.batteryLevel < 0 || b.batteryLevel > 100) {
    return { code: "INVALID_REQUEST", message: "batteryLevel is required and must be 0-100" };
  }

  if (typeof b.timestamp !== "string" || isNaN(Date.parse(b.timestamp))) {
    return { code: "INVALID_REQUEST", message: "timestamp is required and must be a valid ISO 8601 date" };
  }

  return null;
}

export function validateCreatePatientRequest(body: unknown): ValidationError | null {
  if (!body || typeof body !== "object") {
    return { code: "INVALID_REQUEST", message: "Request body is required" };
  }

  const b = body as Record<string, unknown>;

  if (typeof b.name !== "string" || b.name.length === 0) {
    return { code: "INVALID_REQUEST", message: "name is required and must be a non-empty string" };
  }

  if (typeof b.deviceMac !== "string" || b.deviceMac.length === 0) {
    return { code: "INVALID_REQUEST", message: "deviceMac is required and must be a non-empty string" };
  }

  return null;
}
