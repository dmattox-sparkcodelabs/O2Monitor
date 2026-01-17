# O2 Relay Android App - Implementation Tasks

## Overview

This document tracks all tasks needed to implement the O2 Relay Android app as designed in `DESIGN.md`. Tasks are organized by phase, with dependencies noted.

**Legend:**
- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete
- `[B]` Blocked
- `(Pi)` Task is on Pi side
- `(Android)` Task is on Android side

---

## Phase 1: Foundation & Core Relay (MVP)

### 1.1 Pi-side API Endpoints (Pi)

These endpoints are required before the Android app can function.

- [ ] **(Pi) Create relay API blueprint**
  - New file: `src/web/relay_api.py`
  - Register blueprint in `src/web/__init__.py`
  - No auth required for relay endpoints (or use API token)

- [ ] **(Pi) GET /api/relay/status endpoint**
  - Returns: `last_reading_age_seconds`, `source`, `needs_relay`, `pi_ble_connected`
  - `needs_relay = true` when last reading > 30 seconds old
  - Used by phone to decide whether to take over

- [ ] **(Pi) POST /api/relay/reading endpoint**
  - Accepts: `spo2`, `heart_rate`, `battery`, `timestamp`, `device_id`, `queued`
  - Stores reading with `source = "android_relay"`
  - Returns: `{ "status": "ok" }`

- [ ] **(Pi) Track reading source in database**
  - Add `source` column to readings table (default: "ble_direct")
  - Modify `insert_reading()` to accept source parameter
  - Migration script if needed

- [ ] **(Pi) Pi backs off BLE when receiving relay data**
  - In state machine: if relay reading received, don't attempt BLE reconnect
  - Resume BLE attempts after 60s of no relay data
  - Add `last_relay_reading_time` to state tracking

### 1.2 Android Project Setup (Android)

- [ ] **(Android) Create Android project structure**
  - Location: `android/O2Relay/`
  - Package: `com.o2monitor.relay`
  - Min SDK: 26 (Android 8.0)
  - Target SDK: 34 (Android 14)
  - Language: Kotlin

- [ ] **(Android) Configure build.gradle.kts**
  - Kotlin version
  - Dependencies:
    - AndroidX Core KTX
    - AndroidX AppCompat
    - Material Components
    - Coroutines
    - OkHttp (for HTTP)
    - Gson (for JSON)
  - Build config for version management

- [ ] **(Android) Configure AndroidManifest.xml**
  - All permissions (see DESIGN.md)
  - Foreground service declaration
  - Boot receiver declaration
  - Application metadata

- [ ] **(Android) Create Application class**
  - Initialize logging
  - Initialize singletons (SettingsManager)
  - Handle uncaught exceptions

### 1.3 BLE Implementation (Android)

- [ ] **(Android) Create OximeterProtocol.kt**
  - `calcCrc(data: ByteArray): Byte` - CRC calculation
  - `buildReadingCommand(): ByteArray` - Build 0x17 command packet
  - `parsePacket(data: ByteArray): ParseResult` - Parse response
  - `parseReading(payload: ByteArray): OxiReading?` - Extract SpO2, HR, battery
  - Data class: `OxiReading(spo2, heartRate, battery, timestamp)`
  - Unit tests for CRC matching Python implementation

- [ ] **(Android) Create BleManager.kt**
  - Constants: `TARGET_MAC`, `RX_UUID`, `TX_UUID`
  - Callback interface: `onConnected()`, `onDisconnected()`, `onReading()`, `onError()`
  - `startScan(timeout: Long)` - Scan for device
  - `stopScan()`
  - `connect(device: BluetoothDevice)`
  - `disconnect()`
  - `requestReading()` - Send 0x17 command
  - Handle GATT callbacks
  - Buffer incoming data, parse complete packets
  - Connection state tracking

