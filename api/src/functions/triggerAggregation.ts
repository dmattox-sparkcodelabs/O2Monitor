import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getContainer } from "../shared/cosmos";
import { computeNightDate, computeSummary } from "../shared/aggregation";
import { authenticateRequest } from "../shared/auth";
import { Patient, Reading } from "../shared/types";

async function triggerAggregation(
  request: HttpRequest,
  context: InvocationContext
): Promise<HttpResponseInit> {
  const authError = authenticateRequest(request);
  if (authError) return authError;

  const patientId = request.params.id;
  if (!patientId) {
    return { status: 400, jsonBody: { error: { code: "INVALID_REQUEST", message: "Patient ID required" } } };
  }

  const nightDate = request.query.get("nightDate") ?? computeNightDate(new Date().toISOString());

  const readingsContainer = getContainer("readings");
  const summariesContainer = getContainer("dailySummaries");

  const sinceDate = new Date(nightDate);
  sinceDate.setUTCHours(-12, 0, 0, 0);
  const untilDate = new Date(nightDate);
  untilDate.setUTCHours(12, 0, 0, 0);

  const { resources: readings } = await readingsContainer.items
    .query<Reading>({
      query: "SELECT * FROM r WHERE r.patientId = @pid AND r.timestamp >= @since AND r.timestamp < @until ORDER BY r.timestamp ASC",
      parameters: [
        { name: "@pid", value: patientId },
        { name: "@since", value: sinceDate.toISOString() },
        { name: "@until", value: untilDate.toISOString() },
      ],
    })
    .fetchAll();

  if (readings.length === 0) {
    return { status: 200, jsonBody: { nightDate, readingCount: 0, message: "No readings for this night" } };
  }

  const summary = computeSummary(patientId, nightDate, readings);
  await summariesContainer.items.upsert(summary);

  context.log(`Aggregated ${nightDate} for ${patientId}: ${summary.readingCount} readings`);

  return {
    status: 200,
    jsonBody: { nightDate, readingCount: summary.readingCount, spo2Avg: summary.spo2Avg },
  };
}

app.http("triggerAggregation", {
  methods: ["POST"],
  authLevel: "anonymous",
  route: "patients/{id}/aggregate",
  handler: triggerAggregation,
});
