import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { v4 as uuidv4 } from "uuid";
import { getContainer } from "../shared/cosmos";
import { authenticateRequest } from "../shared/auth";

interface PatientAccess {
  id: string;
  patientId: string;
  email: string;
  role: string;
  createdAt: string;
}

async function grantAccess(
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

  const email = body.email;
  const role = body.role;

  if (typeof email !== "string" || email.length === 0) {
    return { status: 400, jsonBody: { error: { code: "INVALID_REQUEST", message: "email is required" } } };
  }
  if (typeof role !== "string" || !["owner", "responder", "viewer"].includes(role)) {
    return { status: 400, jsonBody: { error: { code: "INVALID_REQUEST", message: "role must be owner, responder, or viewer" } } };
  }

  const container = getContainer("patientAccess");

  const { resources: existing } = await container.items
    .query<PatientAccess>({
      query: "SELECT * FROM a WHERE a.patientId = @pid AND a.email = @email",
      parameters: [
        { name: "@pid", value: patientId },
        { name: "@email", value: email },
      ],
    })
    .fetchAll();

  if (existing.length > 0) {
    return { status: 409, jsonBody: { error: { code: "DUPLICATE", message: `${email} already has access` } } };
  }

  const access: PatientAccess = {
    id: uuidv4(),
    patientId,
    email: email as string,
    role: role as string,
    createdAt: new Date().toISOString(),
  };

  await container.items.create(access);
  context.log(`Granted ${role} access to ${email} for patient ${patientId}`);

  return { status: 201, jsonBody: { id: access.id, email: access.email, role: access.role } };
}

async function listAccess(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  const authError = authenticateRequest(request);
  if (authError) return authError;

  const patientId = request.params.id;
  if (!patientId) {
    return { status: 400, jsonBody: { error: { code: "INVALID_REQUEST", message: "Patient ID is required" } } };
  }

  const container = getContainer("patientAccess");
  const { resources } = await container.items
    .query<PatientAccess>({
      query: "SELECT * FROM a WHERE a.patientId = @pid",
      parameters: [{ name: "@pid", value: patientId }],
    })
    .fetchAll();

  return {
    status: 200,
    jsonBody: resources.map((a) => ({ id: a.id, email: a.email, role: a.role, createdAt: a.createdAt })),
  };
}

async function revokeAccess(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  const authError = authenticateRequest(request);
  if (authError) return authError;

  const patientId = request.params.id;
  const accessId = request.params.accessId;

  if (!patientId || !accessId) {
    return { status: 400, jsonBody: { error: { code: "INVALID_REQUEST", message: "Patient ID and access ID are required" } } };
  }

  const container = getContainer("patientAccess");
  try {
    await container.item(accessId, patientId).delete();
  } catch (err: unknown) {
    if (err && typeof err === "object" && "code" in err && (err as { code: number }).code === 404) {
      return { status: 404, jsonBody: { error: { code: "NOT_FOUND", message: "Access entry not found" } } };
    }
    throw err;
  }

  context.log(`Revoked access ${accessId} for patient ${patientId}`);
  return { status: 204 };
}

app.http("grantAccess", {
  methods: ["POST"],
  authLevel: "anonymous",
  route: "patients/{id}/access",
  handler: grantAccess,
});

app.http("listAccess", {
  methods: ["GET"],
  authLevel: "anonymous",
  route: "patients/{id}/access",
  handler: listAccess,
});

app.http("revokeAccess", {
  methods: ["DELETE"],
  authLevel: "anonymous",
  route: "patients/{id}/access/{accessId}",
  handler: revokeAccess,
});