- [ ] **(Android) BLE permissions handling**
  - Check BLUETOOTH_CONNECT, BLUETOOTH_SCAN permissions
  - Check ACCESS_FINE_LOCATION (required for BLE scanning on Android 12+)
  - Request permissions flow
  - Handle permission denied gracefully

- [ ] **(Android) BLE scanning logic**
  - Filter by MAC address (primary) or device name prefix "O2M" (fallback)
  - Scan timeout (30 seconds)
  - Handle scan failures
  - Battery-efficient scanning (low latency mode only when needed)

- [ ] **(Android) GATT connection handling**
  - Connect with autoConnect=false (faster initial connection)
  - Discover services
  - Find RX and TX characteristics
  - Enable notifications on RX characteristic
  - Handle 133 GATT_ERROR (retry logic)
  - Handle disconnection events
  - Clean up resources

### 1.4 Network/API Client (Android)

- [ ] **(Android) Create ApiClient.kt**
  - Constructor takes base URL
  - OkHttp client with timeouts (connect: 10s, read: 30s)
  - Coroutine-based async methods
  - JSON parsing with Gson

- [ ] **(Android) Implement getRelayStatus()**
  - GET `/api/relay/status`
  - Parse response to `RelayStatus` data class
  - Handle network errors, timeouts
  - Return null on failure (let caller decide what to do)

- [ ] **(Android) Implement postReading()**
  - POST `/api/relay/reading`
  - Serialize `OxiReading` to JSON
  - Return success/failure boolean
  - Handle network errors gracefully

- [ ] **(Android) Create data classes**
  - `RelayStatus(timestamp, lastReadingAgeSeconds, source, needsRelay, piBleConnected)`
  - `OxiReading(spo2, heartRate, battery, timestamp, deviceId)`
  - `ApiResponse(status, message)`

### 1.5 Foreground Service (Android)

- [ ] **(Android) Create RelayService.kt**
  - Extend `Service`
  - State enum: `DORMANT`, `SCANNING`, `CONNECTED`, `QUEUING`
  - Binder for MainActivity communication
  - Lifecycle: `onCreate()`, `onStartCommand()`, `onDestroy()`

- [ ] **(Android) Notification channel setup**
  - Create channel in Application class or Service
  - Channel ID: "o2_relay_service"
  - Importance: LOW (no sound, just persistent)

- [ ] **(Android) Foreground notification**
  - Create notification with current state
  - Update notification when state changes
  - Show SpO2/HR when connected
  - Tap opens MainActivity

- [ ] **(Android) State machine implementation**
  - `transitionTo(newState)` method
  - DORMANT: Start 60s check-in timer
  - SCANNING: Start BLE scan, 30s timeout
  - CONNECTED: Start 5s reading request timer
  - Handle state-specific cleanup on exit

- [ ] **(Android) Check-in timer (DORMANT state)**
  - Every 60 seconds, call `getRelayStatus()`
  - If `needsRelay == true`, transition to SCANNING
  - Use `Handler` with `postDelayed()` or coroutine with delay

- [ ] **(Android) Reading timer (CONNECTED state)**
  - Every 5 seconds, call `requestReading()` on BleManager
  - On reading received, call `postReading()` to Pi
  - Track readings sent count

- [ ] **(Android) BLE event handling in service**
  - `onConnected()` → transition to CONNECTED
  - `onDisconnected()` → check Pi status, transition appropriately
  - `onReading()` → post to Pi, update notification
  - `onError()` → log, potentially transition state

### 1.6 Basic UI (Android)

- [ ] **(Android) Create activity_main.xml layout**
  - Status card (state, description)
  - Check-in info (last check, Pi status)
  - Start/Stop button
  - Server URL display
  - Version info footer

- [ ] **(Android) Create MainActivity.kt**
  - Bind to RelayService
  - Observe service state
  - Update UI on state changes
  - Handle Start/Stop button
  - Handle permissions flow on first launch

