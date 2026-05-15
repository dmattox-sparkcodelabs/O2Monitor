import { HttpRequest, HttpResponseInit } from "@azure/functions";

interface AuthError {
  code: string;
  message: string;
}

export function validateApiKey(apiKey: string | undefined): AuthError | null {
  const configuredKeys = process.env.API_KEYS;

  if (!configuredKeys) {
    return null;
  }

  const keys = configuredKeys.split(",").map((k) => k.trim()).filter(Boolean);
  if (keys.length === 0) {
    return null;
  }

  if (!apiKey || !keys.includes(apiKey)) {
    return { code: "UNAUTHORIZED", message: "Invalid or missing API key" };
  }

  return null;
}

export function authenticateRequest(request: HttpRequest): HttpResponseInit | null {
  const apiKey = request.headers.get("x-api-key") ?? undefined;
  const error = validateApiKey(apiKey);
  if (error) {
    return {
      status: 401,
      jsonBody: { error },
    };
  }
  return null;
}
