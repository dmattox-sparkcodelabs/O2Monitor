import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getContainer } from "../shared/cosmos";
import { authenticateRequest } from "../shared/auth";
import { DailySummary } from "../shared/aggregation";

async function querySummaries(
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

  const daysRaw = parseInt(request.query.get("days") ?? "30", 10);
  const days = Math.min(365, Math.max(1, isNaN(daysRaw) ? 30 : daysRaw));

  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString().split("T")[0];

  const container = getContainer("dailySummaries");
  const { resources } = await container.items
    .query<DailySummary>({
      query: "SELECT * FROM s WHERE s.patientId = @pid AND s.nightDate >= @since ORDER BY s.nightDate DESC",
      parameters: [
        { name: "@pid", value: patientId },
        { name: "@since", value: since },
      ],
    })
    .fetchAll();

  return {
    status: 200,
    jsonBody: {
      summaries: resources.map((s) => ({
        nightDate: s.nightDate,
        readingCount: s.readingCount,
        durationSeconds: s.durationSeconds,
        spo2Avg: s.spo2Avg,
        spo2Min: s.spo2Min,
        spo2Max: s.spo2Max,
        hrAvg: s.hrAvg,
        hrMin: s.hrMin,
        hrMax: s.hrMax,
        timeBelow90Seconds: s.timeBelow90Seconds,
        timeBelow88Seconds: s.timeBelow88Seconds,
        pctBelow90: s.pctBelow90,
        pctBelow88: s.pctBelow88,
      })),
    },
  };
}

app.http("querySummaries", {
  methods: ["GET"],
  authLevel: "anonymous",
  route: "patients/{id}/summaries",
  handler: querySummaries,
});
