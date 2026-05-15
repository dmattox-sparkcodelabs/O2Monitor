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
