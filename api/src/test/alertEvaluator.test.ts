import { evaluateSpo2Critical } from "../shared/alertEvaluator";
import { AlertConfig, DEFAULT_ALERT_CONFIG, Reading, Alert } from "../shared/types";

function makeReading(spo2: number, secondsAgo: number): Reading {
  const ts = new Date(Date.now() - secondsAgo * 1000).toISOString();
  return {
    id: `r-${secondsAgo}`,
    patientId: "p1",
    timestamp: ts,
    spo2,
    heartRate: 72,
    batteryLevel: 85,
    movement: 0,
    source: "live",
    deviceId: "test",
    ttl: 7776000,
  };
}

function makeAlert(alertType: string, resolvedAt: string | null = null): Alert {
  return {
    id: "alert-1",
    patientId: "p1",
    alertType,
    severity: "critical",
    message: "test",
    spo2: 88,
    heartRate: 72,
    timestamp: new Date().toISOString(),
    resolvedAt,
    pagerdutyDedupKey: "test",
    ttl: 7776000,
  };
}

const config = DEFAULT_ALERT_CONFIG;

describe("evaluateSpo2Critical", () => {
  it("returns no action when SpO2 is above threshold", () => {
    const current = makeReading(95, 0);
    const recent = [makeReading(95, 5), makeReading(96, 10), makeReading(94, 15)];
    const result = evaluateSpo2Critical(current, recent, config, []);
    expect(result).toBeNull();
  });

  it("returns no action when duration not met (not enough readings below threshold)", () => {
    const current = makeReading(88, 0);
    const recent = [makeReading(88, 5), makeReading(95, 10)];
    const result = evaluateSpo2Critical(current, recent, config, []);
    expect(result).toBeNull();
  });

  it("returns create when all readings in window are below threshold for full duration", () => {
    const current = makeReading(88, 0);
    const recent = [
      makeReading(88, 0),
      makeReading(87, 5),
      makeReading(89, 10),
      makeReading(88, 15),
      makeReading(87, 20),
      makeReading(88, 25),
      makeReading(89, 30),
    ];
    const result = evaluateSpo2Critical(current, recent, config, []);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("create");
    expect(result!.alertType).toBe("spo2_critical");
    expect(result!.severity).toBe("critical");
  });

  it("skips create when unresolved alert already exists", () => {
    const current = makeReading(88, 0);
    const recent = Array.from({ length: 7 }, (_, i) => makeReading(88, i * 5));
    const existing = [makeAlert("spo2_critical")];
    const result = evaluateSpo2Critical(current, recent, config, existing);
    expect(result).toBeNull();
  });

  it("returns resolve when current reading is above threshold and unresolved alert exists", () => {
    const current = makeReading(96, 0);
    const recent = [makeReading(96, 0)];
    const existing = [makeAlert("spo2_critical")];
    const result = evaluateSpo2Critical(current, recent, config, existing);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("resolve");
    expect(result!.alertId).toBe("alert-1");
  });

  it("does not resolve when no unresolved alert exists", () => {
    const current = makeReading(96, 0);
    const recent = [makeReading(96, 0)];
    const result = evaluateSpo2Critical(current, recent, config, []);
    expect(result).toBeNull();
  });

  it("does not resolve already-resolved alerts", () => {
    const current = makeReading(96, 0);
    const recent = [makeReading(96, 0)];
    const existing = [makeAlert("spo2_critical", new Date().toISOString())];
    const result = evaluateSpo2Critical(current, recent, config, existing);
    expect(result).toBeNull();
  });

  it("uses the correct threshold from config", () => {
    const customConfig = { ...config, spo2CriticalThreshold: 85 };
    const current = makeReading(87, 0);
    const recent = Array.from({ length: 7 }, (_, i) => makeReading(87, i * 5));
    const result = evaluateSpo2Critical(current, recent, customConfig, []);
    expect(result).toBeNull(); // 87 is above 85 threshold
  });

  it("fires when readings are at exactly the threshold boundary", () => {
    const current = makeReading(89, 0);
    const recent = Array.from({ length: 7 }, (_, i) => makeReading(89, i * 5));
    const result = evaluateSpo2Critical(current, recent, config, []);
    // 89 < 90 threshold, duration met → should fire
    expect(result).not.toBeNull();
    expect(result!.action).toBe("create");
  });

  it("does not fire when readings are at exactly the threshold value", () => {
    const current = makeReading(90, 0);
    const recent = Array.from({ length: 7 }, (_, i) => makeReading(90, i * 5));
    const result = evaluateSpo2Critical(current, recent, config, []);
    // 90 is NOT below 90 → should not fire
    expect(result).toBeNull();
  });

  it("includes reading values in create action message", () => {
    const current = makeReading(85, 0);
    const recent = Array.from({ length: 7 }, (_, i) => makeReading(85, i * 5));
    const result = evaluateSpo2Critical(current, recent, config, []);
    expect(result).not.toBeNull();
    expect(result!.message).toContain("85");
  });
});
