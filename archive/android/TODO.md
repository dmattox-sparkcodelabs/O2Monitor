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

## Phase 0: Development Environment Setup (Priority)

These tasks must be completed before any Android development can begin.

### 0.1 Install Android Studio

- [x] **Download and install Android Studio**
  - Download from https://developer.android.com/studio
  - Run installer, follow prompts
  - Installed to: `C:\Program Files\Android\Android Studio`

- [x] **Complete Android Studio first-run setup**
  - Accept licenses
  - Choose "Standard" installation type
  - SDK components downloaded successfully

### 0.2 SDK Configuration

- [x] **Install required SDK components**
  - SDK Location: `C:\Users\dmatt\AppData\Local\Android\Sdk`
  - SDK Platforms: Android 36 (API 36) - newer than planned, backwards compatible
  - SDK Tools:
    - Build-Tools 36.1.0
    - Platform-Tools (ADB 36.0.2)
    - Emulator installed

- [ ] **Verify SDK environment variables (optional but recommended)**
  - `ANDROID_HOME` pointing to SDK location
  - Add `platform-tools` to PATH for command-line ADB

### 0.3 Device Setup

Choose emulator OR physical device (physical recommended for BLE testing):

- [x] **Option A: Set up Android Emulator**
  - AVD created during Android Studio setup: "Medium Phone API 36.1"
  - Android 16 (API 36), x86_64, Google Play enabled
  - Emulator starts and connects via ADB (emulator-5554)
  - Note: Emulator cannot test real BLE - only for UI development

- [ ] **Option B: Set up physical device (for BLE testing later)**
  - Enable Developer Options on phone:
    - Settings → About Phone → Tap "Build number" 7 times
  - Enable USB Debugging:
    - Settings → Developer Options → USB Debugging → ON
  - Connect phone via USB cable
  - Accept "Allow USB debugging" prompt on phone
  - *Deferred: Will need physical access or ADB over WiFi*

### 0.4 Verify Setup

- [x] **Verify ADB connection**
  - ADB version: 36.0.2
  - Emulator connected: emulator-5554
  - Status: device (ready)

- [x] **Create test project to verify toolchain**
  - Created actual O2Relay project instead of throwaway test
  - Build successful with Gradle 8.11.1
  - App installs and runs on emulator
  - Toolchain verified working

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

- [x] **(Android) Create Android project structure**
  - Location: `android/O2Relay/`
  - Package: `com.o2monitor.relay`
  - Min SDK: 26 (Android 8.0)
  - Target SDK: 36 (Android 16) - updated from plan
  - Language: Kotlin

- [x] **(Android) Configure build.gradle.kts**
  - Kotlin 2.1.0, AGP 8.9.1
  - Dependencies configured:
    - AndroidX Core KTX, AppCompat, Material, Activity, ConstraintLayout
    - Coroutines (core + android)
    - OkHttp, Gson
  - Version catalog (libs.versions.toml)
  - ViewBinding and BuildConfig enabled

- [x] **(Android) Configure AndroidManifest.xml**
  - All BLE permissions (BLUETOOTH_CONNECT, BLUETOOTH_SCAN, etc.)
  - Location permissions for BLE scanning
  - Foreground service with connectedDevice type
  - Boot receiver declaration
  - POST_NOTIFICATIONS permission

- [x] **(Android) Create Application class**
  - Initialize logging
  - Set up notification channels
  - Handle uncaught exceptions
  - File: `O2RelayApplication.kt`

### 1.3 BLE Implementation (Android)

- [x] **(Android) Create OximeterProtocol.kt**
  - `calcCrc(data: ByteArray): Byte` - CRC calculation
  - `buildReadingCommand(): ByteArray` - Build 0x17 command packet
  - `parsePacket(data: ByteArray): ParseResult` - Parse response
  - `parseReading(payload: ByteArray): OxiReading?` - Extract SpO2, HR, battery
  - Data class: `OxiReading(spo2, heartRate, battery, timestamp, movement)`
  - Sealed class `ParseResult` with Success/Incomplete/Error variants
  - 14 unit tests passing (OximeterProtocolTest.kt)

- [x] **(Android) Create BleManager.kt**
  - Constants: `TARGET_MAC`, `RX_UUID`, `TX_UUID` (from OximeterProtocol)
  - Callback interface: `onConnected()`, `onDisconnected()`, `onReading()`, `onError()`, `onScanResult()`, `onScanFailed()`
  - State enum: IDLE, SCANNING, CONNECTING, DISCOVERING_SERVICES, ENABLING_NOTIFICATIONS, CONNECTED, DISCONNECTING
  - `startScan(timeout: Long)` - Scan for device with timeout
  - `stopScan()` - Cancel scan
  - `connect(device: BluetoothDevice)` - Connect to discovered device
  - `connectToTarget()` - Connect directly by MAC address
  - `disconnect()` - Graceful disconnect
  - `requestReading()` - Send 0x17 command
  - GATT callbacks for connection, service discovery, notifications
  - Data buffering and packet parsing via OximeterProtocol
  - Connection state tracking with timeouts

