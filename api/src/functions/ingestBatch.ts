import { app, HttpRequest, HttpResponseInit, InvocationContext, output } from "@azure/functions";
import { v4 as uuidv4 } from "uuid";
import { getContainer } from "../shared/cosmos";
import { authenticateRequest } from "../shared/auth";
import { validateBatchRequest, validateIngestRequest } from "../shared/validation";
import { buildNewReadingMessage } from "../shared/signalr";
import { evaluateAlertsForReading } from "./evaluateAlerts";
import { Reading, DEFAULT_TTL } from "../shared/types";

const signalROutput = output.generic({
  type: "signalR",
  name: "signalRMessages",
  hubName: "o2monitor",
});

async function ingestBatch(
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

  const validationError = validateBatchRequest(body);
  if (validationError) {
    return { status: 400, jsonBody: { error: validationError } };
  }

  const b = body as { readings: Record<string, unknown>[] };
  const container = getContainer("readings");
  let accepted = 0;
  let rejected = 0;
  const rejectedIndices: number[] = [];
  let latestReading: Reading | null = null;

  for (let i = 0; i < b.readings.length; i++) {
    const r = b.readings[i];
    const rowError = validateIngestRequest(r);
    if (rowError) {
      rejected++;
      rejectedIndices.push(i);
      context.log(`Batch row ${i} rejected: ${rowError.message}`);
      continue;
    }

    const id = uuidv4();
    const reading: Reading = {
      id,
      patientId: r.patientId as string,
      timestamp: r.timestamp as string,
      spo2: r.spo2 as number,
      heartRate: r.heartRate as number,
      batteryLevel: r.batteryLevel as number,
      movement: (r.movement as number) ?? 0,
      source: (r.source as string) ?? "live",
      deviceId: (r.deviceId as string) ?? "unknown",
      ttl: DEFAULT_TTL,
    };

    try {
      await container.items.create(reading);
      accepted++;
      latestReading = reading;
    } catch (err: unknown) {
      if (err && typeof err === "object" && "code" in err && (err as { code: number }).code === 409) {
        rejected++;
        rejectedIndices.push(i);
      } else {
        rejected++;
        rejectedIndices.push(i);
        context.log(`Batch insert failed for reading ${i}: ${err}`);
      }
    }
  }

  const signalRMessages = [];

  if (latestReading) {
    signalRMessages.push(buildNewReadingMessage(latestReading.patientId, latestReading));

    try {
      const alertMessages = await evaluateAlertsForReading(latestReading);
      signalRMessages.push(...alertMessages);
    } catch (err) {
      context.log(`Alert evaluation failed: ${err}`);
    }
  }

  if (signalRMessages.length > 0) {
    context.extraOutputs.set(signalROutput, signalRMessages);
  }

  context.log(`Batch ingest: ${accepted} accepted, ${rejected} rejected`);

  return {
    status: 200,
    jsonBody: { accepted, rejected, rejectedIndices },
  };
}

app.http("ingestBatch", {
  methods: ["POST"],
  authLevel: "anonymous",
  route: "readings/batch",
  extraOutputs: [signalROutput],
  handler: ingestBatch,
});
