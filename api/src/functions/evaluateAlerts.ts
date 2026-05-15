import { v4 as uuidv4 } from "uuid";
import { getContainer } from "../shared/cosmos";
import { evaluateAllAlerts } from "../shared/alertEvaluator";
import { Reading, Patient, Alert, DEFAULT_TTL } from "../shared/types";

export async function evaluateAlertsForReading(reading: Reading): Promise<void> {
  const patientsContainer = getContainer("patients");
  const readingsContainer = getContainer("readings");
  const alertsContainer = getContainer("alerts");

  let patient: Patient;
  try {
    const { resource } = await patientsContainer.item(reading.patientId, reading.patientId).read<Patient>();
    if (!resource) return;
    patient = resource;
  } catch {
    return;
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

  for (const action of actions) {
    if (action.action === "create") {
      const now = new Date();
      const dateStr = now.toISOString().split("T")[0];
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
        pagerdutyDedupKey: `o2-${action.alertType}-${reading.patientId}-${dateStr}`,
        ttl: DEFAULT_TTL,
      };
      await alertsContainer.items.create(alert);
    } else if (action.action === "resolve" && action.alertId) {
      const { resource } = await alertsContainer.item(action.alertId, reading.patientId).read<Alert>();
      if (resource) {
        resource.resolvedAt = new Date().toISOString();
        await alertsContainer.item(action.alertId, reading.patientId).replace(resource);
      }
    }
  }
}
