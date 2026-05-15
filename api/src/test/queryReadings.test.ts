import { parseReadingsQueryParams } from "../shared/queryParams";

describe("parseReadingsQueryParams", () => {
  it("returns defaults when no params provided", () => {
    const result = parseReadingsQueryParams(new URLSearchParams());
    expect(result.hours).toBe(1);
    expect(result.limit).toBe(1000);
  });

  it("parses hours param", () => {
    const result = parseReadingsQueryParams(new URLSearchParams("hours=6"));
    expect(result.hours).toBe(6);
  });

  it("parses limit param", () => {
    const result = parseReadingsQueryParams(new URLSearchParams("limit=500"));
    expect(result.limit).toBe(500);
  });

  it("clamps hours to max 24", () => {
    const result = parseReadingsQueryParams(new URLSearchParams("hours=48"));
    expect(result.hours).toBe(24);
  });

  it("clamps hours to min 1", () => {
    const result = parseReadingsQueryParams(new URLSearchParams("hours=0"));
    expect(result.hours).toBe(1);
  });

  it("clamps limit to max 5000", () => {
    const result = parseReadingsQueryParams(new URLSearchParams("limit=10000"));
    expect(result.limit).toBe(5000);
  });

  it("clamps limit to min 1", () => {
    const result = parseReadingsQueryParams(new URLSearchParams("limit=0"));
    expect(result.limit).toBe(1);
  });

  it("handles non-numeric hours gracefully", () => {
    const result = parseReadingsQueryParams(new URLSearchParams("hours=abc"));
    expect(result.hours).toBe(1);
  });

  it("handles non-numeric limit gracefully", () => {
    const result = parseReadingsQueryParams(new URLSearchParams("limit=abc"));
    expect(result.limit).toBe(1000);
  });

  it("handles negative values", () => {
    const result = parseReadingsQueryParams(new URLSearchParams("hours=-5&limit=-10"));
    expect(result.hours).toBe(1);
    expect(result.limit).toBe(1);
  });
});
