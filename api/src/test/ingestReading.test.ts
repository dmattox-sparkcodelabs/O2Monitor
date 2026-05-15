import { validateIngestRequest } from "../shared/validation";

describe("validateIngestRequest", () => {
  const validRequest = {
    patientId: "test-patient-1",
    spo2: 97,
    heartRate: 72,
    batteryLevel: 85,
    movement: 0,
    timestamp: "2026-05-15T09:30:00Z",
    source: "live",
    deviceId: "curl-test",
  };

  it("accepts a valid request", () => {
    const result = validateIngestRequest(validRequest);
    expect(result).toBeNull();
  });

  it("accepts request with only required fields", () => {
    const minimal = {
      patientId: "test-patient-1",
      spo2: 97,
      heartRate: 72,
      batteryLevel: 85,
      timestamp: "2026-05-15T09:30:00Z",
    };
    const result = validateIngestRequest(minimal);
    expect(result).toBeNull();
  });

  it("rejects null body", () => {
    const result = validateIngestRequest(null);
    expect(result).not.toBeNull();
    expect(result!.code).toBe("INVALID_REQUEST");
  });

  it("rejects undefined body", () => {
    const result = validateIngestRequest(undefined);
    expect(result).not.toBeNull();
    expect(result!.code).toBe("INVALID_REQUEST");
  });

  it("rejects empty object", () => {
    const result = validateIngestRequest({});
    expect(result).not.toBeNull();
    expect(result!.message).toContain("patientId");
  });

  it("rejects missing patientId", () => {
    const { patientId, ...rest } = validRequest;
    const result = validateIngestRequest(rest);
    expect(result).not.toBeNull();
    expect(result!.message).toContain("patientId");
  });

  it("rejects missing spo2", () => {
    const { spo2, ...rest } = validRequest;
    const result = validateIngestRequest(rest);
    expect(result).not.toBeNull();
    expect(result!.message).toContain("spo2");
  });

  it("rejects missing heartRate", () => {
    const { heartRate, ...rest } = validRequest;
    const result = validateIngestRequest(rest);
    expect(result).not.toBeNull();
    expect(result!.message).toContain("heartRate");
  });

  it("rejects missing batteryLevel", () => {
    const { batteryLevel, ...rest } = validRequest;
    const result = validateIngestRequest(rest);
    expect(result).not.toBeNull();
    expect(result!.message).toContain("batteryLevel");
  });

  it("rejects missing timestamp", () => {
    const { timestamp, ...rest } = validRequest;
    const result = validateIngestRequest(rest);
    expect(result).not.toBeNull();
    expect(result!.message).toContain("timestamp");
  });

  it("rejects spo2 out of range (negative)", () => {
    const result = validateIngestRequest({ ...validRequest, spo2: -1 });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("spo2");
  });

  it("rejects spo2 out of range (>100)", () => {
    const result = validateIngestRequest({ ...validRequest, spo2: 101 });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("spo2");
  });

  it("rejects heartRate out of range (negative)", () => {
    const result = validateIngestRequest({ ...validRequest, heartRate: -1 });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("heartRate");
  });

  it("rejects heartRate out of range (>300)", () => {
    const result = validateIngestRequest({ ...validRequest, heartRate: 301 });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("heartRate");
  });

  it("rejects batteryLevel out of range", () => {
    const result = validateIngestRequest({ ...validRequest, batteryLevel: 101 });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("batteryLevel");
  });

  it("rejects non-string patientId", () => {
    const result = validateIngestRequest({ ...validRequest, patientId: 123 });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("patientId");
  });

  it("rejects empty string patientId", () => {
    const result = validateIngestRequest({ ...validRequest, patientId: "" });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("patientId");
  });

  it("rejects invalid timestamp format", () => {
    const result = validateIngestRequest({ ...validRequest, timestamp: "not-a-date" });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("timestamp");
  });

  it("accepts boundary spo2 values (0 and 100)", () => {
    expect(validateIngestRequest({ ...validRequest, spo2: 0 })).toBeNull();
    expect(validateIngestRequest({ ...validRequest, spo2: 100 })).toBeNull();
  });

  it("accepts boundary heartRate values (0 and 300)", () => {
    expect(validateIngestRequest({ ...validRequest, heartRate: 0 })).toBeNull();
    expect(validateIngestRequest({ ...validRequest, heartRate: 300 })).toBeNull();
  });
});
