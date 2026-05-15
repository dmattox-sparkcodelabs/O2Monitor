# O2 Monitor v2 — API Reference

> **NOT FOR MEDICAL USE** — Proof of concept only.

## Overview

Azure Functions app (Node.js 20, TypeScript, Consumption plan). All endpoints require Azure AD B2C JWT token unless noted.

Base URL: `https://<function-app>.azurewebsites.net/api`

## Authentication

All requests include:
```
Authorization: Bearer <b2c-access-token>
```

The JWT is validated by middleware that extracts the user's B2C object ID and resolves it to a `userId` in the `users` container. Authorization (role checks) happens per-endpoint.

## Ingest Endpoints

### POST /api/readings

Ingest a single reading from an Android device. Writes to Cosmos DB and pushes to SignalR.

**Auth:** Any authenticated user with `owner` or `responder` role on the patient.

**Request:**
```json
{
  "patientId": "uuid",
  "spo2": 97,
  "heartRate": 72,
  "batteryLevel": 85,
  "movement": 0,
  "timestamp": "2026-05-15T09:30:00Z",
  "source": "live",
  "deviceId": "pixel-7a"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid"
}
```

**Side effects:**
- Writes reading to `readings` container (with TTL)
- Pushes `newReading` event to SignalR group `patient:{patientId}`
- Triggers alert evaluation via Cosmos change feed

### POST /api/readings/batch

Flush queued offline readings.

**Auth:** Any authenticated user with `owner` or `responder` role on each patient in the batch.

**Request:**
```json
{
  "readings": [
    {
      "patientId": "uuid",
      "spo2": 97,
      "heartRate": 72,
      "batteryLevel": 85,
      "movement": 0,
      "timestamp": "2026-05-15T09:30:00Z",
      "source": "live",
      "deviceId": "pixel-7a"
    }
  ]
}
```

**Response:** `200 OK`
```json
{
  "accepted": 15,
  "rejected": 0
}
```

**Notes:**
- Readings are deduplicated by `(patientId, timestamp)` — duplicate timestamps are silently skipped
- Only the most recent reading in the batch triggers a SignalR push (avoids flooding)

## Query Endpoints

### GET /api/patients

List patients the authenticated user has access to.

**Response:** `200 OK`
```json
[
  {
    "id": "uuid",
    "name": "Dad",
    "deviceMac": "C8:F1:6B:56:7B:F1",
    "role": "owner"
  }
]
```

### GET /api/patients/:id

Get patient details including alert configuration. Requires any role on the patient.

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "name": "Dad",
  "deviceMac": "C8:F1:6B:56:7B:F1",
  "deviceName": "O2M 2781",
  "alertConfig": { ... },
  "createdAt": "2026-05-15T14:00:00Z",
  "role": "owner"
}
```

### GET /api/patients/:id/status

Combined live status: latest reading + connection state + active alerts. Primary endpoint for dashboard.

**Response:** `200 OK`
```json
{
  "patientId": "uuid",
  "patientName": "Dad",
  "latestReading": {
    "spo2": 97,
    "heartRate": 72,
    "batteryLevel": 85,
    "timestamp": "2026-05-15T09:30:00Z",
    "deviceId": "pixel-7a"
  },
  "secondsSinceReading": 5,
  "deviceOnline": true,
  "activeAlerts": [
    {
      "id": "uuid",
      "alertType": "spo2_warning",
      "severity": "warning",
      "message": "SpO2 at 91% for 60 seconds",
      "timestamp": "2026-05-15T09:29:00Z"
    }
  ]
}
```

### GET /api/patients/:id/readings

Recent readings. Supports time range filtering.

**Auth:** Any role (`owner`, `responder`, or `viewer`) on the patient.

**Query params:**
- `hours` (int, default 1, max 24) — how far back to query
- `limit` (int, default 1000, max 5000) — max readings returned

**Response:** `200 OK`
```json
{
  "readings": [
    {
      "id": "uuid",
      "timestamp": "2026-05-15T09:30:00Z",
      "spo2": 97,
      "heartRate": 72,
      "batteryLevel": 85,
      "movement": 0,
      "source": "live",
      "deviceId": "pixel-7a"
    }
  ],
  "count": 720
}
```

### GET /api/patients/:id/readings/latest

Single most recent reading.

**Auth:** Any role (`owner`, `responder`, or `viewer`) on the patient.

**Response:** `200 OK`
```json
{
  "spo2": 97,
  "heartRate": 72,
  "batteryLevel": 85,
  "timestamp": "2026-05-15T09:30:00Z",
  "secondsAgo": 5
}
```

### GET /api/patients/:id/summaries

Daily summary data for long-term trends.

**Auth:** Any role (`owner`, `responder`, or `viewer`) on the patient.

**Query params:**
- `days` (int, default 30, max 365) — how many days back

**Response:** `200 OK`
```json
{
  "summaries": [
    {
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
      "pctBelow88": 0.07
    }
  ]
}

