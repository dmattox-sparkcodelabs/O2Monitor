import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getContainer } from "../shared/cosmos";
import { buildStatusResponse } from "../shared/statusBuilder";
import { Reading, Patient } from "../shared/types";

async function queryStatus(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  const patientId = request.params.id;
  if (!patientId) {
    return {
      status: 400,
      jsonBody: { error: { code: "INVALID_REQUEST", message: "Patient ID is required" } },
    };
  }

  const patientsContainer = getContainer("patients");
  let patient: Patient;
  try {
    const { resource } = await patientsContainer.item(patientId, patientId).read<Patient>();
    if (!resource) {
      return {
        status: 404,
        jsonBody: { error: { code: "PATIENT_NOT_FOUND", message: `Patient '${patientId}' not found` } },
      };
    }
    patient = resource;
  } catch (err: unknown) {
    if (err && typeof err === "object" && "code" in err && (err as { code: number }).code === 404) {
      return {
        status: 404,
        jsonBody: { error: { code: "PATIENT_NOT_FOUND", message: `Patient '${patientId}' not found` } },
      };
    }
    throw err;
  }

  const readingsContainer = getContainer("readings");
  const { resources } = await readingsContainer.items
    .query<Reading>({
      query: "SELECT TOP 1 * FROM r WHERE r.patientId = @patientId ORDER BY r.timestamp DESC",
      parameters: [{ name: "@patientId", value: patientId }],
    })
    .fetchAll();

  const latestReading = resources.length > 0 ? resources[0] : null;
  const status = buildStatusResponse(patient, latestReading, new Date());

  return {
    status: 200,
    jsonBody: status,
  };
}

app.http("queryStatus", {
  methods: ["GET"],
  authLevel: "anonymous",
  route: "patients/{id}/status",
  handler: queryStatus,
});
