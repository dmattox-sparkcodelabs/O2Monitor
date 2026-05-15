import { app, HttpRequest, HttpResponseInit, InvocationContext, output } from "@azure/functions";
import { v4 as uuidv4 } from "uuid";
import { getContainer } from "../shared/cosmos";
import { authenticateRequest } from "../shared/auth";
import { validateIngestRequest } from "../shared/validation";
import { buildNewReadingMessage } from "../shared/signalr";
import { Reading, DEFAULT_TTL } from "../shared/types";

const signalROutput = output.generic({
  type: "signalR",
  name: "signalRMessages",
  hubName: "o2monitor",
});

async function ingestReading(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  const authError = authenticateRequest(request);
  if (authError) return authError;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return {
      status: 400,
      jsonBody: { error: { code: "INVALID_REQUEST", message: "Invalid JSON body" } },
    };
  }

  const validationError = validateIngestRequest(body);
  if (validationError) {
    return {
      status: 400,
      jsonBody: { error: validationError },
    };
  }

  const b = body as Record<string, unknown>;
  const id = uuidv4();

  const reading: Reading = {
    id,
    patientId: b.patientId as string,
    timestamp: b.timestamp as string,
    spo2: b.spo2 as number,
    heartRate: b.heartRate as number,
    batteryLevel: b.batteryLevel as number,
    movement: (b.movement as number) ?? 0,
    source: (b.source as string) ?? "live",
    deviceId: (b.deviceId as string) ?? "unknown",
    ttl: DEFAULT_TTL,
  };

  const container = getContainer("readings");
  await container.items.create(reading);

  context.extraOutputs.set(signalROutput, [buildNewReadingMessage(reading.patientId, reading)]);

  context.log(`Ingested reading ${id} for patient ${reading.patientId}: SpO2=${reading.spo2} HR=${reading.heartRate}`);

  return {
    status: 201,
    jsonBody: { id },
  };
}

app.http("ingestReading", {
  methods: ["POST"],
  authLevel: "anonymous",
  route: "readings",
  extraOutputs: [signalROutput],
  handler: ingestReading,
});
