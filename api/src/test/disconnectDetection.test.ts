import { evaluateDisconnect, evaluateReconnect } from "../shared/disconnectEvaluator";
import { AlertConfig, DEFAULT_ALERT_CONFIG, Alert } from "../shared/types";

function makeAlert(alertType: string, resolvedAt: string | null = null): Alert {
  return {
    id: "alert-disconnect",
    patientId: "p1",
    alertType,
    severity: "warning",
    message: "test",
    spo2: null,
    heartRate: null,
    timestamp: new Date().toISOString(),
    resolvedAt,
    pagerdutyDedupKey: "test",
    ttl: 7776000,
  };
}

const config = DEFAULT_ALERT_CONFIG;

describe("evaluateDisconnect", () => {
  it("returns create when no readings exist for patient", () => {
    const result = evaluateDisconnect(null, config, []);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("create");
    expect(result!.alertType).toBe("disconnect");
    expect(result!.severity).toBe("warning");
  });

  it("returns create when latest reading is older than threshold", () => {
    const oldTime = new Date(Date.now() - 130_000).toISOString(); // 130s ago
    const result = evaluateDisconnect(oldTime, config, []);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("create");
    expect(result!.message).toContain("disconnect");
  });

  it("returns null when latest reading is within threshold", () => {
    const recentTime = new Date(Date.now() - 60_000).toISOString(); // 60s ago
    const result = evaluateDisconnect(recentTime, config, []);
    expect(result).toBeNull();
  });

  it("returns null at exactly the threshold boundary", () => {
    const boundaryTime = new Date(Date.now() - 120_000).toISOString(); // exactly 120s
    const result = evaluateDisconnect(boundaryTime, config, []);
    expect(result).toBeNull();
  });

  it("skips create when unresolved disconnect alert exists", () => {
    const oldTime = new Date(Date.now() - 200_000).toISOString();
    const result = evaluateDisconnect(oldTime, config, [makeAlert("disconnect")]);
    expect(result).toBeNull();
  });

  it("uses custom threshold from config", () => {
    const customConfig = { ...config, disconnectAlertSec: 300 };
    const time = new Date(Date.now() - 200_000).toISOString(); // 200s ago
    const result = evaluateDisconnect(time, customConfig, []);
    expect(result).toBeNull(); // 200 < 300
  });
});

describe("evaluateReconnect", () => {
  it("returns resolve when unresolved disconnect alert exists", () => {
    const existing = makeAlert("disconnect");
    const result = evaluateReconnect([existing]);
    expect(result).not.toBeNull();
    expect(result!.action).toBe("resolve");
    expect(result!.alertId).toBe("alert-disconnect");
  });

  it("returns null when no unresolved disconnect alert exists", () => {
    const result = evaluateReconnect([]);
    expect(result).toBeNull();
  });

  it("ignores resolved disconnect alerts", () => {
    const resolved = makeAlert("disconnect", new Date().toISOString());
    const result = evaluateReconnect([resolved]);
    expect(result).toBeNull();
  });
});
