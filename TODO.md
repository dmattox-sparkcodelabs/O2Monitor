# O2 Monitor v2 — Implementation Tasks

> **NOT FOR MEDICAL USE** — Proof of concept only.

Each task is a vertical slice delivering one testable behavior. Every task produces something a user can exercise and verify end-to-end.

---

## ~~Slice 1: Hello World API + Cosmos DB~~ ✅

**Goal:** Prove Azure Functions + Cosmos DB work together. One function, one container, one curl command.

**What to build:**
- Initialize `api/` as Azure Functions v4 Node.js 20 TypeScript project
- `api/src/shared/cosmos.ts` — Cosmos client from connection string env var
- `api/src/shared/types.ts` — `Reading` and `Patient` TypeScript interfaces (from `docs/specs/data-model.md`)
- `api/src/functions/ingestReading.ts` — HTTP POST trigger, validates `patientId`, `spo2`, `heartRate`, `batteryLevel`, `timestamp` fields, writes to `readings` container, returns 201
- Create Cosmos DB `readings` container (partition key `/patientId`, TTL enabled)
- Manually create one test patient document in a `patients` container (partition key `/id`)
- `api/local.settings.json` (gitignored) with Cosmos connection string
- `api/package.json`, `api/tsconfig.json`, `api/host.json`

**Spec references:**
- Data model: `docs/specs/data-model.md` — `readings` container schema
- API: `docs/specs/api.md` — `POST /api/readings`

**Verify:**
1. `cd api && npm install && npm start` — Functions host starts
2. POST via curl:
   ```bash
   curl -X POST http://localhost:7071/api/readings \
     -H "Content-Type: application/json" \
     -d '{"patientId":"test-patient-1","spo2":97,"heartRate":72,"batteryLevel":85,"movement":0,"timestamp":"2026-05-15T09:30:00Z","source":"live","deviceId":"curl-test"}'
   ```
3. Response: `201 { "id": "..." }`
4. Verify document exists in Cosmos DB (Data Explorer or Cosmos emulator UI)

---

## ~~Slice 2: Query Latest Status~~ ✅

**Goal:** Read back what we wrote. Prove the query path works.

**What to build:**
- `api/src/functions/queryStatus.ts` — `GET /api/patients/:id/status`, returns latest reading + `secondsSinceReading` + `deviceOnline` (true if last reading < 120s ago)
- Reads from `readings` container, ordered by timestamp DESC, limit 1

**Spec references:**
- API: `docs/specs/api.md` — `GET /api/patients/:id/status`

**Verify:**
1. POST a reading (Slice 1)
2. `curl http://localhost:7071/api/patients/test-patient-1/status`
3. Response includes `latestReading` with correct SpO2/HR values and `secondsSinceReading`
4. Wait 2+ minutes without posting — `deviceOnline` flips to `false`

---

## ~~Slice 3: Web App Shell + Live Vitals Display~~ ✅

**Goal:** A web page that shows the latest vitals by polling the API. No auth, no real-time yet — just fetch and display.

**What to build:**
- Initialize `web/` as Next.js 14+ App Router project with TypeScript, Tailwind CSS
- `web/src/lib/types.ts` — shared TypeScript interfaces
- `web/src/lib/api.ts` — fetch wrapper, calls `GET /api/patients/:id/status`
- `web/src/app/page.tsx` — dashboard page, hardcoded patient ID for now
- `web/src/components/VitalsCard.tsx` — displays SpO2 (large, color-coded), HR, battery
- Polls `/api/patients/:id/status` every 15 seconds
- Color coding: green ≥95%, yellow 92-94%, orange 90-91%, red <90%

**Spec references:**
- Web: `docs/specs/web-app.md` — Dashboard page, VitalsCard component, color coding

**Verify:**
1. `cd web && npm install && npm run dev`
2. API running (Slice 1), POST a reading with spo2=97
3. Open `http://localhost:3000` — see green SpO2 card showing 97%, HR, battery
4. POST a reading with spo2=89
5. Page updates within 15s — SpO2 card turns red, shows 89%

---

## ~~Slice 4: SignalR Real-Time Push~~ ✅

