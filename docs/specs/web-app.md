# O2 Monitor v2 — Web App

> **NOT FOR MEDICAL USE** — Proof of concept only.

## Overview

Next.js web application for viewing live vitals, historical trends, alerts, and managing patient settings. Deployed as a static export to Azure Static Web Apps (free tier).

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | Next.js 14+ (App Router) |
| Deployment | Azure Static Web Apps (static export) |
| Auth | `@azure/msal-react` (Azure AD B2C) |
| Real-time | `@microsoft/signalr` |
| Charts | Recharts |
| Styling | Tailwind CSS |
| TypeScript | Yes |

## Authentication

MSAL redirect flow:
1. Unauthenticated user visits any page → redirect to `/login`
2. `/login` initiates B2C login (email/password)
3. B2C redirects back with token
4. Token stored by MSAL, auto-refreshed
5. All API calls include `Authorization: Bearer <token>`

## Real-Time Connection

1. On page load, authenticated client calls `POST /api/negotiate`
2. Receives SignalR connection URL + access token
3. Connects to SignalR, joins group `patient:{selectedPatientId}`
4. Receives events: `newReading`, `alertTriggered`, `alertResolved`, `connectionStatus`
5. UI updates instantly — no polling for live data

Reconnection: SignalR client has built-in auto-reconnect with exponential backoff.

## Pages

### `/login`
- App title + disclaimer
- "Sign In" button → MSAL B2C redirect
- Minimal page, no dashboard content visible without auth

### `/` (Dashboard) — requires auth
Primary monitoring view.

**Header:**
- Patient selector dropdown (if user has access to multiple patients)
- Navigation: Dashboard | History | Alerts | Settings

**Vitals Cards (prominent, large font):**
- **SpO2** — large number with % symbol, color-coded background
  - Green: ≥ 95%
  - Yellow: 92-94%
  - Orange: 90-91%
  - Red: < 90%
- **Heart Rate** — large number with "bpm" label
  - Green: 50-120 BPM
  - Red: outside range
- **Battery** — percentage with icon
- **Connection Status** — "Online" (green) / "Offline" (red) with seconds since last reading

**Alert Banner:**
- Shows at top if any active (unresolved) alerts
- Severity color: red (critical), orange (high), yellow (warning)
- Alert message text
- Dismisses when alert resolves (via SignalR event)

**Live Chart:**
- SpO2 and HR plotted over time (dual Y-axis)
- Time range toggle: 1h | 6h | 24h
- Auto-scrolling as new readings arrive via SignalR
- Threshold zones: red below 90%, yellow 90-92% (SpO2); red outside 50-120 (HR)
- Data source: `GET /api/patients/:id/readings?hours=N` on load, then SignalR appends

### `/history` — requires auth
Historical trends and nightly summaries.

**Date Range Picker:**
- Preset buttons: 7d | 30d | 90d | Custom
- Custom: calendar date range selector

**Charts:**
- SpO2 trend (line chart with threshold zones)
- HR trend (line chart)
- For dates within 90 days: raw readings from `GET /api/patients/:id/readings`
- For dates beyond 90 days: daily summaries from `GET /api/patients/:id/summaries`

**Nightly Summary Table:**
- One row per night: date, avg SpO2, min SpO2, time below 90%, avg HR, reading count
- Sortable columns
- Click row to drill down into that night's raw data (if within 90 days)

### `/alerts` — requires auth
Alert history and management.

**Tabs:** Active | Resolved | All

**Alert Table:**
- Columns: Time, Type, Severity (color badge), Message, SpO2, HR, Status
- Severity filter dropdown
- Type filter dropdown
- Pagination

**Data source:** `GET /api/patients/:id/alerts?days=N&status=X`

### `/settings` — requires auth, `owner` role

**Patient Info:**
- Name (editable)
- Device MAC (editable)
- Device name

**Alert Thresholds:**
Table format (matching v1 settings page pattern):

| Alert | Threshold | Duration | Severity |
|-------|-----------|----------|----------|
| SpO2 Critical | < 90% | 30s | Critical |
| SpO2 Warning | < 92% | 60s | Warning |
| HR High | > 120 BPM | 60s | High |
| HR Low | < 50 BPM | 60s | High |
| Battery Warning | ≤ 25% | — | Warning |
| Battery Critical | ≤ 10% | — | Critical |
| Disconnect | 120s no data | — | Warning |

All values editable. Save button → `PUT /api/patients/:id`.

**PagerDuty:**
- Routing key field (masked input)
- Resend interval (seconds)

**Access Management:**
- Table of users with access: email, role, actions
- "Invite User" form: email + role selector
- Remove access button (with confirmation)

## Responsive Design

- **Desktop (≥1024px):** Full layout, charts side-by-side
- **Tablet (768-1023px):** Stacked vitals, full-width charts
- **Mobile (<768px):** Single column, large vitals cards, simplified charts

Large font option: vitals cards use 4-5rem font on desktop, 3rem on mobile. Dad's eyesight needs big numbers.

## Project Structure

```
web/
├── package.json
├── next.config.js
├── tailwind.config.js
├── tsconfig.json
├── src/
│   ├── app/
│   │   ├── layout.tsx              # root layout, MSAL provider, nav
│   │   ├── page.tsx                # dashboard (default route)
│   │   ├── login/page.tsx
│   │   ├── history/page.tsx
│   │   ├── alerts/page.tsx
│   │   └── settings/page.tsx
│   ├── components/
│   │   ├── VitalsCard.tsx          # SpO2/HR/Battery display
│   │   ├── LiveChart.tsx           # real-time Recharts chart
│   │   ├── HistoryChart.tsx        # historical trend chart
│   │   ├── AlertBanner.tsx         # active alert display
│   │   ├── AlertTable.tsx          # alert history table
│   │   ├── PatientSelector.tsx     # patient dropdown
│   │   ├── ThresholdEditor.tsx     # settings threshold table
│   │   ├── AccessManager.tsx       # user access CRUD
│   │   └── NightlySummaryTable.tsx # history summary rows
│   ├── hooks/
│   │   ├── useSignalR.ts           # SignalR connection + events
│   │   ├── useAuth.ts              # MSAL wrapper
│   │   ├── usePatient.ts           # selected patient state
│   │   └── useApi.ts               # fetch wrapper with auth
│   └── lib/
│       ├── api.ts                  # API client functions
│       ├── auth.ts                 # MSAL config (B2C tenant, scopes)
│       └── types.ts                # shared TypeScript interfaces
```
