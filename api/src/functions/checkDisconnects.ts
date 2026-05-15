import { app, InvocationContext, Timer, output } from "@azure/functions";
import { v4 as uuidv4 } from "uuid";
import { getContainer } from "../shared/cosmos";
import { evaluateDisconnect } from "../shared/disconnectEvaluator";
import { getRoutingKey, triggerAlert, resolveAlert } from "../shared/pagerduty";
import { Patient, Alert, Reading, DEFAULT_TTL } from "../shared/types";

const signalROutput = output.generic({
  type: "signalR",
  name: "signalRMessages",
  hubName: "o2monitor",
});

async function checkDisconnects(
  timer: Timer,
  context: InvocationContext
): Promise<void> {
  const patientsContainer = getContainer("patients");
  const readingsContainer = getContainer("readings");
  const alertsContainer = getContainer("alerts");

  const { resources: patients } = await patientsContainer.items
    .query<Patient>({ query: "SELECT * FROM c" })
    .fetchAll();

  const signalRMessages: unknown[] = [];

  for (const patient of patients) {
    const { resources: latestReadings } = await readingsContainer.items
      .query<Reading>({
        query: "SELECT TOP 1 * FROM r WHERE r.patientId = @pid ORDER BY r.timestamp DESC",
        parameters: [{ name: "@pid", value: patient.id }],
      })
      .fetchAll();

    const latestTimestamp = latestReadings.length > 0 ? latestReadings[0].timestamp : null;

    const { resources: unresolvedAlerts } = await alertsContainer.items
      .query<Alert>({
        query: "SELECT * FROM a WHERE a.patientId = @pid AND a.resolvedAt = null",
        parameters: [{ name: "@pid", value: patient.id }],
      })
      .fetchAll();

    const action = evaluateDisconnect(latestTimestamp, patient.alertConfig, unresolvedAlerts);

    if (action && action.action === "create") {
      const now = new Date();
      const dateStr = now.toISOString().split("T")[0];
      const dedupKey = `o2-disconnect-${patient.id}-${dateStr}`;
      const alert: Alert = {
        id: uuidv4(),
        patientId: patient.id,
        alertType: "disconnect",
        severity: "warning",
        message: action.message,
        spo2: null,
        heartRate: null,
        timestamp: now.toISOString(),
        resolvedAt: null,
        pagerdutyDedupKey: dedupKey,
        ttl: DEFAULT_TTL,
      };
      await alertsContainer.items.create(alert);

      const routingKey = getRoutingKey(patient.alertConfig.pagerdutyRoutingKey);
      if (routingKey) {
        await triggerAlert(routingKey, dedupKey, action.message, "warning", patient.name, patient.id, null, null);
      }

      const secondsSinceReading = latestTimestamp
        ? Math.round((Date.now() - new Date(latestTimestamp).getTime()) / 1000)
        : null;

      signalRMessages.push({
        target: "connectionStatus",
        groupName: `patient:${patient.id}`,
        arguments: [{ patientId: patient.id, deviceOnline: false, secondsSinceReading }],
      });

      context.log(`Disconnect alert created for patient ${patient.id} (${patient.name})`);
    }
  }

  if (signalRMessages.length > 0) {
    context.extraOutputs.set(signalROutput, signalRMessages);
  }
}

app.timer("checkDisconnects", {
  schedule: "0 */1 * * * *",
  extraOutputs: [signalROutput],
  handler: checkDisconnects,
});