**Goal:** Vitals update instantly on the web page without polling. Prove the SignalR pipeline works.

**What to build:**
- Create Azure SignalR Service (free tier) or configure local emulator
- `api/src/shared/signalr.ts` — helper to send messages to SignalR groups
- `api/src/functions/negotiate.ts` — SignalR negotiation endpoint
- Update `ingestReading.ts` to push `newReading` event after Cosmos write
- `web/src/hooks/useSignalR.ts` — connect to SignalR, subscribe to `newReading` events for patient group
- Update dashboard to use SignalR for live updates (keep polling as fallback)

**Spec references:**
- API: `docs/specs/api.md` — `POST /api/negotiate`, SignalR Events table
- Architecture: `docs/specs/architecture.md` — Azure SignalR Service section

**Verify:**
1. Open `http://localhost:3000` in browser
2. POST a reading via curl
3. Vitals card updates within 1-2 seconds (no 15s polling delay)
4. Open browser dev tools Network tab — confirm SignalR WebSocket connection active
5. Kill SignalR connection (disconnect network briefly) — confirm fallback to polling resumes

---

## ~~Slice 5: API Key Auth~~ ✅

**Goal:** API endpoints reject unauthenticated requests. Simple API key auth — swap for Azure AD B2C later.

**What to build:**
- `api/src/shared/auth.ts` — validates `x-api-key` header against `API_KEYS` env var (comma-separated list)
- Apply auth middleware to `ingestReading`, `queryStatus`, and `negotiate`
- `API_KEYS` in `local.settings.json` (e.g., `"dad-phone-key,david-phone-key,web-dashboard-key"`)
- Web app sends API key via header on all fetch calls and SignalR negotiate
- Update `web/src/lib/api.ts` to include the key from an env var (`NEXT_PUBLIC_API_KEY`)

**Spec references:**
- Architecture: `docs/specs/architecture.md` — Authentication & Authorization (simplified for now)

**Verify:**
1. `curl http://localhost:7071/api/patients/test-patient-1/status` — returns 401
2. `curl -H "x-api-key: test-key" http://localhost:7071/api/patients/test-patient-1/status` — returns 200
3. Web dashboard still works (sends API key automatically)
4. Invalid API key — returns 401

---

## Slice 6: Azure AD B2C Auth (Deferred)

**Goal:** Replace API key auth with Azure AD B2C for proper multi-user identity.

**Status:** Deferred — requires creating a B2C tenant in Azure portal (~30 min manual setup). Current API key auth is sufficient for development and initial use.

**What to build (when ready):**
- Set up Azure AD B2C tenant with sign-up/sign-in user flow
- Register API and Web app registrations
- Replace `x-api-key` validation with JWT validation
- Add MSAL to web app for login/logout flow
- Auto-create user documents in `users` container on first login

---

## ~~Slice 7: Patient CRUD + Access Model~~ ✅

**Goal:** Users can create patients and the system enforces who can see what. Replaces the hardcoded test patient.

**What to build:**
- Create `patientAccess` container in Cosmos DB
- `api/src/functions/managePatients.ts`:
  - `POST /api/patients` — create patient, auto-assign caller as `owner`
  - `GET /api/patients` — list patients user has access to
  - `GET /api/patients/:id` — get patient details (checks access)
- Update `ingestReading` and `queryStatus` to check `patientAccess` (user must have any role)
- Update web dashboard to fetch patient list and show a patient selector dropdown
- `web/src/hooks/usePatient.ts` — selected patient state (persisted to localStorage)
- `web/src/components/PatientSelector.tsx` — dropdown in header
- Empty state: "No patients yet — create one to get started" with create button

**Spec references:**
- Data model: `docs/specs/data-model.md` — `patients` and `patientAccess` containers
- API: `docs/specs/api.md` — `POST /api/patients`, `GET /api/patients`, `GET /api/patients/:id`
- Web: `docs/specs/web-app.md` — PatientSelector component

**Verify:**
1. Log in — see "No patients" message
2. Create a patient via curl (with Bearer token):
   ```bash
   curl -X POST http://localhost:7071/api/patients \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"name":"Dad","deviceMac":"C8:F1:6B:56:7B:F1"}'
   ```
