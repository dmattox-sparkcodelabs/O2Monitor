import { buildTriggerEvent, buildResolveEvent, mapSeverity, getRoutingKey } from "../shared/pagerduty";

describe("mapSeverity", () => {
  it("maps critical to critical", () => expect(mapSeverity("critical")).toBe("critical"));
  it("maps high to error", () => expect(mapSeverity("high")).toBe("error"));
  it("maps warning to warning", () => expect(mapSeverity("warning")).toBe("warning"));
  it("maps info to info", () => expect(mapSeverity("info")).toBe("info"));
  it("defaults unknown to warning", () => expect(mapSeverity("unknown")).toBe("warning"));
});

describe("getRoutingKey", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it("returns patient key when set", () => {
    process.env.PAGERDUTY_ROUTING_KEY = "global-key";
    expect(getRoutingKey("patient-key")).toBe("patient-key");
  });

  it("falls back to global key when patient key is empty", () => {
    process.env.PAGERDUTY_ROUTING_KEY = "global-key";
    expect(getRoutingKey("")).toBe("global-key");
  });

  it("returns null when neither key is set", () => {
    delete process.env.PAGERDUTY_ROUTING_KEY;
    expect(getRoutingKey("")).toBeNull();
  });
});

describe("buildTriggerEvent", () => {
  it("builds a valid trigger event", () => {
    const event = buildTriggerEvent({
      routingKey: "test-key",
      dedupKey: "o2-spo2_critical-p1-2026-05-15",
      summary: "SpO2 Critical: 88% for 30s (Dad)",
      severity: "critical",
      patientName: "Dad",
      patientId: "p1",
      spo2: 88,
      heartRate: 72,
    });

    expect(event.routing_key).toBe("test-key");
    expect(event.event_action).toBe("trigger");
    expect(event.dedup_key).toBe("o2-spo2_critical-p1-2026-05-15");
    expect(event.payload.summary).toBe("SpO2 Critical: 88% for 30s (Dad)");
    expect(event.payload.severity).toBe("critical");
    expect(event.payload.source).toBe("O2Monitor v2");
    expect(event.payload.custom_details.patientName).toBe("Dad");
    expect(event.payload.custom_details.spo2).toBe(88);
  });
});

describe("buildResolveEvent", () => {
  it("builds a valid resolve event", () => {
    const event = buildResolveEvent("test-key", "o2-spo2_critical-p1-2026-05-15");

    expect(event.routing_key).toBe("test-key");
    expect(event.event_action).toBe("resolve");
    expect(event.dedup_key).toBe("o2-spo2_critical-p1-2026-05-15");
    expect(event).not.toHaveProperty("payload");
  });
});
