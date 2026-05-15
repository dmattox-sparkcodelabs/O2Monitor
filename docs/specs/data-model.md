# O2 Monitor v2 — Data Model

> **NOT FOR MEDICAL USE** — Proof of concept only.

## Cosmos DB Configuration

- **API**: NoSQL
- **Capacity**: Serverless (pay-per-RU, no provisioned throughput)
- **Consistency**: Session (default)
- **Region**: South Central US (closest to McAllen, TX)

## Containers

### `users` (partition key: `/id`)

Stores registered user profiles. Linked to Azure AD B2C via `b2cObjectId`.

```json
{
  "id": "uuid",
  "email": "dmattox@gmail.com",
  "displayName": "David",
  "b2cObjectId": "azure-ad-b2c-object-id",
  "createdAt": "2026-05-15T14:00:00Z"
}
```

### `patients` (partition key: `/id`)

Each oximeter wearer is a patient. Stores device info and alert configuration.

```json
{
  "id": "uuid",
  "name": "Dad",
  "deviceMac": "C8:F1:6B:56:7B:F1",
  "deviceName": "O2M 2781",
  "alertConfig": {
    "spo2CriticalThreshold": 90,
    "spo2CriticalDurationSec": 30,
    "spo2WarningThreshold": 92,
    "spo2WarningDurationSec": 60,
    "hrHighThreshold": 120,
    "hrLowThreshold": 50,
    "hrDurationSec": 60,
    "batteryWarningThreshold": 25,
    "batteryCriticalThreshold": 10,
    "disconnectAlertSec": 120,
    "pagerdutyRoutingKey": "",
    "resendIntervalSec": 300
  },
  "createdAt": "2026-05-15T14:00:00Z",
  "createdBy": "user-uuid"
}
```

**Alert config fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `spo2CriticalThreshold` | int | 90 | SpO2 % below which critical alert fires |
| `spo2CriticalDurationSec` | int | 30 | Seconds SpO2 must stay below threshold |
| `spo2WarningThreshold` | int | 92 | SpO2 % for warning alert |
| `spo2WarningDurationSec` | int | 60 | Seconds for warning |
| `hrHighThreshold` | int | 120 | HR above which alert fires |
| `hrLowThreshold` | int | 50 | HR below which alert fires |
| `hrDurationSec` | int | 60 | Seconds HR must stay outside range |
| `batteryWarningThreshold` | int | 25 | Battery % for warning |
| `batteryCriticalThreshold` | int | 10 | Battery % for critical |
| `disconnectAlertSec` | int | 120 | Seconds without data before disconnect alert |
| `pagerdutyRoutingKey` | string | "" | Per-patient PD key (falls back to global) |
| `resendIntervalSec` | int | 300 | Cooldown before re-sending same alert type |

### `patientAccess` (partition key: `/patientId`)

Maps users to patients with roles.

```json
{
  "id": "uuid",
  "patientId": "patient-uuid",
  "userId": "user-uuid",
  "role": "owner",
  "createdAt": "2026-05-15T14:00:00Z"
}
```

**Roles:**
- `owner` — configure alerts/thresholds, manage access, view all data
- `responder` — receives PagerDuty alerts, view all data
- `viewer` — read-only dashboard access

### `readings` (partition key: `/patientId`)

Raw oximeter readings. Auto-deleted after 90 days via TTL.

```json
{
  "id": "uuid",
  "patientId": "patient-uuid",
  "timestamp": "2026-05-15T09:30:00Z",
  "spo2": 97,
  "heartRate": 72,
  "batteryLevel": 85,
  "movement": 0,
  "source": "live",
  "deviceId": "pixel-7a",
  "ttl": 7776000
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `patientId` | string | FK to patients container |
| `timestamp` | string (ISO 8601) | Reading time in UTC |
| `spo2` | int (0-100) | Blood oxygen saturation percentage |
| `heartRate` | int (0-300) | Heart rate in BPM |
| `batteryLevel` | int (0-100) | Oximeter battery percentage |
| `movement` | int | Motion indicator from device |
| `source` | string | `"live"` (real-time poll) or `"history"` (downloaded file) |
| `deviceId` | string | Android device identifier |
| `ttl` | int | 7776000 (90 days in seconds) |

**Indexing:** Composite index on `(patientId, timestamp DESC)` for efficient range queries.

### `dailySummaries` (partition key: `/patientId`)

Aggregated nightly stats. No TTL — kept indefinitely for long-term trends.

```json
{
  "id": "patient-uuid:2026-05-15",
  "patientId": "patient-uuid",
  "nightDate": "2026-05-15",
  "readingCount": 8640,
  "durationSeconds": 43200,
  "spo2Avg": 95.2,
  "spo2Min": 88,
  "spo2Max": 99,
  "hrAvg": 68,
  "hrMin": 52,
  "hrMax": 94,
  "timeBelow90Seconds": 120,
  "timeBelow88Seconds": 30,
  "pctBelow90": 0.28,
  "pctBelow88": 0.07,
  "createdAt": "2026-05-16T08:00:00Z"
}
```

**Night date logic:** `nightDate = (timestamp + 12 hours).date()`. This groups overnight sleep sessions into a single logical night.

Examples (all timestamps in UTC):
- `2026-05-14T23:30:00Z` + 12h = `2026-05-15T11:30:00Z` → nightDate = `"2026-05-15"`
- `2026-05-15T03:00:00Z` + 12h = `2026-05-15T15:00:00Z` → nightDate = `"2026-05-15"`
- `2026-05-15T11:00:00Z` + 12h = `2026-05-15T23:00:00Z` → nightDate = `"2026-05-15"`
- `2026-05-15T12:00:00Z` + 12h = `2026-05-16T00:00:00Z` → nightDate = `"2026-05-16"`

This means readings from approximately 12:00 UTC (7 AM CDT) through 11:59 UTC the next day group together — covering a full overnight sleep window for the CDT timezone.

**Summary fields:**

| Field | Type | Description |
|-------|------|-------------|
| `readingCount` | int | Total valid readings in the night |
| `durationSeconds` | int | Time span from first to last reading |
| `spo2Avg` | float | Mean SpO2 |
| `spo2Min` | int | Lowest SpO2 |
| `spo2Max` | int | Highest SpO2 |
| `hrAvg` | float | Mean heart rate |
| `hrMin` | int | Lowest heart rate |
| `hrMax` | int | Highest heart rate |
| `timeBelow90Seconds` | int | Total seconds with SpO2 < 90% |
| `timeBelow88Seconds` | int | Total seconds with SpO2 < 88% |
| `pctBelow90` | float | Percentage of time below 90% |
| `pctBelow88` | float | Percentage of time below 88% |

### `alerts` (partition key: `/patientId`)

Alert events. TTL 90 days.

```json
{
  "id": "uuid",
  "patientId": "patient-uuid",
  "alertType": "spo2_critical",
  "severity": "critical",
  "message": "SpO2 dropped to 87% for 30 seconds",
  "spo2": 87,
  "heartRate": 72,
  "timestamp": "2026-05-15T03:22:00Z",
  "resolvedAt": null,
  "pagerdutyDedupKey": "o2-spo2_critical-patient-uuid-2026-05-15",
  "ttl": 7776000
}
```

**Alert types:** `spo2_critical`, `spo2_warning`, `hr_high`, `hr_low`, `battery_warning`, `battery_critical`, `disconnect`

**Severity levels:** `critical`, `high`, `warning`, `info`
