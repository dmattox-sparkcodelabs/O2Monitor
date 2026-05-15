import { validateApiKey } from "../shared/auth";

describe("validateApiKey", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it("rejects when no api key header is provided", () => {
    process.env.API_KEYS = "key1,key2";
    const result = validateApiKey(undefined);
    expect(result).not.toBeNull();
    expect(result!.code).toBe("UNAUTHORIZED");
  });

  it("rejects when api key header is empty string", () => {
    process.env.API_KEYS = "key1,key2";
    const result = validateApiKey("");
    expect(result).not.toBeNull();
    expect(result!.code).toBe("UNAUTHORIZED");
  });

  it("rejects when api key does not match any configured key", () => {
    process.env.API_KEYS = "key1,key2";
    const result = validateApiKey("wrong-key");
    expect(result).not.toBeNull();
    expect(result!.code).toBe("UNAUTHORIZED");
  });

  it("accepts a valid api key", () => {
    process.env.API_KEYS = "key1,key2";
    const result = validateApiKey("key1");
    expect(result).toBeNull();
  });

  it("accepts the second key in the list", () => {
    process.env.API_KEYS = "key1,key2,key3";
    const result = validateApiKey("key2");
    expect(result).toBeNull();
  });

  it("trims whitespace from configured keys", () => {
    process.env.API_KEYS = " key1 , key2 ";
    const result = validateApiKey("key1");
    expect(result).toBeNull();
  });

  it("allows all requests when API_KEYS is not set (dev mode)", () => {
    delete process.env.API_KEYS;
    const result = validateApiKey(undefined);
    expect(result).toBeNull();
  });

  it("allows all requests when API_KEYS is empty string (dev mode)", () => {
    process.env.API_KEYS = "";
    const result = validateApiKey(undefined);
    expect(result).toBeNull();
  });

  it("rejects when API_KEYS is set but request has no key", () => {
    process.env.API_KEYS = "valid-key";
    const result = validateApiKey(undefined);
    expect(result).not.toBeNull();
  });
});
