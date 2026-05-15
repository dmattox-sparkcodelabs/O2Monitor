# O2 Monitor v2 — Alert System

> **NOT FOR MEDICAL USE** — Proof of concept only.

## Overview

Server-side alert evaluation running in Azure Functions. Every new reading triggers threshold checks via Cosmos DB change feed. Device disconnects detected by a timer function. Notifications delivered via PagerDuty Events API v2.

## Alert Types

| Type | Trigger | Default Threshold | Default Duration | Default Severity |
|------|---------|-------------------|------------------|------------------|
| `spo2_critical` | SpO2 below threshold | < 90% | 30s | critical |
| `spo2_warning` | SpO2 below threshold | < 92% | 60s | warning |
| `hr_high` | Heart rate above threshold | > 120 BPM | 60s | high |
| `hr_low` | Heart rate below threshold | < 50 BPM | 60s | high |
| `battery_warning` | Battery below threshold | ≤ 25% | instant | warning |
| `battery_critical` | Battery below threshold | ≤ 10% | instant | critical |
| `disconnect` | No readings received | 120s gap | — | warning |

All thresholds are configurable per patient via the `alertConfig` field in the `patients` container.

## Severity Levels

| Severity | PagerDuty Mapping | Behavior |
|----------|-------------------|----------|
| `critical` | `critical` | Phone call escalation |
| `high` | `error` | SMS/push notification |
| `warning` | `warning` | Push notification only |
| `info` | `info` | Logged, no notification |

## Evaluation Logic

### Change Feed Trigger (evaluateAlerts function)

Fires on every new document in the `readings` container.

```
For each new reading:
  1. Load patient document (alertConfig)
  2. Load unresolved alerts for this patient
  
  For each threshold (spo2_critical, spo2_warning, hr_high, hr_low):
    3. Query readings from the last `durationSec` seconds
    4. If ALL readings in the window violate the threshold:
       - If no unresolved alert of this type exists → CREATE alert
       - If unresolved alert exists but resendInterval has passed → RE-TRIGGER PagerDuty
    5. If the LATEST reading does NOT violate the threshold:
       - If unresolved alert of this type exists → RESOLVE alert
  
  For battery thresholds (no duration):
    6. If current reading's battery ≤ threshold → CREATE alert (if none exists)
    7. If current reading's battery > threshold → RESOLVE alert (if one exists)
```

### Timer Trigger (checkDisconnects function)

Runs every 60 seconds.

```
For each patient:
  1. Query the latest reading timestamp
  2. Calculate secondsSinceLastReading = now - latestTimestamp
  
  If secondsSinceLastReading > disconnectAlertSec:
    3. If no unresolved `disconnect` alert → CREATE alert
    4. Push `connectionStatus: offline` via SignalR
  
  If secondsSinceLastReading ≤ disconnectAlertSec:
    5. If unresolved `disconnect` alert exists → RESOLVE alert
    6. Push `connectionStatus: online` via SignalR
```

## Deduplication

- **One unresolved alert per type per patient**: Before creating, check if an unresolved alert of the same type already exists.
- **Resend interval**: If an unresolved alert exists but the `resendIntervalSec` has elapsed since the last PagerDuty trigger, re-send. Prevents alert fatigue while ensuring persistent conditions are not silently ignored.
- **PagerDuty dedup key**: `o2-{alertType}-{patientId}-{YYYY-MM-DD}` — PagerDuty uses this to group triggers/resolves for the same incident.

## Auto-Resolution

Alerts resolve automatically when the triggering condition clears:
- SpO2/HR alerts: latest reading is within normal range
- Battery alerts: latest reading shows battery above threshold
- Disconnect alerts: a new reading arrives

Resolution actions:
1. Update alert document: set `resolvedAt` timestamp
2. Send PagerDuty `resolve` event with matching dedup key
3. Push `alertResolved` event via SignalR

## PagerDuty Integration

Uses Events API v2: `POST https://events.pagerduty.com/v2/enqueue`

### Trigger Event
```json
{
  "routing_key": "<patient or global routing key>",
  "event_action": "trigger",
  "dedup_key": "o2-spo2_critical-<patient-id>-2026-05-15",
  "payload": {
    "summary": "SpO2 Critical: 87% for 30s (Dad)",
    "severity": "critical",
    "source": "O2Monitor v2",
    "timestamp": "2026-05-15T03:22:00Z",
    "custom_details": {
      "patientName": "Dad",
      "patientId": "<uuid>",
      "spo2": 87,
      "heartRate": 72,
      "duration": "30 seconds",
      "threshold": 90
    }
  }
}
```

### Resolve Event
```json
{
  "routing_key": "<routing key>",
  "event_action": "resolve",
  "dedup_key": "o2-spo2_critical-<patient-id>-2026-05-15"
}
```

### Routing Key Priority
1. Patient-specific `pagerdutyRoutingKey` in `alertConfig`
2. Global routing key in Azure Function App Settings (`PAGERDUTY_ROUTING_KEY`)
3. If neither set: alert is logged but PagerDuty is not called

## Deferred Alert Types (Not in v2 Core)

These will be added as future vertical slices:

| Type | Reason Deferred |
|------|-----------------|
| `no_therapy_at_night` | Requires AVAPS/smart plug integration |
| `spo2_critical_on_therapy` | Requires therapy state detection |
| `vision_sleep_no_mask` | Requires vision service |
| `adapter_disconnect` | Pi-specific, not applicable |

The alert evaluation architecture supports adding new types by:
1. Adding the type to the patient's `alertConfig`
2. Adding evaluation logic to the change feed function
3. No schema changes needed — `alerts` container accepts any `alertType` string