- [x] **(Android) BLE permissions handling**
  - Created `BlePermissions.kt` helper object
  - Version-aware permission detection (Android 12+ vs older)
  - Check BLUETOOTH_CONNECT, BLUETOOTH_SCAN (API 31+)
  - Check ACCESS_FINE_LOCATION (API 23-30)
  - Permission request flow with rationale
  - Result processing helper

- [x] **(Android) BLE scanning logic**
  - Filter by MAC address (primary) using ScanFilter
  - Fallback to device name prefix "O2M" if MAC invalid
  - Configurable scan timeout (default 30 seconds)
  - Balanced scan mode for battery efficiency
  - Auto-connect on device found

- [x] **(Android) GATT connection handling**
  - Connect with autoConnect=false and TRANSPORT_LE
  - Connection timeout (10 seconds)
  - Service and characteristic discovery
  - Find RX/TX characteristics by UUID
  - Enable notifications via CCCD descriptor
  - Handle API 33+ characteristic/descriptor methods
  - Graceful disconnect with cleanup
  - Note: GATT_ERROR 133 retry logic deferred to RelayService

### 1.4 Network/API Client (Android)

- [x] **(Android) Create ApiClient.kt**
  - Constructor takes base URL and deviceId
  - OkHttp client with timeouts (connect: 10s, read: 30s, write: 30s)
  - Coroutine-based async methods (suspend functions on Dispatchers.IO)
  - JSON parsing with Gson and @SerializedName annotations
  - 15 unit tests passing (ApiClientTest.kt with MockWebServer)

- [x] **(Android) Implement getRelayStatus()**
  - GET `/api/relay/status`
  - Returns `RelayStatus?` (null on error)
  - Handles network errors, timeouts gracefully

- [x] **(Android) Implement postReading()**
  - POST `/api/relay/reading`
  - Accepts `OxiReading` and optional `queued` flag
  - Returns `Boolean` success/failure

- [x] **(Android) Implement postBatch()**
  - POST `/api/relay/batch`
  - Accepts list of readings for batch upload
  - Returns `BatchResponse?` with accepted/rejected counts

- [x] **(Android) Implement getAppVersion()**
  - GET `/api/relay/app-version`
  - Returns `AppVersion?` for update checking

- [x] **(Android) Create data classes**
  - `RelayStatus` - Pi status response
  - `ReadingRequest` - Single reading POST body
  - `BatchRequest/BatchResponse` - Batch upload
  - `AppVersion` - Version check response
  - `ApiResponse` - Generic status response

### 1.5 Foreground Service (Android)

- [x] **(Android) Create RelayService.kt**
  - Extends `Service` with full lifecycle management
  - State enum: `STOPPED`, `DORMANT`, `SCANNING`, `CONNECTED`, `QUEUING`
  - `RelayBinder` for MainActivity communication
  - `StateListener` interface for UI updates
  - Intent actions: `ACTION_START`, `ACTION_STOP`
  - Coroutine scope for async operations

- [x] **(Android) Notification channel setup**
  - Channel created in `O2RelayApplication` (already done in Phase 1.2)
  - Channel ID: "o2_relay_service"
  - Importance: LOW (no sound, persistent)

- [x] **(Android) Foreground notification**
  - Dynamic content based on state
  - Shows SpO2/HR when connected
  - Tap opens MainActivity
  - Stop action button
  - Uses system Bluetooth icon

- [x] **(Android) State machine implementation**
  - `transitionTo(newState)` with exit/enter state handling
  - DORMANT: 60s check-in timer, initial check-in on enter
  - SCANNING: 30s BLE scan timeout
  - CONNECTED: 5s reading request timer
  - QUEUING: 10s Pi retry timer
  - Proper cleanup on state exit

- [x] **(Android) Check-in timer (DORMANT state)**
  - Handler-based timer with 60s interval
  - Calls `getRelayStatus()` via ApiClient
  - Transitions to SCANNING if `needsRelay == true`
  - Updates `lastPiStatus` for UI

- [x] **(Android) Reading timer (CONNECTED state)**
  - Handler-based timer with 5s interval
  - Calls `requestReading()` on BleManager
  - Posts reading to Pi via ApiClient
  - Transitions to QUEUING on Pi unreachable
  - Tracks `readingsSentCount` and `readingsQueuedCount`

- [x] **(Android) BLE event handling in service**
  - `onConnected()` → transition to CONNECTED
  - `onDisconnected()` → check Pi status, go DORMANT or SCANNING
  - `onReading()` → post to Pi, update notification
  - `onError()` → notify listener, transition to DORMANT on scan failure
  - `onScanResult()` → status update
  - `onScanFailed()` → transition to DORMANT

