import { validateCreatePatientRequest } from "../shared/validation";

describe("validateCreatePatientRequest", () => {
  const validRequest = {
    name: "Dad",
    deviceMac: "C8:F1:6B:56:7B:F1",
  };

  it("accepts a valid request with name and MAC", () => {
    const result = validateCreatePatientRequest(validRequest);
    expect(result).toBeNull();
  });

  it("accepts request with optional deviceName", () => {
    const result = validateCreatePatientRequest({ ...validRequest, deviceName: "O2M 2781" });
    expect(result).toBeNull();
  });

  it("rejects null body", () => {
    const result = validateCreatePatientRequest(null);
    expect(result).not.toBeNull();
    expect(result!.code).toBe("INVALID_REQUEST");
  });

  it("rejects empty object", () => {
    const result = validateCreatePatientRequest({});
    expect(result).not.toBeNull();
    expect(result!.message).toContain("name");
  });

  it("rejects missing name", () => {
    const result = validateCreatePatientRequest({ deviceMac: "AA:BB:CC:DD:EE:FF" });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("name");
  });

  it("rejects empty name", () => {
    const result = validateCreatePatientRequest({ name: "", deviceMac: "AA:BB:CC:DD:EE:FF" });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("name");
  });

  it("rejects missing deviceMac", () => {
    const result = validateCreatePatientRequest({ name: "Dad" });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("deviceMac");
  });

  it("rejects empty deviceMac", () => {
    const result = validateCreatePatientRequest({ name: "Dad", deviceMac: "" });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("deviceMac");
  });

  it("rejects non-string name", () => {
    const result = validateCreatePatientRequest({ name: 123, deviceMac: "AA:BB:CC:DD:EE:FF" });
    expect(result).not.toBeNull();
    expect(result!.message).toContain("name");
  });
});
