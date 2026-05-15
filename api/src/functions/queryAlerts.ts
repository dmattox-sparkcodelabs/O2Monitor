import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { getContainer } from "../shared/cosmos";
import { authenticateRequest } from "../shared/auth";
import { Alert } from "../shared/types";

async function queryAlerts(
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

  const daysRaw = parseInt(request.query.get("days") ?? "7", 10);
  const days = Math.min(90, Math.max(1, isNaN(daysRaw) ? 7 : daysRaw));
  const statusFilter = request.query.get("status") ?? "";

  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

  let query = "SELECT * FROM a WHERE a.patientId = @patientId AND a.timestamp >= @since";
  const parameters: { name: string; value: string }[] = [
    { name: "@patientId", value: patientId },
    { name: "@since", value: since },
  ];

  if (statusFilter === "active") {
    query += " AND a.resolvedAt = null";
  } else if (statusFilter === "resolved") {
    query += " AND a.resolvedAt != null";
  }

  query += " ORDER BY a.timestamp DESC";

  const container = getContainer("alerts");
  const { resources } = await container.items
    .query<Alert>({ query, parameters })
    .fetchAll();

  return {
    status: 200,
    jsonBody: {
      alerts: resources.map((a) => ({
        id: a.id,
        alertType: a.alertType,
        severity: a.severity,
        message: a.message,
        spo2: a.spo2,
        heartRate: a.heartRate,
        timestamp: a.timestamp,
        resolvedAt: a.resolvedAt,
      })),
    },
  };
}

app.http("queryAlerts", {
  methods: ["GET"],
  authLevel: "anonymous",
  route: "patients/{id}/alerts",
  handler: queryAlerts,
});