### 1.6 Basic UI (Android)

- [x] **(Android) Create activity_main.xml layout**
  - Status card (state, description)
  - Readings card (SpO2, HR, Battery) - shown when connected
  - Check-in info (last check, Pi status)
  - Stats text (sent/queued counts)
  - Error text display
  - Start/Stop button
  - Server URL display
  - Version info footer

- [x] **(Android) Create MainActivity.kt**
  - Bind to RelayService
  - Observe service state via StateListener interface
  - Update UI on state changes
  - Handle Start/Stop button
  - Handle permissions flow on first launch

- [x] **(Android) Service binding**
  - `ServiceConnection` implementation
  - Bind on `onStart()`, unbind on `onStop()`
  - Get state updates from service via StateListener

- [x] **(Android) Permission request flow**
  - ActivityResultContracts for modern permission handling
  - Request BLE permissions (version-aware)
  - Request location permission (Android <12)
  - Handle denial gracefully (show error message)

### 1.7 Settings Storage (Android)

- [x] **(Android) Create SettingsManager.kt**
  - SharedPreferences wrapper with property accessors
  - `serverUrl: String` (default: "http://10.6.0.7:5000" - Pi via WireGuard VPN)
  - `oximeterMac: String` (default: "C8:F1:6B:56:7B:F1")
  - `checkInIntervalSeconds: Int` (default: 60, constrained 10-300)
  - `deviceId: String` (auto-generated "android_XXXXXXXX" on first run)
  - `autoStartOnBoot: Boolean` (default: true)
  - `serviceEnabled: Boolean` (tracks if service was running)
  - Validation methods: `isValidServerUrl()`, `isValidMacAddress()`
  - `resetToDefaults()` method
  - 10 unit tests (SettingsManagerTest.kt)

- [x] **(Android) Integrate SettingsManager into RelayService**
  - Service uses settings for server URL, oximeter MAC, device ID
  - Check-in interval is configurable from settings
  - `serviceEnabled` persisted on start/stop for reboot recovery
  - Public accessor: `getSettings()`

- [x] **(Android) Integrate SettingsManager into MainActivity**
  - Server URL displayed from settings
  - Device MAC displayed from settings
  - Settings initialized on app start

---

## Phase 2: Reliability

### 2.1 Local Queue (Android)

- [x] **(Android) Create ReadingQueue.kt**
  - SQLiteOpenHelper subclass for database management
  - Table: `queued_readings(id, spo2, heart_rate, battery, timestamp, created_at)`
  - `enqueue(reading: OxiReading): Long` - add reading, returns row ID
  - `peek(limit: Int): List<QueuedReading>` - get oldest readings
  - `remove(ids: List<Long>): Int` - remove by IDs
  - `remove(id: Long): Boolean` - remove single reading
  - `count(): Int` - queue size
  - `isEmpty(): Boolean` - check if empty
  - `clear(): Int` - remove all readings
  - `pruneExpired(): Int` - remove readings older than 24 hours
  - `getStats(): QueueStats` - queue statistics
  - Max queue size: 10,000 readings (auto-prunes oldest)
  - Data classes: `QueuedReading`, `QueueStats`

- [x] **(Android) Create database schema**
  - Database name: "o2relay.db"
  - Version: 1
  - SQLite table with proper indexes
  - Database closed properly in service onDestroy

- [x] **(Android) QUEUING state implementation**
  - On Pi unreachable in CONNECTED state → transition to QUEUING
  - Queue readings locally via `readingQueue.enqueue()`
  - Retry Pi connection every 10 seconds
  - On Pi reachable → flush queue via batch upload, transition to CONNECTED
  - Status updates to UI with queue size

### 2.2 Batch Upload (Pi + Android)

- [ ] **(Pi) POST /api/relay/batch endpoint**
  - Accepts: `{ "readings": [...] }`
  - Insert all readings with correct timestamps
  - Reject readings older than 24 hours
  - Return: `{ "status": "ok", "accepted": N, "rejected": M }`

- [x] **(Android) Implement postBatch()**
  - POST `/api/relay/batch` (implemented in Phase 1.4)
  - Send up to 100 readings at a time
  - Returns `BatchResponse?` with accepted/rejected counts
  - 3 unit tests in ApiClientTest.kt

- [x] **(Android) Queue flush logic**
  - `flushQueue()` method in RelayService
  - Prunes expired readings before upload
  - Processes in batches of 100
  - Removes successfully sent readings from queue
  - Tracks totalSent/totalFailed statistics
  - Called when transitioning QUEUING → CONNECTED

### 2.3 Auto-Reconnect (Android)

