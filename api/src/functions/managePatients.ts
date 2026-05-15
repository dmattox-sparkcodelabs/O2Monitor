import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { v4 as uuidv4 } from "uuid";
import { getContainer } from "../shared/cosmos";
import { authenticateRequest } from "../shared/auth";
import { validateCreatePatientRequest } from "../shared/validation";
import { Patient, DEFAULT_ALERT_CONFIG } from "../shared/types";

async function createPatient(
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

  const validationError = validateCreatePatientRequest(body);
  if (validationError) {
    return { status: 400, jsonBody: { error: validationError } };
  }

  const b = body as Record<string, unknown>;
  const id = uuidv4();

  const patient: Patient = {
    id,
    name: b.name as string,
    deviceMac: b.deviceMac as string,
    deviceName: (b.deviceName as string) ?? undefined,
    alertConfig: { ...DEFAULT_ALERT_CONFIG },
    createdAt: new Date().toISOString(),
    createdBy: "api-key-user",
  };

  const container = getContainer("patients");
  await container.items.create(patient);

  context.log(`Created patient ${id}: ${patient.name}`);

  return {
    status: 201,
    jsonBody: patient,
  };
}

async function listPatients(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  const authError = authenticateRequest(request);
  if (authError) return authError;

  const container = getContainer("patients");
  const { resources } = await container.items
    .query<Patient>({
      query: "SELECT c.id, c.name, c.deviceMac, c.deviceName FROM c",
    })
    .fetchAll();

  return {
    status: 200,
    jsonBody: resources,
  };
}

async function getPatient(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  const authError = authenticateRequest(request);
  if (authError) return authError;

  const patientId = request.params.id;
  if (!patientId) {
    return {
      status: 400,
      jsonBody: { error: { code: "INVALID_REQUEST", message: "Patient ID is required" } },
    };
  }

  const container = getContainer("patients");
  try {
    const { resource } = await container.item(patientId, patientId).read<Patient>();
    if (!resource) {
      return {
        status: 404,
        jsonBody: { error: { code: "PATIENT_NOT_FOUND", message: `Patient '${patientId}' not found` } },
      };
    }
    return { status: 200, jsonBody: resource };
  } catch (err: unknown) {
    if (err && typeof err === "object" && "code" in err && (err as { code: number }).code === 404) {
      return {
        status: 404,
        jsonBody: { error: { code: "PATIENT_NOT_FOUND", message: `Patient '${patientId}' not found` } },
      };
    }
    throw err;
  }
}

app.http("createPatient", {
  methods: ["POST"],
  authLevel: "anonymous",
  route: "patients",
  handler: createPatient,
});

app.http("listPatients", {
  methods: ["GET"],
  authLevel: "anonymous",
  route: "patients",
  handler: listPatients,
});

async function updatePatient(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  const authError = authenticateRequest(request);
  if (authError) return authError;

  const patientId = request.params.id;
  if (!patientId) {
    return { status: 400, jsonBody: { error: { code: "INVALID_REQUEST", message: "Patient ID is required" } } };
  }

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return { status: 400, jsonBody: { error: { code: "INVALID_REQUEST", message: "Invalid JSON body" } } };
  }

  const container = getContainer("patients");
  let patient: Patient;
  try {
    const { resource } = await container.item(patientId, patientId).read<Patient>();
    if (!resource) {
      return { status: 404, jsonBody: { error: { code: "PATIENT_NOT_FOUND", message: `Patient '${patientId}' not found` } } };
    }
    patient = resource;
  } catch (err: unknown) {
    if (err && typeof err === "object" && "code" in err && (err as { code: number }).code === 404) {
      return { status: 404, jsonBody: { error: { code: "PATIENT_NOT_FOUND", message: `Patient '${patientId}' not found` } } };
    }
    throw err;
  }

  if (typeof body.name === "string" && body.name.length > 0) patient.name = body.name;
  if (typeof body.deviceMac === "string" && body.deviceMac.length > 0) patient.deviceMac = body.deviceMac;
  if (typeof body.deviceName === "string") patient.deviceName = body.deviceName;

  if (body.alertConfig && typeof body.alertConfig === "object") {
    const ac = body.alertConfig as Record<string, unknown>;
    const cfg = patient.alertConfig;
    if (typeof ac.spo2CriticalThreshold === "number") cfg.spo2CriticalThreshold = ac.spo2CriticalThreshold;
    if (typeof ac.spo2CriticalDurationSec === "number") cfg.spo2CriticalDurationSec = ac.spo2CriticalDurationSec;
    if (typeof ac.spo2WarningThreshold === "number") cfg.spo2WarningThreshold = ac.spo2WarningThreshold;
    if (typeof ac.spo2WarningDurationSec === "number") cfg.spo2WarningDurationSec = ac.spo2WarningDurationSec;
    if (typeof ac.hrHighThreshold === "number") cfg.hrHighThreshold = ac.hrHighThreshold;
    if (typeof ac.hrLowThreshold === "number") cfg.hrLowThreshold = ac.hrLowThreshold;
    if (typeof ac.hrDurationSec === "number") cfg.hrDurationSec = ac.hrDurationSec;
    if (typeof ac.batteryWarningThreshold === "number") cfg.batteryWarningThreshold = ac.batteryWarningThreshold;
    if (typeof ac.batteryCriticalThreshold === "number") cfg.batteryCriticalThreshold = ac.batteryCriticalThreshold;
    if (typeof ac.disconnectAlertSec === "number") cfg.disconnectAlertSec = ac.disconnectAlertSec;
    if (typeof ac.pagerdutyRoutingKey === "string") cfg.pagerdutyRoutingKey = ac.pagerdutyRoutingKey;
    if (typeof ac.resendIntervalSec === "number") cfg.resendIntervalSec = ac.resendIntervalSec;
  }

  await container.item(patientId, patientId).replace(patient);
  context.log(`Updated patient ${patientId}`);

  return { status: 200, jsonBody: patient };
}

app.http("getPatient", {
  methods: ["GET"],
  authLevel: "anonymous",
  route: "patients/{id}",
  handler: getPatient,
});

app.http("updatePatient", {
  methods: ["PUT"],
  authLevel: "anonymous",
  route: "patients/{id}",
  handler: updatePatient,
});