- [ ] **(Android) Service binding**
  - `ServiceConnection` implementation
  - Bind on `onStart()`, unbind on `onStop()`
  - Get state updates from service

- [ ] **(Android) Permission request flow**
  - On first launch, explain why permissions needed
  - Request BLE permissions
  - Request location permission
  - Handle denial gracefully (show instructions)

### 1.7 Settings Storage (Android)

- [ ] **(Android) Create SettingsManager.kt**
  - SharedPreferences wrapper
  - `serverUrl: String` (default: "http://192.168.4.100:5000")
  - `oximeterMac: String` (default: "C8:F1:6B:56:7B:F1")
  - `checkInIntervalSeconds: Int` (default: 60)
  - `deviceId: String` (auto-generated UUID on first run)

---

## Phase 2: Reliability

### 2.1 Local Queue (Android)

- [ ] **(Android) Create ReadingQueue.kt**
  - SQLite database helper
  - Table: `queued_readings(id, spo2, heart_rate, battery, timestamp, created_at)`
  - `enqueue(reading: OxiReading)`
  - `peek(limit: Int): List<QueuedReading>`
  - `remove(ids: List<Long>)`
  - `count(): Int`
  - `clear()`

- [ ] **(Android) Create database schema**
  - Database name: "o2relay.db"
  - Version: 1
  - Handle database upgrades

- [ ] **(Android) QUEUING state implementation**
  - On Pi unreachable in CONNECTED state → transition to QUEUING
  - Queue readings locally
  - Retry Pi connection every 10 seconds
  - On Pi reachable → flush queue, transition back to CONNECTED

### 2.2 Batch Upload (Pi + Android)

- [ ] **(Pi) POST /api/relay/batch endpoint**
  - Accepts: `{ "readings": [...] }`
  - Insert all readings with correct timestamps
  - Reject readings older than 24 hours
  - Return: `{ "status": "ok", "accepted": N, "rejected": M }`

- [ ] **(Android) Implement postBatch()**
  - POST `/api/relay/batch`
  - Send up to 100 readings at a time
  - On success, remove from local queue
  - Handle partial success

- [ ] **(Android) Queue flush logic**
  - When transitioning QUEUING → CONNECTED
  - Batch upload all queued readings
  - Continue normal relay after flush

### 2.3 Auto-Reconnect (Android)

- [ ] **(Android) BLE reconnect logic**
  - On disconnect in CONNECTED state, attempt reconnect
  - Exponential backoff: 5s, 10s, 20s, 30s
  - Max 3 attempts before transitioning to check Pi status
  - Reset backoff on successful connection

- [ ] **(Android) Network reconnect logic**
  - On network error, retry with backoff
  - Transition to QUEUING after 3 failures
  - Monitor network state changes
  - Auto-retry when network returns

### 2.4 Boot Receiver (Android)

- [ ] **(Android) Create BootReceiver.kt**
  - Extend `BroadcastReceiver`
  - Listen for `BOOT_COMPLETED`
  - Start RelayService if it was running before reboot
  - Use `SettingsManager` to check if service should auto-start

- [ ] **(Android) Add to manifest**
  - Receiver declaration
  - Intent filter for BOOT_COMPLETED
  - Add RECEIVE_BOOT_COMPLETED permission

- [ ] **(Android) Service auto-start setting**
  - Add `autoStartOnBoot: Boolean` to SettingsManager
  - Default: true
  - UI toggle in settings

---

## Phase 3: Polish

### 3.1 Enhanced UI (Android)

- [ ] **(Android) Current readings display**
  - Large SpO2 and HR values when connected
  - Battery indicator
  - Last reading timestamp
  - Color coding (green/yellow/red based on values)

- [ ] **(Android) Statistics display**
  - Readings sent this session
  - Readings queued
  - Time in current state
  - Session duration