3. Refresh dashboard — patient appears in selector dropdown
4. POST a reading for that patient — vitals display
5. `GET /api/patients` — returns patient with `role: "owner"`
6. Try querying a random patient ID — returns 403

---

## Slice 8: Live Chart (SpO2 + HR)

**Goal:** Dashboard shows an auto-scrolling line chart of SpO2 and HR over the last hour.

**What to build:**
- Add Recharts dependency to web app
- `web/src/components/LiveChart.tsx` — dual Y-axis line chart (SpO2 left, HR right)
- Loads last 1 hour of readings on mount via `GET /api/patients/:id/readings?hours=1`
- Appends new data points from SignalR `newReading` events
- SpO2 threshold zones: red background below 90%, yellow 90-92%
- `api/src/functions/queryReadings.ts` — `GET /api/patients/:id/readings?hours=N&limit=N`

**Spec references:**
- API: `docs/specs/api.md` — `GET /api/patients/:id/readings`
- Web: `docs/specs/web-app.md` — LiveChart component, threshold zones

**Verify:**
1. Seed 1 hour of readings (script that POSTs one every 5s with varying SpO2 88-99)
2. Open dashboard — chart shows the full hour of data with dual axes
3. Threshold zones visible (red/yellow bands)
4. POST a new reading — chart appends the point in real-time
5. Chart auto-scrolls to show most recent data

---

## Slice 9: Chart Time Range Toggle

**Goal:** User can switch the live chart between 1h, 6h, and 24h views.

**What to build:**
- Add toggle buttons (1h | 6h | 24h) above the chart
- On toggle: re-fetch readings for the selected range
- Continue appending SignalR data regardless of selected range
- Adjust chart X-axis scale and tick formatting per range

**Spec references:**
- Web: `docs/specs/web-app.md` — Dashboard time range toggle

**Verify:**
1. Seed 24 hours of readings
2. Default view: 1h — chart shows ~720 points
3. Click 6h — chart re-renders with 6 hours of data, X-axis rescales
4. Click 24h — full day visible
5. POST a new reading — appends to whichever view is active

---

## Slice 10: Alert Evaluation (SpO2 Critical)

**Goal:** When SpO2 stays below threshold for the configured duration, an alert document appears in Cosmos. Start with just one alert type to prove the change feed pipeline.

**What to build:**
- `api/src/functions/evaluateAlerts.ts` — Cosmos change feed trigger on `readings` container
- On each new reading: load patient's `alertConfig`, query last N seconds of readings
- Evaluate `spo2_critical` only: if all readings in window below threshold → create alert in `alerts` container
- Auto-resolve: if latest reading is above threshold and an unresolved alert exists → set `resolvedAt`
- Create `alerts` container in Cosmos DB (partition key `/patientId`, TTL enabled)
- Deduplication: skip if unresolved alert of same type already exists

**Spec references:**
- Alerts: `docs/specs/alerts.md` — Evaluation Logic, Change Feed Trigger section
- Data model: `docs/specs/data-model.md` — `alerts` container

**Verify:**
1. POST readings with spo2=88 every 5 seconds for 35 seconds (exceeds 30s critical duration)
2. Check `alerts` container — document exists with `alertType: "spo2_critical"`, `severity: "critical"`
3. POST a reading with spo2=96
4. Check alert document — `resolvedAt` is now set
5. POST spo2=88 again for 35s — new alert created (not a duplicate of the resolved one)

---

## Slice 11: All Alert Types

**Goal:** Extend alert evaluation to cover all v2 alert types.

**What to build:**
- Add to `evaluateAlerts.ts`: `spo2_warning`, `hr_high`, `hr_low`, `battery_warning`, `battery_critical`
- Each follows same pattern: check threshold + duration window → create/resolve alert
- Battery alerts are instantaneous (no duration window)
- Resend interval: if unresolved alert exists and `resendIntervalSec` has passed, mark for re-notification (flag in alert doc)

