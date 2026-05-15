import { v4 as uuidv4 } from "uuid";
import { getContainer } from "../shared/cosmos";
import { evaluateAllAlerts } from "../shared/alertEvaluator";
import { evaluateReconnect } from "../shared/disconnectEvaluator";
import { getRoutingKey, triggerAlert, resolveAlert } from "../shared/pagerduty";
import { buildAlertTriggeredMessage, buildAlertResolvedMessage, SignalRMessage } from "../shared/signalr";
import { Reading, Patient, Alert, DEFAULT_TTL } from "../shared/types";

export async function evaluateAlertsForReading(reading: Reading): Promise<SignalRMessage[]> {
  const signalRMessages: SignalRMessage[] = [];
  const patientsContainer = getContainer("patients");
  const readingsContainer = getContainer("readings");
  const alertsContainer = getContainer("alerts");

  let patient: Patient;
  try {
    const { resource } = await patientsContainer.item(reading.patientId, reading.patientId).read<Patient>();
    if (!resource) return signalRMessages;
    patient = resource;
  } catch {
    return signalRMessages;
  }

  const maxDuration = Math.max(
    patient.alertConfig.spo2CriticalDurationSec,
    patient.alertConfig.spo2WarningDurationSec,
    patient.alertConfig.hrDurationSec,
    60
  );
  const since = new Date(Date.now() - maxDuration * 1000).toISOString();

  const { resources: recentReadings } = await readingsContainer.items
    .query<Reading>({
      query: "SELECT * FROM r WHERE r.patientId = @pid AND r.timestamp >= @since ORDER BY r.timestamp DESC",
      parameters: [
        { name: "@pid", value: reading.patientId },
        { name: "@since", value: since },
      ],
    })
    .fetchAll();

  const { resources: unresolvedAlerts } = await alertsContainer.items
    .query<Alert>({
      query: "SELECT * FROM a WHERE a.patientId = @pid AND a.resolvedAt = null",
      parameters: [{ name: "@pid", value: reading.patientId }],
    })
    .fetchAll();

  const actions = evaluateAllAlerts(reading, recentReadings, patient.alertConfig, unresolvedAlerts);
  const routingKey = getRoutingKey(patient.alertConfig.pagerdutyRoutingKey);

  const reconnectAction = evaluateReconnect(unresolvedAlerts);
  if (reconnectAction) actions.push(reconnectAction);

  for (const action of actions) {
    if (action.action === "create") {
      const now = new Date();
      const dateStr = now.toISOString().split("T")[0];
      const dedupKey = `o2-${action.alertType}-${reading.patientId}-${dateStr}`;
      const alert: Alert = {
        id: uuidv4(),
        patientId: reading.patientId,
        alertType: action.alertType,
        severity: action.severity,
        message: action.message,
        spo2: action.spo2,
        heartRate: action.heartRate,
        timestamp: now.toISOString(),
        resolvedAt: null,
        pagerdutyDedupKey: dedupKey,
        ttl: DEFAULT_TTL,
      };
      await alertsContainer.items.create(alert);

      signalRMessages.push(buildAlertTriggeredMessage(reading.patientId, alert));

      if (routingKey) {
        await triggerAlert(
          routingKey, dedupKey, action.message, action.severity,
          patient.name, patient.id, action.spo2, action.heartRate
        );
      }
    } else if (action.action === "resolve" && action.alertId) {
      const { resource } = await alertsContainer.item(action.alertId, reading.patientId).read<Alert>();
      if (resource) {
        resource.resolvedAt = new Date().toISOString();
        await alertsContainer.item(action.alertId, reading.patientId).replace(resource);

        signalRMessages.push(buildAlertResolvedMessage(reading.patientId, {
          id: resource.id, alertType: resource.alertType, resolvedAt: resource.resolvedAt,
        }));

        if (routingKey) {
          await resolveAlert(routingKey, resource.pagerdutyDedupKey);
        }
      }
    }
  }

  return signalRMessages;
}