- [ ] **(Android) Connection status indicators**
  - BLE connection icon/status
  - Pi connection icon/status
  - Network type (WiFi/LTE)

- [ ] **(Android) Error display**
  - Show last error message
  - Timestamp of last error
  - Clear errors button

### 3.2 Settings Screen (Android)

- [ ] **(Android) Create activity_settings.xml**
  - Server URL input field
  - Oximeter MAC input field
  - Check-in interval radio buttons (30s, 60s, 120s)
  - Auto-start on boot toggle
  - Battery optimization button
  - Check for updates button
  - Version info

- [ ] **(Android) Create SettingsActivity.kt**
  - Load settings from SettingsManager
  - Validate inputs (URL format, MAC format)
  - Save settings
  - Handle battery optimization intent

- [ ] **(Android) Battery optimization prompt**
  - Check if app is ignoring battery optimizations
  - If not, show explanation dialog
  - Launch system settings to disable optimization

- [ ] **(Android) Settings navigation**
  - Menu button in MainActivity
  - Navigate to SettingsActivity
  - Apply settings on return

### 3.3 Pi Dashboard Integration (Pi)

- [ ] **(Pi) Show relay status on dashboard**
  - Add "Source" indicator (BLE Direct / Android Relay)
  - Show phone device ID when relay active
  - Show last relay reading time

- [ ] **(Pi) Relay status in /api/status**
  - Add `relay` section to status response
  - `source`: "ble_direct" or "android_relay"
  - `relay_device_id`: phone identifier (if relay)
  - `last_relay_time`: timestamp

### 3.4 Error Handling & Logging (Android)

- [ ] **(Android) Logging infrastructure**
  - Use Android Log with consistent tags
  - Log state transitions
  - Log BLE events
  - Log API calls and responses
  - Log errors with stack traces

- [ ] **(Android) Error reporting**
  - Store last N errors in memory
  - Display in UI
  - Option to export logs (share intent)

- [ ] **(Android) Crash handling**
  - Uncaught exception handler in Application
  - Log crash to file
  - Restart service after crash

---

## Phase 4: Auto-Update

### 4.1 Pi-side APK Hosting (Pi)

