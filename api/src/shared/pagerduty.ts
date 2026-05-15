const PD_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue";

export function mapSeverity(severity: string): string {
  switch (severity) {
    case "critical": return "critical";
    case "high": return "error";
    case "warning": return "warning";
    case "info": return "info";
    default: return "warning";
  }
}

export function getRoutingKey(patientKey: string): string | null {
  if (patientKey) return patientKey;
  const globalKey = process.env.PAGERDUTY_ROUTING_KEY ?? "";
  if (globalKey) return globalKey;
  return null;
}

interface TriggerParams {
  routingKey: string;
  dedupKey: string;
  summary: string;
  severity: string;
  patientName: string;
  patientId: string;
  spo2: number | null;
  heartRate: number | null;
}

export function buildTriggerEvent(params: TriggerParams) {
  return {
    routing_key: params.routingKey,
    event_action: "trigger" as const,
    dedup_key: params.dedupKey,
    payload: {
      summary: params.summary,
      severity: mapSeverity(params.severity),
      source: "O2Monitor v2",
      timestamp: new Date().toISOString(),
      custom_details: {
        patientName: params.patientName,
        patientId: params.patientId,
        spo2: params.spo2,
        heartRate: params.heartRate,
      },
    },
  };
}

export function buildResolveEvent(routingKey: string, dedupKey: string) {
  return {
    routing_key: routingKey,
    event_action: "resolve" as const,
    dedup_key: dedupKey,
  };
}

export async function sendPagerDutyEvent(event: Record<string, unknown>): Promise<boolean> {
  try {
    const res = await fetch(PD_EVENTS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(event),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function triggerAlert(
  routingKey: string,
  dedupKey: string,
  summary: string,
  severity: string,
  patientName: string,
  patientId: string,
  spo2: number | null,
  heartRate: number | null
): Promise<boolean> {
  const event = buildTriggerEvent({
    routingKey, dedupKey, summary, severity, patientName, patientId, spo2, heartRate,
  });
  return sendPagerDutyEvent(event);
}

export async function resolveAlert(routingKey: string, dedupKey: string): Promise<boolean> {
  const event = buildResolveEvent(routingKey, dedupKey);
  return sendPagerDutyEvent(event);
}
