import { buildStatusResponse } from "../shared/statusBuilder";
import { Reading, Patient, Alert } from "../shared/types";

const testPatient: Patient = {
  id: "test-patient-1",
  name: "Dad (Test)",
  deviceMac: "C8:F1:6B:56:7B:F1",
  deviceName: "O2M 2781",
  alertConfig: {
    spo2CriticalThreshold: 90,
    spo2CriticalDurationSec: 30,
    spo2WarningThreshold: 92,
    spo2WarningDurationSec: 60,
    hrHighThreshold: 120,
    hrLowThreshold: 50,
    hrDurationSec: 60,
    batteryWarningThreshold: 25,
    batteryCriticalThreshold: 10,
    disconnectAlertSec: 120,
    pagerdutyRoutingKey: "",
    resendIntervalSec: 300,
  },
  createdAt: "2026-05-15T14:00:00Z",
  createdBy: "setup-script",
};

function makeReading(overrides: Partial<Reading> = {}): Reading {
  return {
    id: "reading-1",
    patientId: "test-patient-1",
    timestamp: new Date().toISOString(),
    spo2: 97,
    heartRate: 72,
    batteryLevel: 85,
    movement: 0,
    source: "live",
    deviceId: "curl-test",
    ttl: 7776000,
    ...overrides,
  };
}

describe("buildStatusResponse", () => {
  it("returns correct fields when a reading exists", () => {
    const now = new Date();
    const reading = makeReading({ timestamp: now.toISOString() });
    const result = buildStatusResponse(testPatient, reading, [], now);

    expect(result.patientId).toBe("test-patient-1");
    expect(result.patientName).toBe("Dad (Test)");
    expect(result.latestReading).not.toBeNull();
    expect(result.latestReading!.spo2).toBe(97);
    expect(result.latestReading!.heartRate).toBe(72);
    expect(result.latestReading!.batteryLevel).toBe(85);
    expect(result.latestReading!.deviceId).toBe("curl-test");
    expect(result.secondsSinceReading).toBeGreaterThanOrEqual(0);
    expect(result.secondsSinceReading).toBeLessThan(2);
    expect(result.deviceOnline).toBe(true);
    expect(result.activeAlerts).toEqual([]);
  });

  it("returns null latestReading when no readings exist", () => {
    const now = new Date();
    const result = buildStatusResponse(testPatient, null, [], now);

    expect(result.patientId).toBe("test-patient-1");
    expect(result.patientName).toBe("Dad (Test)");
    expect(result.latestReading).toBeNull();
    expect(result.secondsSinceReading).toBeNull();
    expect(result.deviceOnline).toBe(false);
  });

  it("marks device offline when reading is older than 120 seconds", () => {
    const now = new Date();
    const oldTime = new Date(now.getTime() - 130_000); // 130 seconds ago
    const reading = makeReading({ timestamp: oldTime.toISOString() });
    const result = buildStatusResponse(testPatient, reading, [], now);

    expect(result.deviceOnline).toBe(false);
    expect(result.secondsSinceReading).toBeGreaterThanOrEqual(130);
  });

  it("marks device online when reading is within 120 seconds", () => {
    const now = new Date();
    const recentTime = new Date(now.getTime() - 10_000); // 10 seconds ago
    const reading = makeReading({ timestamp: recentTime.toISOString() });
    const result = buildStatusResponse(testPatient, reading, [], now);

    expect(result.deviceOnline).toBe(true);
    expect(result.secondsSinceReading).toBeGreaterThanOrEqual(10);
    expect(result.secondsSinceReading).toBeLessThan(12);
  });

  it("marks device online at exactly 120 seconds boundary", () => {
    const now = new Date();
    const boundaryTime = new Date(now.getTime() - 120_000);
    const reading = makeReading({ timestamp: boundaryTime.toISOString() });
    const result = buildStatusResponse(testPatient, reading, [], now);

    expect(result.deviceOnline).toBe(true);
  });

  it("marks device offline at 121 seconds", () => {
    const now = new Date();
    const overTime = new Date(now.getTime() - 121_000);
    const reading = makeReading({ timestamp: overTime.toISOString() });
    const result = buildStatusResponse(testPatient, reading, [], now);

    expect(result.deviceOnline).toBe(false);
  });

  it("computes secondsSinceReading as whole number", () => {
    const now = new Date();
    const reading = makeReading({ timestamp: new Date(now.getTime() - 45_500).toISOString() });
    const result = buildStatusResponse(testPatient, reading, [], now);

    expect(Number.isInteger(result.secondsSinceReading)).toBe(true);
  });

  it("includes active alerts in response", () => {
    const now = new Date();
    const reading = makeReading({ timestamp: now.toISOString() });
    const alerts: Alert[] = [{
      id: "alert-1",
      patientId: "test-patient-1",
      alertType: "spo2_critical",
      severity: "critical",
      message: "SpO2 dropped to 88%",
      spo2: 88,
      heartRate: 72,
      timestamp: now.toISOString(),
      resolvedAt: null,
      pagerdutyDedupKey: "test",
      ttl: 7776000,
    }];
    const result = buildStatusResponse(testPatient, reading, alerts, now);

    expect(result.activeAlerts).toHaveLength(1);
    expect(result.activeAlerts[0].alertType).toBe("spo2_critical");
    expect(result.activeAlerts[0].severity).toBe("critical");
    expect(result.activeAlerts[0].message).toBe("SpO2 dropped to 88%");
  });
});
