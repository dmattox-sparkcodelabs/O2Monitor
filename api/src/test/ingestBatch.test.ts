import { validateBatchRequest } from "../shared/validation";

describe("validateBatchRequest", () => {
  const validReading = {
    patientId: "p1",
    spo2: 97,
    heartRate: 72,
    batteryLevel: 85,
    timestamp: "2026-05-15T09:30:00Z",
  };

  it("accepts a valid batch with one reading", () => {
    const result = validateBatchRequest({ readings: [validReading] });
    expect(result).toBeNull();
  });

  it("accepts a valid batch with multiple readings", () => {
    const result = validateBatchRequest({
      readings: [validReading, { ...validReading, timestamp: "2026-05-15T09:30:05Z" }],
    });
    expect(result).toBeNull();
  });

  it("rejects null body", () => {
    const result = validateBatchRequest(null);
    expect(result).not.toBeNull();
  });

  it("rejects missing readings array", () => {
    const result = validateBatchRequest({});
    expect(result).not.toBeNull();
    expect(result!.message).toContain("readings");
  });

  it("rejects empty readings array", () => {
    const result = validateBatchRequest({ readings: [] });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("empty");
  });

  it("rejects readings that are not an array", () => {
    const result = validateBatchRequest({ readings: "not-array" });
    expect(result).not.toBeNull();
  });

  it("rejects reading with missing patientId", () => {
    const result = validateBatchRequest({ readings: [{ spo2: 97, heartRate: 72, batteryLevel: 85, timestamp: "2026-05-15T09:30:00Z" }] });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("patientId");
  });

  it("rejects reading with invalid spo2", () => {
    const result = validateBatchRequest({ readings: [{ ...validReading, spo2: 150 }] });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("spo2");
  });
});