**Spec references:**
- Alerts: `docs/specs/alerts.md` — Alert Types table, full evaluation logic
- Data model: `docs/specs/data-model.md` — `patients.alertConfig` fields

**Verify:**
1. POST readings with heartRate=130 for 65s → `hr_high` alert created
2. POST reading with heartRate=70 → alert resolves
3. POST reading with batteryLevel=8 → `battery_critical` alert created instantly (no duration)
4. POST reading with batteryLevel=50 → battery alert resolves
5. POST readings with spo2=91 for 65s → `spo2_warning` alert (not critical)

---

## Slice 12: PagerDuty Integration

**Goal:** Alerts trigger PagerDuty incidents and auto-resolve them.

**What to build:**
- `api/src/shared/pagerduty.ts` — PagerDuty Events API v2 client (trigger, resolve)
- Dedup key format: `o2-{alertType}-{patientId}-{YYYY-MM-DD}`
- Severity mapping: critical→critical, high→error, warning→warning, info→info
- Routing key: patient-specific `pagerdutyRoutingKey` or global env var `PAGERDUTY_ROUTING_KEY`
- Wire into `evaluateAlerts.ts`: call PagerDuty on alert create and resolve
- Handle resend: re-trigger PagerDuty when `resendIntervalSec` elapses for an unresolved alert

**Spec references:**
- Alerts: `docs/specs/alerts.md` — PagerDuty Integration section, dedup keys, severity mapping

**Verify:**
1. Set `PAGERDUTY_ROUTING_KEY` to a test/sandbox PD service routing key
2. POST readings triggering spo2_critical (spo2=88 for 35s)
3. Check PagerDuty dashboard — incident created with summary "SpO2 Critical: 88% for 30s"
4. POST reading with spo2=96 (recover)
5. PagerDuty incident auto-resolves
6. Wait `resendIntervalSec` with ongoing spo2=88 readings — PagerDuty re-triggers

---

## Slice 13: Disconnect Detection

**Goal:** Detect when a patient's device stops sending data and fire a disconnect alert.

**What to build:**
- `api/src/functions/checkDisconnects.ts` — Timer trigger, runs every 60 seconds
- For each patient: query latest reading timestamp
- If `now - latestTimestamp > disconnectAlertSec` → create `disconnect` alert (if none unresolved)
- Push `connectionStatus` event via SignalR (`{ patientId, deviceOnline: false, secondsSinceReading }`)
- When a new reading arrives for a patient with an unresolved disconnect alert → resolve it + push `connectionStatus: online`

**Spec references:**
- Alerts: `docs/specs/alerts.md` — Disconnect detection (Timer Trigger section)
- API: `docs/specs/api.md` — `connectionStatus` SignalR event

**Verify:**
1. POST readings normally — `connectionStatus: online` on web dashboard
2. Stop posting for 2+ minutes
3. After timer fires: `disconnect` alert in Cosmos, PagerDuty triggers, web dashboard shows "Offline"
4. Resume posting readings — disconnect alert resolves, dashboard shows "Online"

---

## Slice 14: Alert Banner on Dashboard

**Goal:** Active alerts show as a prominent banner on the web dashboard, appearing and disappearing in real-time.

**What to build:**
- `web/src/components/AlertBanner.tsx` — displays active alerts at top of dashboard
- Severity coloring: red (critical), orange (high), yellow (warning)
- Shows alert message text and timestamp
- Subscribe to SignalR `alertTriggered` and `alertResolved` events
- On page load: fetch active alerts from `GET /api/patients/:id/status` (already includes `activeAlerts`)

**Spec references:**
- Web: `docs/specs/web-app.md` — AlertBanner component
- API: `docs/specs/api.md` — `GET /api/patients/:id/status` response, SignalR alert events

**Verify:**
1. Open dashboard — no banner (no active alerts)
2. Trigger spo2_critical alert (POST low SpO2 readings for 35s)
3. Red banner appears within seconds: "SpO2 Critical: 88% for 30 seconds"
4. POST a recovery reading (spo2=96)
5. Banner disappears within seconds
6. Refresh page with an active alert — banner shows on load (not just from SignalR)

---

## Slice 15: Alerts History Page

