import { computeNightDate, computeSummary } from "../shared/aggregation";
import { Reading } from "../shared/types";

function makeReading(spo2: number, heartRate: number, timestampStr: string): Reading {
  return {
    id: `r-${timestampStr}`,
    patientId: "p1",
    timestamp: timestampStr,
    spo2,
    heartRate,
    batteryLevel: 85,
    movement: 0,
    source: "live",
    deviceId: "test",
    ttl: 7776000,
  };
}

describe("computeNightDate", () => {
  it("groups 23:30 UTC into the next day", () => {
    expect(computeNightDate("2026-05-14T23:30:00Z")).toBe("2026-05-15");
  });

  it("groups 03:00 UTC into the same calendar day", () => {
    expect(computeNightDate("2026-05-15T03:00:00Z")).toBe("2026-05-15");
  });

  it("groups 11:00 UTC into the same calendar day", () => {
    expect(computeNightDate("2026-05-15T11:00:00Z")).toBe("2026-05-15");
  });

  it("groups 12:00 UTC into the next day", () => {
    expect(computeNightDate("2026-05-15T12:00:00Z")).toBe("2026-05-16");
  });

  it("groups 07:00 CDT (12:00 UTC) into next day", () => {
    expect(computeNightDate("2026-05-15T12:00:00Z")).toBe("2026-05-16");
  });
});

describe("computeSummary", () => {
  it("computes correct stats for a set of readings", () => {
    const readings = [
      makeReading(95, 70, "2026-05-15T02:00:00Z"),
      makeReading(92, 65, "2026-05-15T02:00:15Z"),
      makeReading(88, 80, "2026-05-15T02:00:30Z"),
      makeReading(90, 72, "2026-05-15T02:00:45Z"),
      makeReading(96, 68, "2026-05-15T02:01:00Z"),
    ];

    const summary = computeSummary("p1", "2026-05-15", readings);

    expect(summary.patientId).toBe("p1");
    expect(summary.nightDate).toBe("2026-05-15");
    expect(summary.readingCount).toBe(5);
    expect(summary.durationSeconds).toBe(60);
    expect(summary.spo2Min).toBe(88);
    expect(summary.spo2Max).toBe(96);
    expect(summary.spo2Avg).toBeCloseTo(92.2, 1);
    expect(summary.hrMin).toBe(65);
    expect(summary.hrMax).toBe(80);
    expect(summary.hrAvg).toBeCloseTo(71, 0);
  });

  it("computes timeBelow90 correctly", () => {
    const readings = [
      makeReading(91, 70, "2026-05-15T02:00:00Z"),
      makeReading(89, 70, "2026-05-15T02:00:15Z"),
      makeReading(87, 70, "2026-05-15T02:00:30Z"),
      makeReading(91, 70, "2026-05-15T02:00:45Z"),
    ];

    const summary = computeSummary("p1", "2026-05-15", readings);

    // readings[1] and [2] are below 90; each spans ~15s
    expect(summary.timeBelow90Seconds).toBe(30);
    expect(summary.timeBelow88Seconds).toBe(15);
  });

  it("handles single reading", () => {
    const readings = [makeReading(95, 70, "2026-05-15T02:00:00Z")];
    const summary = computeSummary("p1", "2026-05-15", readings);

    expect(summary.readingCount).toBe(1);
    expect(summary.durationSeconds).toBe(0);
    expect(summary.spo2Avg).toBe(95);
    expect(summary.pctBelow90).toBe(0);
  });

  it("handles all readings below threshold", () => {
    const readings = [
      makeReading(85, 70, "2026-05-15T02:00:00Z"),
      makeReading(86, 70, "2026-05-15T02:00:15Z"),
      makeReading(84, 70, "2026-05-15T02:00:30Z"),
    ];

    const summary = computeSummary("p1", "2026-05-15", readings);

    expect(summary.timeBelow90Seconds).toBe(30);
    expect(summary.timeBelow88Seconds).toBe(30);
    expect(summary.pctBelow90).toBe(1);
    expect(summary.pctBelow88).toBe(1);
  });
});