**Notes:** Daily summaries are pre-computed nightly at 08:00 UTC (3 AM CDT) by the `nightlyAggregation` timer function and kept indefinitely. For dates within 90 days, use the raw `readings` endpoint. For older dates, use this summaries endpoint.
```

### GET /api/patients/:id/alerts

Alert history.

**Auth:** Any role (`owner`, `responder`, or `viewer`) on the patient.

**Query params:**
- `days` (int, default 7, max 90) — how far back
- `status` (string, optional) — `"active"` or `"resolved"`

**Response:** `200 OK`
```json
{
  "alerts": [
    {
      "id": "uuid",
      "alertType": "spo2_critical",
      "severity": "critical",
      "message": "SpO2 dropped to 87% for 30 seconds",
      "spo2": 87,
      "heartRate": 72,
      "timestamp": "2026-05-15T03:22:00Z",
      "resolvedAt": "2026-05-15T03:23:30Z"
    }
  ]
}
```

## Management Endpoints

### POST /api/patients

Create a new patient. Caller becomes `owner` automatically.

**Request:**
```json
{
  "name": "Dad",
  "deviceMac": "C8:F1:6B:56:7B:F1",
  "deviceName": "O2M 2781"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "name": "Dad",
  "deviceMac": "C8:F1:6B:56:7B:F1",
  "alertConfig": { ... },
  "createdBy": "user-uuid"
}
```

### PUT /api/patients/:id

Update patient details and/or alert configuration. Requires `owner` role.

**Request (partial update):**
```json
{
  "name": "Dad",
  "alertConfig": {
    "spo2CriticalThreshold": 88,
    "spo2CriticalDurationSec": 45
  }
}
```

**Response:** `200 OK` — returns updated patient.

### POST /api/patients/:id/access

Grant a user access to a patient. Requires `owner` role.

**Request:**
```json
{
  "email": "sister@gmail.com",
  "role": "viewer"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "userId": "user-uuid",
  "role": "viewer"
}
```

**Notes:** If the email doesn't match an existing user, the invite is "pending" — access is granted when they first log in with that email.

### DELETE /api/patients/:id/access/:userId

Revoke a user's access. Requires `owner` role. Cannot revoke your own owner access.

**Response:** `204 No Content`

### GET /api/users/me

Get current user profile and list of patients they have access to.

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "email": "dmattox@gmail.com",
  "displayName": "David",
  "patients": [
    { "id": "uuid", "name": "Dad", "role": "owner" },
    { "id": "uuid", "name": "David", "role": "owner" }
  ]
}
```

## SignalR

### POST /api/negotiate

Returns SignalR connection info. Called by web client on page load.

**Response:** `200 OK`
```json
{
  "url": "https://o2monitor-signalr.service.signalr.net/client/",
  "accessToken": "..."
}
```

### SignalR Events

Clients join group `patient:{patientId}` after connecting.

| Event | Payload | When |
|-------|---------|------|
| `newReading` | `{ patientId, spo2, heartRate, batteryLevel, timestamp }` | Each new reading ingested |
| `alertTriggered` | `{ patientId, id, alertType, severity, message }` | New alert fires |
| `alertResolved` | `{ patientId, id, alertType, resolvedAt }` | Alert condition clears |
| `connectionStatus` | `{ patientId, deviceOnline, secondsSinceReading }` | Device goes online/offline |

## Rate Limiting

- `POST /api/readings`: Max 20 requests per minute per user
- `POST /api/readings/batch`: Max 10 requests per minute per user
- Query endpoints: No application-level limit (rely on Cosmos DB RU throttling)
- Management endpoints: Max 30 requests per minute per user

Rate limiting is advisory for v2 core — implement if abuse is observed. The 429 error code is reserved for this purpose.

## Error Responses

All errors follow a consistent format:

```json
{
  "error": {
    "code": "PATIENT_NOT_FOUND",
    "message": "Patient with id 'xyz' not found"
  }
}
```

| HTTP Status | Code | Meaning |
|-------------|------|---------|
| 400 | `INVALID_REQUEST` | Missing or malformed fields |
| 401 | `UNAUTHORIZED` | Missing or invalid JWT |
| 403 | `FORBIDDEN` | Valid JWT but insufficient role |
| 404 | `PATIENT_NOT_FOUND` | Patient ID doesn't exist |
| 409 | `DUPLICATE` | Resource already exists |
| 429 | `RATE_LIMITED` | Too many requests |
| 500 | `INTERNAL_ERROR` | Server error |

## Timer-Triggered Functions

These are not HTTP endpoints but run on schedules:

| Function | Schedule | Purpose |
|----------|----------|---------|
| `checkDisconnects` | Every 60 seconds | Detect patients with no recent readings, fire disconnect alerts |
| `nightlyAggregation` | 08:00 UTC daily (3 AM CDT) | Roll up raw readings into daily summaries |