**Goal:** Dedicated page to browse alert history with filtering.

**What to build:**
- `api/src/functions/queryAlerts.ts` — `GET /api/patients/:id/alerts?days=N&status=active|resolved`
- `web/src/app/alerts/page.tsx` — alert history page
- `web/src/components/AlertTable.tsx` — table with columns: Time, Type, Severity (color badge), Message, Status
- Tabs: Active | Resolved | All
- Severity and type filter dropdowns
- Add "Alerts" link to navigation

**Spec references:**
- API: `docs/specs/api.md` — `GET /api/patients/:id/alerts`
- Web: `docs/specs/web-app.md` — `/alerts` page, AlertTable

**Verify:**
1. Trigger and resolve a few different alert types (spo2_critical, hr_high, battery_warning)
2. Navigate to `/alerts` — all alerts appear in table
3. Click "Active" tab — only unresolved alerts shown
4. Click "Resolved" tab — only resolved alerts shown
5. Filter by severity "critical" — only critical alerts shown
6. Confirm severity badges are color-coded

---

## Slice 16: Settings Page — Alert Thresholds

**Goal:** Patient owners can view and edit alert thresholds from the web UI.

**What to build:**
- `api/src/functions/managePatients.ts` — add `PUT /api/patients/:id` (owner role check, updates `alertConfig`)
- `web/src/app/settings/page.tsx` — settings page
- `web/src/components/ThresholdEditor.tsx` — editable table of all alert thresholds (threshold, duration, severity per type)
- Patient info section: name and device MAC (editable)
- PagerDuty routing key field (masked input) and resend interval
- Save button → `PUT /api/patients/:id`
- Owner-only gate: non-owners see "Contact the owner to change settings"
- Add "Settings" link to navigation

**Spec references:**
- API: `docs/specs/api.md` — `PUT /api/patients/:id`
- Data model: `docs/specs/data-model.md` — `patients.alertConfig` fields
- Web: `docs/specs/web-app.md` — `/settings` page, ThresholdEditor

**Verify:**
1. Log in as patient owner, navigate to `/settings`
2. Change SpO2 critical threshold from 90 to 88, click Save
3. `GET /api/patients/:id` returns `alertConfig.spo2CriticalThreshold = 88`
4. POST readings with spo2=89 for 35s — NO alert (threshold is now 88)
5. POST readings with spo2=87 for 35s — alert fires
6. Log in as a viewer (if one exists) — settings page shows read-only message

---

## Slice 17: Access Management

**Goal:** Patient owners can invite family members and assign roles.

