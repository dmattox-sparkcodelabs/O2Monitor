import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getContainer } from "../shared/cosmos";
import { authenticateRequest } from "../shared/auth";
import { parseReadingsQueryParams } from "../shared/queryParams";
import { Reading } from "../shared/types";

async function queryReadings(
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

  const params = parseReadingsQueryParams(request.query as unknown as URLSearchParams);
  const since = new Date(Date.now() - params.hours * 60 * 60 * 1000).toISOString();

  const container = getContainer("readings");
  const { resources } = await container.items
    .query<Reading>({
      query: `SELECT TOP @limit * FROM r WHERE r.patientId = @patientId AND r.timestamp >= @since ORDER BY r.timestamp DESC`,
      parameters: [
        { name: "@patientId", value: patientId },
        { name: "@since", value: since },
        { name: "@limit", value: params.limit },
      ],
    })
    .fetchAll();

  return {
    status: 200,
    jsonBody: {
      readings: resources,
      count: resources.length,
    },
  };
}

app.http("queryReadings", {
  methods: ["GET"],
  authLevel: "anonymous",
  route: "patients/{id}/readings",
  handler: queryReadings,
});
