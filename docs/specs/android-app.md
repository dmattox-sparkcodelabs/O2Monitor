# O2 Monitor v2 — Android App

> **NOT FOR MEDICAL USE** — Proof of concept only.

## Overview

Fresh Kotlin Android app. Connects to Checkme O2 Max oximeter via BLE, reads vitals every 5 seconds, and uploads to Azure Functions API. Queues readings locally when offline.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Kotlin |
| Min SDK | 26 (Android 8.0) |
| UI | Jetpack Compose |
| DI | Hilt |
| Local DB | Room |
| Networking | OkHttp |
| Auth | MSAL (Azure AD B2C) |
| Architecture | MVVM |

## BLE Protocol

Ported from `archive/windows/protocol.py` — the cleanest implementation.

### UUIDs
- **RX** (device → host notifications): `0734594a-a8e7-4b1a-a6b1-cd5243059a57`
- **TX** (host → device writes): `8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3`

### Packet Structure
```
Request:  0xAA | cmd | cmd^0xFF | block(LE 2B) | len(LE 2B) | payload | crc
Response: 0x55 | status | status^0xFF | block(LE 2B) | len(LE 2B) | payload | crc
```

### CRC-8
Polynomial 0x07, same algorithm as `archive/windows/protocol.py:calc_crc()`.

### Command 0x17 (Read Sensors)
Request: empty payload. Response payload (13 bytes):
- Byte 0: SpO2 (0-100)
- Byte 1: Heart Rate (BPM)
- Byte 2: Flag (0xFF = sensor off, 0x00 with zeros = idle)
- Byte 7: Battery (0-100)
- Byte 9: Movement

**Validity:** Skip if flag == 0xFF or (flag == 0x00 && spo2 == 0 && hr == 0).

### Device Discovery
- Scan for device name prefix `"O2M"` or specific MAC address
- Scan timeout: 30 seconds
- Connection timeout: 10 seconds

## Core Components

### BleProtocol.kt (pure Kotlin, no Android deps)

Stateless packet building and parsing:
- `buildCommand(cmd: Byte): ByteArray` — builds request packet
- `calcCrc(data: ByteArray): Byte` — CRC-8 calculation
- `PacketParser` — stateful parser for fragmented BLE notifications
  - `feed(data: ByteArray): List<Packet>` — buffers and yields complete packets
- `parseReading(payload: ByteArray): OxiReading?` — extracts vitals from 0x17 response

### BleService.kt (Foreground Service)

State machine:
```
IDLE → SCANNING → CONNECTING → READING → RECONNECTING
                                  ↑            |
                                  +------------+
```

- **IDLE**: Not started or explicitly stopped
- **SCANNING**: BLE scan in progress (30s timeout → RECONNECTING)
- **CONNECTING**: GATT connection and service discovery in progress (10s timeout)
- **READING**: Connected, polling every 5 seconds
- **RECONNECTING**: Waiting before next attempt (exponential backoff: 5s → 10s → 20s → 30s cap)

Foreground notification:
- Ongoing, shows current state: "Monitoring SpO2 — 97% | HR 72" or "Scanning..." or "Reconnecting..."
- Updated on every reading

Watchdog:
- If no reading received for 60 seconds while in READING state → force disconnect and transition to RECONNECTING
- Catches "connected but silent" failure mode (same issue Pi had)

Lifecycle:
- Started by `MainActivity` or `BootReceiver`
- Survives app backgrounding (foreground service)
- Requests battery optimization exemption

### ReadingRepository.kt

Room-backed offline queue:

```kotlin
@Entity(tableName = "reading_queue")
data class ReadingEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val patientId: String,
    val timestamp: String,  // ISO 8601 UTC
    val spo2: Int,
    val heartRate: Int,
    val batteryLevel: Int,
    val movement: Int,
    val source: String,     // "live"
    val deviceId: String,
    val createdAt: Long     // System.currentTimeMillis()
)
```

Operations:
- `enqueue(reading)` — insert into Room
- `flushToCloud(limit = 100)` — batch POST queued readings, delete on success
- `pruneExpired(maxAgeHours = 24)` — drop stale queued readings
- `pendingCount()` — for UI display

Flow:
1. BleService gets a reading
2. Calls `repository.enqueue(reading)`
3. Calls `repository.flushToCloud()` — attempts batch upload
4. On network failure: reading stays in queue, retried on next reading cycle
5. On success: uploaded readings deleted from Room

### ApiClient.kt

OkHttp-based client with MSAL token management:

- `postReading(reading)` → `POST /api/readings`
- `postBatch(readings)` → `POST /api/readings/batch`
- `getPatients()` → `GET /api/patients`
- `getPatientStatus(patientId)` → `GET /api/patients/:id/status`

Timeouts: connect 10s, read 15s, write 15s.

Error handling: returns `Result<T>` — never throws. Network errors return `Result.failure()`.

### AuthManager.kt

MSAL wrapper:
- `acquireTokenSilent()` — cached/refresh token
- `acquireTokenInteractive(activity)` — B2C login redirect
- `getAccessToken()` — returns current valid token or null
- `isLoggedIn()` — check auth state
- `logout()` — clear token cache

## Screens

### Login Screen
- Single "Sign In" button → MSAL B2C redirect
- App logo and disclaimer text
- On success: navigate to Patient Select or Dashboard

### Patient Select Screen
- List of patients from `GET /api/patients`
- Tap to select which patient this phone monitors
- Selection saved to SharedPreferences
- Shown on first login or when changing patients

### Dashboard Screen
- Current SpO2 (large, color-coded): green ≥95, yellow 92-94, orange 90-91, red <90
- Current Heart Rate (large)
- Battery level
- BLE connection status (scanning/connected/reconnecting)
- Azure upload status (online/offline, pending queue count)
- Last reading timestamp
- Start/Stop service toggle

### Settings Screen
- Selected patient (tap to change)
- Device MAC address (auto-discovered or manual entry)
- Upload status (readings in queue)
- Account info (email, logout button)
- App version

## Permissions

```xml
<uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE" />
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
```

Runtime permission flow: request BLE + location permissions on first launch before enabling scanning.

## Battery Optimization

- Request `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` on first launch
- Foreground service with ongoing notification prevents process kill
- BLE connection is maintained (not scan/reconnect cycles) — power efficient
- Network batching: queue locally on failure, don't retry per-reading
