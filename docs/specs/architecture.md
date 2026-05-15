# O2 Monitor v2 — Architecture

> **NOT FOR MEDICAL USE** — Proof of concept only.

## Overview

Cloud-connected pulse oximetry monitoring. Android phones read BLE oximeters, push data to Azure, and web + mobile frontends provide dashboards and alerting.

```
[Checkme O2 Max] --BLE--> [Android App] --HTTPS--> [Azure Functions]
                                                        |
                                              +---------+---------+
                                              |         |         |
                                        [Cosmos DB] [SignalR] [PagerDuty]
                                              |         |
                                        [Nightly    [Next.js Web App]
                                         Aggregation]
```

## Components

### Android App (BLE Reader + Uploader)
- Kotlin, Jetpack Compose, Hilt, Room, MSAL
- Foreground service maintains BLE connection to Checkme O2 Max
- Reads vitals every 5 seconds via BLE command 0x17
- POSTs readings to Azure Functions API
- Queues locally (Room DB) when offline, flushes on reconnect
- See: [android-app.md](android-app.md)

### Azure Functions API (Backend)
- Node.js 20, TypeScript, Consumption plan (serverless)
- HTTP triggers for ingest, queries, and management
- Cosmos change feed trigger for alert evaluation
- Timer triggers for disconnect detection and nightly aggregation
- SignalR output bindings for real-time push to web clients
- Azure AD B2C JWT validation on all endpoints
- See: [api.md](api.md)

### Cosmos DB (Data Store)
- Serverless capacity mode
- Containers: `users`, `patients`, `patientAccess`, `readings`, `dailySummaries`, `alerts`
- TTL-based retention: 90 days for raw readings and alerts
- Daily summaries kept indefinitely
- See: [data-model.md](data-model.md)

### Next.js Web App (Dashboard)
- Static export deployed to Azure Static Web Apps (free tier)
- MSAL authentication (Azure AD B2C)
- SignalR client for real-time vitals updates
- Recharts for historical visualization
- Tailwind CSS, responsive (desktop + mobile)
- See: [web-app.md](web-app.md)

### Alert System
- Cosmos change feed evaluates thresholds on every new reading
- Timer function detects device disconnects (no new data)
- PagerDuty Events API v2 for notifications
- Per-patient configurable thresholds and severity mapping
- See: [alerts.md](alerts.md)

### Azure SignalR Service
- Free tier (20 connections, 20k messages/day)
- Managed WebSocket infrastructure
- Groups scoped by patientId for access control
- Events: `newReading`, `alertTriggered`, `alertResolved`, `connectionStatus`

## Authentication & Authorization

- **Identity**: Azure AD B2C (email/password, social login optional)
- **Android**: MSAL for Android, silent token refresh
- **Web**: `@azure/msal-react`, redirect flow
- **API**: JWT validation middleware on all Azure Functions
- **Authorization**: Patient + Role model
  - `owner`: full control (configure, manage access)
  - `responder`: gets PagerDuty alerts, full read access
  - `viewer`: read-only dashboard access

## Infrastructure

| Resource | SKU | Est. Cost/mo |
|----------|-----|-------------|
| Azure Functions | Consumption | ~$0-2 |
| Cosmos DB | Serverless | ~$2-5 |
| SignalR Service | Free | $0 |
| Azure AD B2C | Free (50k MAU) | $0 |
| Static Web Apps | Free | $0 |
| Application Insights | Free (5GB) | $0 |

**Total: ~$2-7/month**

## Deployment

- **Functions**: GitHub Actions → Azure Functions on push to `main`
- **Web**: GitHub Actions → build static export → Azure Static Web Apps
- **Android**: GitHub Actions → build APK → GitHub Releases (sideload)
- **Secrets**: Azure Key Vault, referenced by Functions App Settings

## Monitoring

- Application Insights for function metrics and errors
- Cosmos DB RU consumption metrics
- Custom metric: readings-per-minute per patient

## Deferred (Not in v2 Core)

- AVAPS/therapy monitoring (smart plug)
- History file download from oximeter
- ODI calculation
- Vision/camera-based sleep monitoring
- No-therapy-at-night alerts
- Local audio alerts
