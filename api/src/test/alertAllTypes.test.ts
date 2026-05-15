import {
  evaluateSpo2Warning,
  evaluateHrHigh,
  evaluateHrLow,
  evaluateBatteryWarning,
  evaluateBatteryCritical,
  evaluateAllAlerts,
} from "../shared/alertEvaluator";
import { AlertConfig, DEFAULT_ALERT_CONFIG, Reading, Alert } from "../shared/types";

function makeReading(overrides: Partial<Reading> = {}, secondsAgo = 0): Reading {
  return {
    id: `r-${secondsAgo}`,
    patientId: "p1",
    timestamp: new Date(Date.now() - secondsAgo * 1000).toISOString(),
    spo2: 97,
    heartRate: 72,
    batteryLevel: 85,
    movement: 0,
    source: "live",
    deviceId: "test",
    ttl: 7776000,
    ...overrides,
  };
}

function makeAlert(alertType: string): Alert {
  return {
    id: `alert-${alertType}`,
    patientId: "p1",
    alertType,
    severity: "warning",
    message: "test",
    spo2: null,
    heartRate: null,
    timestamp: new Date().toISOString(),
    resolvedAt: null,
    pagerdutyDedupKey: "test",
    ttl: 7776000,
  };
}

function recentReadings(overrides: Partial<Reading>, count = 13): Reading[] {
  return Array.from({ length: count }, (_, i) => makeReading(overrides, i * 5));
}

const config = DEFAULT_ALERT_CONFIG;

describe("evaluateSpo2Warning", () => {
  it("creates alert when SpO2 below 92 for 60s", () => {
    const current = makeReading({ spo2: 91 });
    const recent = recentReadings({ spo2: 91 });
    const result = evaluateSpo2Warning(current, recent, config, []);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("create");
    expect(result!.alertType).toBe("spo2_warning");
    expect(result!.severity).toBe("warning");
  });

  it("does not fire when SpO2 is 92 (at threshold)", () => {
    const current = makeReading({ spo2: 92 });
    const recent = recentReadings({ spo2: 92 });
    const result = evaluateSpo2Warning(current, recent, config, []);
    expect(result).toBeNull();
  });

  it("resolves when SpO2 recovers", () => {
    const current = makeReading({ spo2: 95 });
    const result = evaluateSpo2Warning(current, [current], config, [makeAlert("spo2_warning")]);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("resolve");
  });
});

describe("evaluateHrHigh", () => {
  it("creates alert when HR above 120 for 60s", () => {
    const current = makeReading({ heartRate: 130 });
    const recent = recentReadings({ heartRate: 130 });
    const result = evaluateHrHigh(current, recent, config, []);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("create");
    expect(result!.alertType).toBe("hr_high");
    expect(result!.severity).toBe("high");
  });

  it("does not fire at exactly 120 (threshold is >120)", () => {
    const current = makeReading({ heartRate: 120 });
    const recent = recentReadings({ heartRate: 120 });
    const result = evaluateHrHigh(current, recent, config, []);
    expect(result).toBeNull();
  });

  it("resolves when HR drops to normal", () => {
    const current = makeReading({ heartRate: 80 });
    const result = evaluateHrHigh(current, [current], config, [makeAlert("hr_high")]);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("resolve");
  });
});

describe("evaluateHrLow", () => {
  it("creates alert when HR below 50 for 60s", () => {
    const current = makeReading({ heartRate: 45 });
    const recent = recentReadings({ heartRate: 45 });
    const result = evaluateHrLow(current, recent, config, []);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("create");
    expect(result!.alertType).toBe("hr_low");
    expect(result!.severity).toBe("high");
  });

  it("does not fire at exactly 50", () => {
    const current = makeReading({ heartRate: 50 });
    const recent = recentReadings({ heartRate: 50 });
    const result = evaluateHrLow(current, recent, config, []);
    expect(result).toBeNull();
  });

  it("resolves when HR rises", () => {
    const current = makeReading({ heartRate: 60 });
    const result = evaluateHrLow(current, [current], config, [makeAlert("hr_low")]);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("resolve");
  });
});

describe("evaluateBatteryWarning", () => {
  it("creates alert instantly when battery <= 25", () => {
    const current = makeReading({ batteryLevel: 25 });
    const result = evaluateBatteryWarning(current, config, []);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("create");
    expect(result!.alertType).toBe("battery_warning");
    expect(result!.severity).toBe("warning");
  });

  it("does not fire when battery is 26", () => {
    const result = evaluateBatteryWarning(makeReading({ batteryLevel: 26 }), config, []);
    expect(result).toBeNull();
  });

  it("resolves when battery recovers above threshold", () => {
    const current = makeReading({ batteryLevel: 30 });
    const result = evaluateBatteryWarning(current, config, [makeAlert("battery_warning")]);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("resolve");
  });

  it("skips create if unresolved alert exists", () => {
    const current = makeReading({ batteryLevel: 20 });
    const result = evaluateBatteryWarning(current, config, [makeAlert("battery_warning")]);
    expect(result).toBeNull();
  });
});

describe("evaluateBatteryCritical", () => {
  it("creates alert instantly when battery <= 10", () => {
    const current = makeReading({ batteryLevel: 10 });
    const result = evaluateBatteryCritical(current, config, []);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("create");
    expect(result!.alertType).toBe("battery_critical");
    expect(result!.severity).toBe("critical");
  });

  it("does not fire at 11", () => {
    const result = evaluateBatteryCritical(makeReading({ batteryLevel: 11 }), config, []);
    expect(result).toBeNull();
  });

  it("resolves when battery recovers", () => {
    const current = makeReading({ batteryLevel: 15 });
    const result = evaluateBatteryCritical(current, config, [makeAlert("battery_critical")]);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("resolve");
  });
});

describe("evaluateAllAlerts", () => {
  it("returns multiple actions when multiple conditions are met", () => {
    const current = makeReading({ spo2: 88, heartRate: 130, batteryLevel: 8 });
    const recent = recentReadings({ spo2: 88, heartRate: 130, batteryLevel: 8 });
    const actions = evaluateAllAlerts(current, recent, config, []);
    const types = actions.map((a) => a.alertType).sort();
    expect(types).toContain("spo2_critical");
    expect(types).toContain("hr_high");
    expect(types).toContain("battery_critical");
  });

  it("returns empty array when everything is normal", () => {
    const current = makeReading({ spo2: 97, heartRate: 72, batteryLevel: 85 });
    const recent = recentReadings({ spo2: 97, heartRate: 72, batteryLevel: 85 });
    const actions = evaluateAllAlerts(current, recent, config, []);
    expect(actions).toEqual([]);
  });
});
