import { InvocationContext } from "@azure/functions";

export interface SignalRMessage {
  target: string;
  arguments: unknown[];
  groupName?: string;
}

export function buildNewReadingMessage(
  patientId: string,
  reading: { spo2: number; heartRate: number; batteryLevel: number; timestamp: string }
): SignalRMessage {
  return {
    target: "newReading",
    groupName: `patient:${patientId}`,
    arguments: [{
      patientId,
      spo2: reading.spo2,
      heartRate: reading.heartRate,
      batteryLevel: reading.batteryLevel,
      timestamp: reading.timestamp,
    }],
  };
}

export function buildAlertTriggeredMessage(
  patientId: string,
  alert: { id: string; alertType: string; severity: string; message: string }
): SignalRMessage {
  return {
    target: "alertTriggered",
    groupName: `patient:${patientId}`,
    arguments: [{ patientId, id: alert.id, alertType: alert.alertType, severity: alert.severity, message: alert.message }],
  };
}

export function buildAlertResolvedMessage(
  patientId: string,
  alert: { id: string; alertType: string; resolvedAt: string }
): SignalRMessage {
  return {
    target: "alertResolved",
    groupName: `patient:${patientId}`,
    arguments: [{ patientId, id: alert.id, alertType: alert.alertType, resolvedAt: alert.resolvedAt }],
  };
}