- [x] **(Android) BLE reconnect logic**
  - On disconnect in CONNECTED/QUEUING state, increment reconnect attempts
  - Exponential backoff: 5s, 10s, 20s, 30s (RECONNECT_BACKOFF_MS array)
  - Max 4 attempts before checking Pi status
  - If Pi still needs relay, continue trying with max backoff
  - If Pi has readings, go DORMANT
  - `scheduleReconnect()` - posts delayed runnable with backoff
  - `resetReconnectTracking()` - called on successful BLE connection
  - Status updates show "Reconnecting in Xs..."

- [x] **(Android) Network error tracking**
  - `consecutiveNetworkFailures` counter tracks failed Pi posts
  - Reset to 0 on successful post
  - Logged for debugging ("consecutive failures: N")
  - Immediate transition to QUEUING on first failure (queue locally ASAP)
  - Queue flush when Pi becomes reachable again

### 2.4 Boot Receiver (Android)

- [x] **(Android) Create BootReceiver.kt**
  - Extends `BroadcastReceiver`
  - Listens for `BOOT_COMPLETED` intent
  - Checks `autoStartOnBoot` setting (must be true)
  - Checks `serviceEnabled` setting (service was running before reboot)
  - Checks BLE permissions before starting
  - Starts RelayService via `ContextCompat.startForegroundService()`
  - Comprehensive logging for debugging boot issues

- [x] **(Android) Add to manifest**
  - Receiver declaration with `exported="false"`
  - Intent filter for `android.intent.action.BOOT_COMPLETED`
  - `RECEIVE_BOOT_COMPLETED` permission (was already in manifest)

- [x] **(Android) Service auto-start setting**
  - `autoStartOnBoot: Boolean` in SettingsManager (added in Phase 1.7)
  - `serviceEnabled: Boolean` tracks if service was running
  - Default: true
  - UI toggle in settings (Phase 3)

### 2.5 API Authentication (Android)

- [x] **(Android) Add auth token storage to SettingsManager**
  - `authToken: String?` - API bearer token
  - `authTokenExpires: String?` - ISO timestamp of token expiration
  - `authUsername: String?` - logged-in username
  - `hasValidToken(): Boolean` - checks token exists and not expired
  - `saveAuth(token, expiresAt, username)` - save after successful login
  - `clearAuth()` - logout, clear all auth data

- [x] **(Android) Add login method to ApiClient**
  - POST `/api/login` with username, password, device_name
  - `LoginRequest` data class with @SerializedName annotations
  - `LoginResponse` data class (success, token, expiresAt, error)
  - Auto-sets `authToken` property on successful login
  - Returns `LoginResponse?` (null on network error)

- [x] **(Android) Add Bearer token to API requests**
  - `addAuthHeader()` extension function on Request.Builder
  - Adds `Authorization: Bearer <token>` header if token is set
  - Applied to: `getRelayStatus()`, `postReading()`, `postBatch()`, `getAppVersion()`

- [x] **(Android) Update MainActivity for login flow**
  - Check `hasValidToken()` before starting service
  - Show login dialog if no valid token
  - `dialog_login.xml` layout with username/password fields
  - `performLogin()` coroutine calls `apiClient.login()`
  - Saves token to SettingsManager on success
  - Auth status display in footer (clickable)
  - Long-press to logout with confirmation

- [x] **(Android) Update RelayService to load auth token**
  - Load token from SettingsManager in `onCreate()`
  - Set `apiClient.authToken` if valid token exists
  - Log warning if no valid token (API calls may fail)

### 2.6 Test Mode (Android)

- [x] **(Android) Add test mode to SettingsManager**
  - `testMode: Boolean` - when true, uses test server URL
  - `TEST_SERVER_URL = "http://10.0.2.2:5000"` (host localhost from Android emulator)
  - `getEffectiveServerUrl()` - returns test or production URL

- [x] **(Android) Test mode toggle in MainActivity**
  - Long-press on server URL to toggle test mode
  - Toast notification shows new mode and URL
  - Service restart required to apply change

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

- [x] **(Android) CRC calculation tests**
  - Test vectors verified against implementation
  - Edge cases (0x00, 0x01, 0xFF, multi-byte sequences)

- [x] **(Android) Packet parsing tests**
  - Valid reading packet
  - Sensor off packet (flag 0xFF)
  - Idle packet (zeros)
  - Incomplete packet
  - Multiple packets in buffer (findPacket)
  - Invalid header detection
  - Too short packet handling

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
Phase 0 (Dev Environment) ──> All Android tasks

Phase 0 Complete ─┬─> Phase 1.1 (Pi API) ──────────┐
                  │                                 │
                  └─> Phase 1.2 (Project Setup) ───┤
                                                   ├──> Phase 1.5 (Service) ──> Phase 1.6 (UI)
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
| Phase 0 | 1-2 hours | Download/install time, longer on slow internet |
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