**What to build:**
- `api/src/functions/manageAccess.ts`:
  - `POST /api/patients/:id/access` — invite by email + role (owner only)
  - `DELETE /api/patients/:id/access/:userId` — revoke access (owner only, can't revoke self)
- `web/src/components/AccessManager.tsx` — table of users with access (email, role), invite form, remove button
- Add to settings page below threshold editor
- Pending invites: if email not yet in `users` container, store in `patientAccess` anyway — access granted when they first log in

**Spec references:**
- API: `docs/specs/api.md` — `POST /api/patients/:id/access`, `DELETE /api/patients/:id/access/:userId`
- Data model: `docs/specs/data-model.md` — `patientAccess` container
- Web: `docs/specs/web-app.md` — AccessManager component

**Verify:**
1. Navigate to `/settings` → Access Management section
2. Invite `sister@gmail.com` as `viewer`
3. Check `patientAccess` container — document created
4. Log in as sister (create B2C account with that email) — dashboard shows dad's data
5. Sister navigates to `/settings` — sees read-only message
6. As owner, revoke sister's access
7. Sister refreshes — patient no longer visible

---

## Slice 18: History Page — Readings Chart + Table

**Goal:** Browse historical SpO2/HR data with a date range picker.

**What to build:**
- `web/src/app/history/page.tsx` — history page
- `web/src/components/HistoryChart.tsx` — SpO2 + HR trend chart (Recharts)
- Date range presets: 7d | 30d | 90d | Custom (calendar picker)
- Readings table: timestamp, SpO2, HR, battery — paginated, newest first
- Stats summary bar: avg SpO2, min SpO2, avg HR, reading count for selected range
- Uses `GET /api/patients/:id/readings?hours=N` for data
- Add "History" link to navigation

**Spec references:**
- API: `docs/specs/api.md` — `GET /api/patients/:id/readings`
- Web: `docs/specs/web-app.md` — `/history` page, HistoryChart

**Verify:**
1. Seed several days of test readings
2. Navigate to `/history` — default 7d view shows chart and table
3. Switch to 30d — chart rescales, more data
4. Stats bar shows correct avg/min SpO2 values
5. Table is paginated, newest first
6. Custom date range: select specific 2-day window — only that data shown

---

## Slice 19: Nightly Aggregation

**Goal:** Raw readings older than 90 days are replaced by daily summaries. A timer function computes nightly stats.

**What to build:**
- `api/src/functions/nightlyAggregation.ts` — Timer trigger (08:00 UTC daily)
- For each patient: query readings for completed night using `nightDate = (timestamp + 12h).date()`
- Compute: readingCount, durationSeconds, spo2 avg/min/max, hr avg/min/max, timeBelow90Seconds, timeBelow88Seconds, pctBelow90, pctBelow88
- Upsert to `dailySummaries` container (idempotent by `id = patientId:nightDate`)
- Create `dailySummaries` container in Cosmos DB (partition key `/patientId`, no TTL)
- `api/src/functions/querySummaries.ts` — `GET /api/patients/:id/summaries?days=N`

**Spec references:**
- Data model: `docs/specs/data-model.md` — `dailySummaries` container, night date logic
- API: `docs/specs/api.md` — `GET /api/patients/:id/summaries`, Timer functions

**Verify:**
1. Seed a full night of readings (22:00-06:00, every 15s, SpO2 varying 90-98)
2. Manually trigger aggregation function
3. Check `dailySummaries` container — document with correct nightDate, stats match seeded data
4. `GET /api/patients/:id/summaries?days=30` — returns the summary
5. Re-trigger aggregation — same document updated (upsert, not duplicate)

---

## Slice 20: Nightly Summary Table on History Page

**Goal:** History page shows nightly summaries and seamlessly blends raw + summary data.

**What to build:**
- `web/src/components/NightlySummaryTable.tsx` — one row per night: date, avg SpO2, min SpO2, time below 90%, avg HR, count
- Add to history page below the charts
- For date ranges beyond 90 days: fetch from summaries endpoint instead of readings
- Long-term trend chart: plot avg SpO2 per night from summaries

**Spec references:**
- Web: `docs/specs/web-app.md` — NightlySummaryTable, history page long-term trends
- API: `docs/specs/api.md` — `GET /api/patients/:id/summaries`

**Verify:**
1. Have both raw readings (recent) and daily summaries (older) in Cosmos
2. Navigate to `/history`, select 90d range — see chart with raw data
3. Select "all time" or a range spanning summary-only dates — chart uses summary data
4. Nightly summary table shows each night's stats
5. Click a recent night row — drills down to raw readings for that night

---

## Slice 21: Android App — Project Setup + Login

**Goal:** Android app shell that authenticates with Azure AD B2C and fetches the patient list.

**What to build:**
- Initialize `android/O2Monitor/` — Kotlin, min SDK 26, Jetpack Compose, Hilt
- Gradle dependencies: MSAL, OkHttp, Room, Hilt, Compose
- `network/AuthManager.kt` — MSAL B2C login (interactive + silent refresh)
- `network/ApiClient.kt` — `getPatients()`, `getUserProfile()` with Bearer token
- Login screen (Compose): "Sign In" button → MSAL redirect
- Patient select screen: list from `GET /api/patients`, tap to select, save to SharedPreferences
- Minimal dashboard screen: shows selected patient name + "Not monitoring yet"

**Spec references:**
- Android: `docs/specs/android-app.md` — Tech Stack, AuthManager, Screens (Login, Patient Select)

**Verify:**
1. Build and install APK
2. Open app — login screen appears
3. Tap "Sign In" — B2C login flow in browser
4. After login — patient select screen shows your patients
5. Select a patient — dashboard screen shows patient name
6. Kill and reopen app — still logged in (silent token refresh), same patient selected

---

## Slice 22: Android BLE Protocol Layer

**Goal:** Port the BLE protocol to Kotlin and prove it parses real oximeter packets correctly.

**What to build:**
- `ble/BleProtocol.kt` — pure Kotlin (no Android deps):
  - `calcCrc(data: ByteArray): Byte`
  - `buildCommand(cmd: Byte): ByteArray`
  - `PacketParser` class with `feed(data: ByteArray): List<Packet>`
  - `parseReading(payload: ByteArray): OxiReading?`
- Unit tests: test CRC against known values from `archive/windows/protocol.py`, test packet parsing with captured byte sequences from v1

**Spec references:**
- Android: `docs/specs/android-app.md` — BLE Protocol section, BleProtocol.kt
- Reference: `archive/windows/protocol.py` (Python implementation to port from)
- Reference: `archive/android/O2Relay/app/src/test/java/com/o2monitor/relay/OximeterProtocolTest.kt` (existing Kotlin tests)

**Verify:**
1. Unit tests pass: CRC matches Python implementation for known inputs
2. `buildCommand(0x17)` produces `AA 17 E8 00 00 00 00 <crc>` (same as Python)
3. `parseReading()` correctly extracts SpO2, HR, battery from a captured 13-byte payload
4. `PacketParser` handles fragmented input (feed partial data, then rest — yields one complete packet)

---

## Slice 23: Android BLE Service + Live Readings

**Goal:** Android app connects to the oximeter, reads vitals every 5 seconds, and displays them.

**What to build:**
- `ble/BleState.kt` — state enum: IDLE, SCANNING, CONNECTING, READING, RECONNECTING
- `ble/BleService.kt` — foreground service:
  - Scan for device by MAC or name prefix "O2M"
  - Connect, discover services, enable notifications on RX UUID
  - Poll every 5s via command 0x17
  - Foreground notification: "Monitoring SpO2 — 97% | HR 72"
  - Stale watchdog: force reconnect if no reading for 60s
  - Exponential backoff: 5s → 10s → 20s → 30s
- Update dashboard screen: show live SpO2, HR, battery, BLE state
- Start/Stop toggle button on dashboard
- Runtime permission flow: request BLE + location on first start

**Spec references:**
- Android: `docs/specs/android-app.md` — BleService, state machine, foreground notification, permissions

**Verify:**
1. Put Checkme O2 Max on finger
2. Open app, tap Start
3. App scans → connects → shows "Connected"
4. Dashboard shows SpO2, HR, battery updating every 5s
5. Notification bar shows "Monitoring SpO2 — 97% | HR 72"
6. Remove oximeter — app shows "Reconnecting..." after 60s
7. Put oximeter back — reconnects and resumes

---

## Slice 24: Android Cloud Upload + Offline Queue

**Goal:** Readings from the Android BLE service are uploaded to Azure and appear on the web dashboard.

**What to build:**
- `data/ReadingEntity.kt`, `data/ReadingDao.kt`, `data/AppDatabase.kt` — Room offline queue
- `data/ReadingRepository.kt` — enqueue every reading, flushToCloud (single POST), pruneExpired (24h)
- Wire BleService: on each reading → `repository.enqueue()` → `repository.flushToCloud()`
- On network failure: reading stays in queue, retried next cycle
- Update dashboard: show upload status (online/offline, queue count)

**Spec references:**
- Android: `docs/specs/android-app.md` — ReadingRepository, offline queue flow
- API: `docs/specs/api.md` — `POST /api/readings`

**Verify:**
1. Android app reading oximeter + uploading
2. Open web dashboard — vitals appear within 1-2 seconds of each Android reading
3. Turn off phone WiFi — Android shows "Offline (N readings queued)", queue count grows
4. Turn WiFi back on — queue flushes, web dashboard catches up
5. Check Cosmos DB — no duplicate readings (same timestamps not double-inserted)

---

## Slice 25: Android Batch Upload

**Goal:** Offline queue flushes efficiently using the batch endpoint.

**What to build:**
- `api/src/functions/ingestBatch.ts` — `POST /api/readings/batch`, deduplicates by `(patientId, timestamp)`, bulk writes, returns accepted/rejected counts
- Only push most recent reading to SignalR (avoid flooding)
- Update Android `ReadingRepository.flushToCloud()` to use batch endpoint when queue > 1

**Spec references:**
- API: `docs/specs/api.md` — `POST /api/readings/batch`
- Android: `docs/specs/android-app.md` — ReadingRepository

**Verify:**
1. Disconnect phone WiFi for 5 minutes while BLE reads
2. Queue shows ~60 readings
3. Reconnect WiFi — app flushes as one batch
4. API returns `{ "accepted": 60, "rejected": 0 }`
5. Web dashboard shows latest reading (not replaying 60 updates)
6. Repeat disconnect/reconnect — no duplicates in Cosmos

---

## Slice 26: Android Boot Receiver + Battery Optimization

**Goal:** App survives reboots and Android battery management.

**What to build:**
- `util/BootReceiver.kt` — starts BleService on `BOOT_COMPLETED`
- Register in AndroidManifest
- Request `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` on first launch
- Settings screen: device info, account info, logout button, app version

**Spec references:**
- Android: `docs/specs/android-app.md` — Boot receiver, battery optimization, Settings screen

**Verify:**
1. App is monitoring, reboot the phone
2. After boot completes — notification reappears, BLE service resumes automatically
3. Check battery settings — app is listed as "Not optimized"
4. Leave running overnight — confirm readings still flowing in the morning

---

## Slice 27: Responsive Web Design + Mobile Polish

**Goal:** Web dashboard works well on phones and tablets with large, readable vitals.

**What to build:**
- Responsive layout breakpoints:
  - Desktop (≥1024px): side-by-side vitals + chart
  - Tablet (768-1023px): stacked vitals, full-width chart
  - Mobile (<768px): single column, bottom nav bar
- Large font vitals: 4-5rem desktop, 3rem mobile
- Color-coded card backgrounds (not just text) for SpO2 ranges
- Dark mode: Tailwind dark variant, respect system preference
- Touch-friendly tap targets on mobile

**Spec references:**
- Web: `docs/specs/web-app.md` — Responsive Design section

**Verify:**
1. Desktop browser — full layout with side-by-side elements
2. Resize to 768px — stacks, chart full-width
3. Resize to 375px — single column, bottom nav, large vitals
4. Open on actual phone — numbers readable from arm's length
5. Toggle system dark mode — dashboard theme switches
6. Navigate all pages on mobile — no layout breakage

---

## Slice 28: CI/CD — API Deployment

**Goal:** Pushing to main auto-deploys Azure Functions.

**What to build:**
- `.github/workflows/deploy-api.yml` — trigger on push to `main` with changes in `api/`
- Steps: checkout, install deps, build TypeScript, run tests, deploy to Azure Functions
- Azure publish profile stored as GitHub secret
- Document Azure resource provisioning steps in `docs/specs/architecture.md`

**Spec references:**
- Architecture: `docs/specs/architecture.md` — Deployment section

**Verify:**
1. Push a change to `api/src/` on main
2. GitHub Actions workflow triggers and succeeds
3. `curl https://<func-app>.azurewebsites.net/api/users/me` responds (with auth)

---

## Slice 29: CI/CD — Web + Android Deployment

**Goal:** Web app and Android APK deploy automatically.

**What to build:**
- `.github/workflows/deploy-web.yml` — build Next.js static export, deploy to Azure Static Web Apps
- `.github/workflows/build-android.yml` — build debug APK, upload to GitHub Releases
- Secrets: Static Web Apps deployment token, signing key for Android (if release build)

**Spec references:**
- Architecture: `docs/specs/architecture.md` — Deployment section

**Verify:**
1. Push a change to `web/` — Static Web App deploys, accessible at public URL
2. Push a change to `android/` — APK artifact in GitHub Releases
3. Download APK, install, connects to production Azure backend
4. Full loop: Android reading → Azure → web dashboard at production URL
