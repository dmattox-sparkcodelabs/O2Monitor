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
  const since = params.since ?? new Date(Date.now() - params.hours * 60 * 60 * 1000).toISOString();

  const container = getContainer("readings");

  let query: string;
  const queryParams: { name: string; value: string | number }[] = [
    { name: "@patientId", value: patientId },
    { name: "@since", value: since },
    { name: "@limit", value: params.limit },
  ];

  if (params.until) {
    query = `SELECT TOP @limit * FROM r WHERE r.patientId = @patientId AND r.timestamp >= @since AND r.timestamp < @until ORDER BY r.timestamp ASC`;
    queryParams.push({ name: "@until", value: params.until });
  } else {
    query = `SELECT TOP @limit * FROM r WHERE r.patientId = @patientId AND r.timestamp >= @since ORDER BY r.timestamp DESC`;
  }

  const { resources } = await container.items
    .query<Reading>({ query, parameters: queryParams })
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