- [ ] **(Pi) Create APK hosting directory**
  - Directory: `src/web/static/app/`
  - Add to `.gitignore` (don't commit APKs)

- [ ] **(Pi) Create version.json**
  - Location: `src/web/static/app/version.json`
  - Fields: `version`, `version_code`, `release_notes`, `apk_filename`, `min_version_code`

- [ ] **(Pi) GET /api/relay/app-version endpoint**
  - Read version.json
  - Return version info
  - Include APK download URL

- [ ] **(Pi) APK upload script**
  - Script to copy APK to static/app/
  - Update version.json
  - Optional: extract version from APK

### 4.2 Update Checker (Android)

- [ ] **(Android) Create UpdateChecker.kt**
  - `checkForUpdate(): UpdateInfo?`
  - Compare current version code with server
  - Return update info if newer version available

- [ ] **(Android) Update check triggers**
  - On app start
  - Daily (use WorkManager for periodic check)
  - Manual button in settings

- [ ] **(Android) Update notification**
  - Show notification when update available
  - Include version and release notes
  - Tap to download

### 4.3 APK Download & Install (Android)

- [ ] **(Android) APK download**
  - Download to app's external files directory
  - Show progress notification
  - Handle download errors

- [ ] **(Android) Install APK**
  - Use FileProvider to share APK
  - Create install intent
  - Handle REQUEST_INSTALL_PACKAGES permission

- [ ] **(Android) Update flow UI**
  - "Update available" banner in app
  - Download progress
  - "Install now" button

---

## Phase 5: Testing & Deployment

### 5.1 Unit Tests (Android)

- [ ] **(Android) CRC calculation tests**
  - Test vectors from Python implementation
  - Edge cases (empty data, single byte, etc.)

- [ ] **(Android) Packet parsing tests**
  - Valid reading packet
  - Sensor off packet (flag 0xFF)
  - Idle packet (zeros)
  - Incomplete packet
  - Multiple packets in buffer

- [ ] **(Android) State machine tests**
  - All state transitions
  - Timer behavior
  - Event handling

### 5.2 Integration Tests

- [ ] **(Android) Mock BLE device**
  - Consider using Android BLE mock library
  - Or test with real device

- [ ] **(Pi) Test relay endpoints**
  - Unit tests for relay API
  - Test with curl/httpie

- [ ] **(Both) End-to-end test**
  - Phone connects to oximeter
  - Phone relays to Pi
  - Pi stores reading
  - Verify in database

### 5.3 Manual Test Checklist

- [ ] **Test: Normal dormant operation**
  - Start app, Pi connected to oximeter
  - Verify app shows DORMANT
  - Verify check-in every 60s in logs

- [ ] **Test: Takeover scenario**
  - Pi connected, move oximeter away from Pi
  - Verify Pi loses connection
  - Verify phone detects needs_relay
  - Verify phone connects and relays

- [ ] **Test: Return to Pi scenario**
  - Phone relaying, move oximeter back to Pi
  - Disconnect phone from oximeter
  - Verify phone checks Pi status
  - Verify phone goes DORMANT

- [ ] **Test: WiFi loss**
  - Phone connected and relaying
  - Disable WiFi
  - Verify phone queues locally
  - Re-enable WiFi
  - Verify queue flushes

- [ ] **Test: App killed**
  - Phone relaying
  - Force stop app
  - Verify Pi resumes BLE attempts

- [ ] **Test: Phone reboot**
  - Phone relaying
  - Reboot phone
  - Verify app restarts
  - Verify correct state (DORMANT or resumes relay)

- [ ] **Test: LTE relay (if WireGuard configured)**
  - Leave house with phone and oximeter
  - Verify relay works over WireGuard

### 5.4 Deployment

- [ ] **(Android) Generate signed APK**
  - Create keystore (store securely!)
  - Configure signing in build.gradle
  - Build release APK

- [ ] **(Android) Version management**
  - Increment version code for each release
  - Update version name
  - Document changes

- [ ] **(Pi) Deploy first APK**
  - Copy APK to Pi
  - Update version.json
  - Verify download works

- [ ] **(Android) First install on dad's phone**
  - Enable "Install unknown apps" for browser/file manager
  - Transfer APK (email, web download, USB)
  - Install and configure
  - Test full flow

---

## Dependencies

```
Phase 1.1 (Pi API) ──────────┐
                             ├──> Phase 1.5 (Service) ──> Phase 1.6 (UI)
Phase 1.2 (Project Setup) ───┤
                             │
Phase 1.3 (BLE) ─────────────┤
                             │
Phase 1.4 (API Client) ──────┘

Phase 1 Complete ──> Phase 2 (Reliability)
                 ──> Phase 3 (Polish)

Phase 3 Complete ──> Phase 4 (Auto-Update)

All Phases ──> Phase 5 (Testing & Deployment)
```

---

## Estimated Effort

| Phase | Effort | Notes |
|-------|--------|-------|
| Phase 1 | 3-4 days | Core functionality, can test end-to-end |
| Phase 2 | 1-2 days | Queue and reliability |
| Phase 3 | 1-2 days | Polish, can ship without |
| Phase 4 | 0.5-1 day | Nice to have |
| Phase 5 | 1 day | Testing and deployment |
| **Total** | **6-10 days** | Depends on BLE debugging time |

---

## Notes

- BLE is notoriously finicky on Android. Budget extra time for debugging.
- Test on dad's actual phone model early (different manufacturers have BLE quirks).
- The CRC and packet parsing is well-documented in DESIGN.md - should be straightforward.
- Consider starting with hardcoded settings (server URL, MAC) for faster MVP.
