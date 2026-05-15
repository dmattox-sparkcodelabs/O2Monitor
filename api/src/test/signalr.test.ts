import { buildNewReadingMessage } from "../shared/signalr";

describe("buildNewReadingMessage", () => {
  it("creates a message targeting the correct patient group", () => {
    const msg = buildNewReadingMessage("patient-123", {
      spo2: 97,
      heartRate: 72,
      batteryLevel: 85,
      timestamp: "2026-05-15T09:30:00Z",
    });

    expect(msg.target).toBe("newReading");
    expect(msg.groupName).toBe("patient:patient-123");
    expect(msg.arguments).toHaveLength(1);
  });

  it("includes all reading fields in the payload", () => {
    const msg = buildNewReadingMessage("patient-123", {
      spo2: 91,
      heartRate: 110,
      batteryLevel: 20,
      timestamp: "2026-05-15T10:00:00Z",
    });

    const payload = msg.arguments[0] as Record<string, unknown>;
    expect(payload.patientId).toBe("patient-123");
    expect(payload.spo2).toBe(91);
    expect(payload.heartRate).toBe(110);
    expect(payload.batteryLevel).toBe(20);
    expect(payload.timestamp).toBe("2026-05-15T10:00:00Z");
  });

  it("does not include extra fields", () => {
    const msg = buildNewReadingMessage("p1", {
      spo2: 97,
      heartRate: 72,
      batteryLevel: 85,
      timestamp: "2026-05-15T09:30:00Z",
    });

    const payload = msg.arguments[0] as Record<string, unknown>;
    const keys = Object.keys(payload).sort();
    expect(keys).toEqual(["batteryLevel", "heartRate", "patientId", "spo2", "timestamp"]);
  });
});
