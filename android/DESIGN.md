# O2 Relay Android App - Design Document

## Overview

Android app that acts as a **backup relay** for the O2Monitor system. The Raspberry Pi is the primary BLE reader. When dad moves out of BLE range of the Pi (living room, out of house), the phone detects this and takes over reading the oximeter, relaying data to the Pi over WiFi or WireGuard VPN.

### Architecture

```
                    PRIMARY PATH (Dad near Pi)
[Checkme O2 Max] ----BLE----> [Raspberry Pi] ----> [Database/Alerts]

                    BACKUP PATH (Dad away from Pi)
[Checkme O2 Max] ----BLE----> [Android Phone] --WiFi/WG--> [Pi] ----> [Database/Alerts]
```

### Design Philosophy

- **Pi is Primary**: Always plugged in, no battery concerns, already integrated
- **Phone is Backup**: Only activates when Pi can't reach oximeter
- **Minimal Phone Battery Impact**: Phone stays dormant when not needed
- **Graceful Handoff**: Clear coordination to avoid BLE contention

---

## State Machines

### Phone States

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    v                                     │
┌─────────┐    Pi needs help    ┌──────────┐    Lost BLE │
│ DORMANT │ ─────────────────> │ SCANNING │ ────────────┘
│         │ <───────────────── │          │
└─────────┘   Pi has readings  └──────────┘
     ^                              │
     │                              │ Found device
     │                              v
     │         Lost BLE       ┌───────────┐    Pi unreachable    ┌──────────┐
     └─────────────────────── │ CONNECTED │ ──────────────────> │ QUEUING  │
          (Pi has readings)   │ (Relaying)│ <────────────────── │          │
                              └───────────┘    Pi reachable     └──────────┘
```

| State | Description | Actions |
|-------|-------------|---------|
| **DORMANT** | Pi handling readings, phone idle | Check in every 60s via `/api/relay/status` |
| **SCANNING** | Looking for oximeter | BLE scan with 30s timeout |
| **CONNECTED** | Reading oximeter, relaying to Pi | Read every 5s, POST to Pi |
| **QUEUING** | Can't reach Pi, storing locally | Queue readings, retry Pi every 10s |

### Pi States (for context)

| State | Description |
|-------|-------------|
| **DIRECT_BLE** | Reading directly from oximeter |
| **RELAY** | Receiving readings from phone |
| **DISCONNECTED** | No readings from either source |

---

## API Endpoints (Pi-side)

### GET /api/relay/status

Phone calls this every 60s when dormant to check if Pi needs help.

**Response:**
```json
{
  "timestamp": "2024-01-15T10:30:00",
  "last_reading_age_seconds": 5,
  "source": "ble_direct",
  "needs_relay": false,
  "pi_ble_connected": true
}
```

**Logic:**
- `needs_relay = true` when `last_reading_age_seconds > 30`
- Phone transitions DORMANT → SCANNING when `needs_relay = true`

### POST /api/relay/reading

Phone posts individual readings while relaying.

**Request:**
```json
{
  "spo2": 97,
  "heart_rate": 72,
  "battery": 85,
  "timestamp": "2024-01-15T10:30:00",
  "device_id": "dads_pixel",
  "queued": false
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Reading received"
}
```

**Pi Behavior:**
- On receiving relay data, Pi stops its own BLE attempts
- Stores reading with `source = "android_relay"`
- Resets disconnect timer

### POST /api/relay/batch

Phone flushes queued readings when Pi becomes reachable.

**Request:**
```json
{
  "readings": [
    {
      "spo2": 97,
      "heart_rate": 72,
      "battery": 85,
      "timestamp": "2024-01-15T10:30:00",
      "device_id": "dads_pixel"
    },
    ...
  ]
}
```

**Response:**
```json
{
  "status": "ok",
  "accepted": 15,
  "rejected": 0
}
```

**Pi Behavior:**
- Insert readings with correct timestamps (may be backdated)
- Reject readings older than 24 hours

### GET /api/relay/app-version

Phone checks for updates on startup and daily.

**Response:**
```json
{
  "version": "1.2.0",
  "version_code": 3,
  "apk_url": "/static/app/o2relay-1.2.0.apk",
  "release_notes": "Bug fixes and battery improvements",
  "min_version_code": 1
}
```

---

## BLE Protocol

### Device Identification

- **Device Name**: "O2M 2781" (or similar O2M prefix)
- **MAC Address**: C8:F1:6B:56:7B:F1 (from config.yaml)

### Service/Characteristic UUIDs

| UUID | Purpose |
|------|---------|
| `0734594a-a8e7-4b1a-a6b1-cd5243059a57` | RX - Receive notifications |
| `8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3` | TX - Send commands |

### Command Protocol

**Request Reading (Command 0x17):**
```
Byte 0: 0xAA (header)
Byte 1: 0x17 (command)
Byte 2: 0xE8 (0xFF ^ 0x17)
Byte 3-6: 0x00 (padding)
Byte 7: CRC
```

**CRC Calculation:**
```kotlin
fun calcCrc(data: ByteArray): Byte {
    var crc = 0x00
    for (b in data) {
        var chk = (crc xor b.toInt()) and 0xFF
        crc = 0x00
        if (chk and 0x01 != 0) crc = crc xor 0x07
        if (chk and 0x02 != 0) crc = crc xor 0x0e
        if (chk and 0x04 != 0) crc = crc xor 0x1c
        if (chk and 0x08 != 0) crc = crc xor 0x38
        if (chk and 0x10 != 0) crc = crc xor 0x70
        if (chk and 0x20 != 0) crc = crc xor 0xe0
        if (chk and 0x40 != 0) crc = crc xor 0xc7
        if (chk and 0x80 != 0) crc = crc xor 0x89
    }
    return crc.toByte()
}
```

### Response Parsing

**Packet Structure:**
```
Byte 0: 0x55 (header)
Byte 1-4: metadata
Byte 5-6: payload length (little endian)
Byte 7+: payload
```

**Sensor Reading Payload (13 bytes):**
```
Byte 0: SpO2 (0-100)
Byte 1: Heart Rate (BPM)
Byte 2: Flag (0xFF = sensor off, 0x00 with zeros = idle)
Byte 7: Battery (0-100)
Byte 9: Movement indicator
```

**Validity Check:**
- Skip if `flag == 0xFF` (sensor not on finger)
- Skip if `flag == 0x00 && spo2 == 0 && hr == 0` (sensor idle)

---

## Android Implementation

### Project Structure

```
android/
├── app/
│   ├── src/main/
│   │   ├── java/com/o2monitor/relay/
│   │   │   ├── MainActivity.kt           # Main UI
│   │   │   ├── RelayService.kt           # Foreground service (state machine)
│   │   │   ├── BleManager.kt             # BLE scanning/connection
│   │   │   ├── OximeterProtocol.kt       # Packet parsing, CRC
│   │   │   ├── ApiClient.kt              # HTTP to Pi
│   │   │   ├── ReadingQueue.kt           # Local SQLite queue
│   │   │   ├── SettingsManager.kt        # SharedPreferences
│   │   │   └── UpdateChecker.kt          # APK updates
│   │   ├── res/
│   │   │   ├── layout/
│   │   │   │   ├── activity_main.xml
│   │   │   │   └── notification_relay.xml
│   │   │   ├── values/
│   │   │   │   ├── strings.xml
│   │   │   │   └── colors.xml
│   │   │   └── drawable/
│   │   └── AndroidManifest.xml
│   └── build.gradle.kts
├── build.gradle.kts
├── settings.gradle.kts
└── gradle.properties
```

### Key Classes

#### RelayService.kt (Foreground Service)

```kotlin
class RelayService : Service() {
    enum class State { DORMANT, SCANNING, CONNECTED, QUEUING }

    private var state = State.DORMANT
    private val checkInInterval = 60_000L  // 60 seconds

    // State transitions
    fun onPiStatusReceived(status: RelayStatus) {
        when (state) {
            State.DORMANT -> {
                if (status.needsRelay) {
                    transitionTo(State.SCANNING)
                }
            }
            State.CONNECTED -> {
                // Keep relaying even if Pi says it doesn't need help
                // Phone decides when to stop (on BLE disconnect)
            }
            // ...
        }
    }

    fun onBleConnected() {
        transitionTo(State.CONNECTED)
    }

    fun onBleDisconnected() {
        // Check if Pi has readings before going dormant
        checkPiStatus { status ->
            if (status.lastReadingAgeSeconds < 30) {
                transitionTo(State.DORMANT)
            } else {
                transitionTo(State.SCANNING)  // Try to reconnect
            }
        }
    }

    fun onPiUnreachable() {
        if (state == State.CONNECTED) {
            transitionTo(State.QUEUING)
        }
    }
}
```

#### BleManager.kt

```kotlin
class BleManager(private val context: Context) {
    private val TARGET_MAC = "C8:F1:6B:56:7B:F1"
    private val RX_UUID = UUID.fromString("0734594a-a8e7-4b1a-a6b1-cd5243059a57")
    private val TX_UUID = UUID.fromString("8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3")

    interface Callback {
        fun onConnected()
        fun onDisconnected()
        fun onReading(spo2: Int, heartRate: Int, battery: Int)
        fun onError(message: String)
    }

    fun startScan(timeout: Long = 30_000L)
    fun connect(device: BluetoothDevice)
    fun disconnect()
    fun requestReading()  // Send 0x17 command
}
```

#### ApiClient.kt

```kotlin
class ApiClient(private val baseUrl: String) {
    suspend fun getRelayStatus(): RelayStatus
    suspend fun postReading(reading: OxiReading): Boolean
    suspend fun postBatch(readings: List<OxiReading>): BatchResult
    suspend fun getAppVersion(): AppVersion
}

data class RelayStatus(
    val timestamp: String,
    val lastReadingAgeSeconds: Int,
    val source: String,
    val needsRelay: Boolean,
    val piBleConnected: Boolean
)
```

#### ReadingQueue.kt

```kotlin
class ReadingQueue(context: Context) {
    // SQLite-backed queue for offline readings

    fun enqueue(reading: OxiReading)
    fun peek(limit: Int = 100): List<OxiReading>
    fun remove(ids: List<Long>)
    fun count(): Int
    fun clear()
}
```

### Permissions

```xml
<manifest>
    <!-- Bluetooth -->
    <uses-permission android:name="android.permission.BLUETOOTH" />
    <uses-permission android:name="android.permission.BLUETOOTH_ADMIN" />
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" />

    <!-- Android 12+ requires FINE_LOCATION for BLE scanning -->
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />

    <!-- Foreground service -->
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE" />
    <uses-permission android:name="android.permission.WAKE_LOCK" />

    <!-- Network -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

    <!-- Auto-start on boot -->
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />

    <!-- Install APK updates -->
    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />
</manifest>
```

### Foreground Service Notification

Required for Android 8+ to keep service alive.

```
┌────────────────────────────────────────┐
│ O2 Relay                          [·]  │
│ Status: Dormant - Pi is reading        │
│ Last check: 30s ago                    │
└────────────────────────────────────────┘
```

When active:
```
┌────────────────────────────────────────┐
│ O2 Relay                          [·]  │
│ Active: SpO2 97% HR 72 bpm             │
│ Relaying to Pi                         │
└────────────────────────────────────────┘
```

---

## UI Design

### Main Screen

```
┌─────────────────────────────────────┐
│  O2 Relay                      [≡]  │
├─────────────────────────────────────┤
│                                     │
│  ┌─────────────────────────────┐    │
│  │     Status: DORMANT         │    │
│  │     Pi is reading directly  │    │
│  └─────────────────────────────┘    │
│                                     │
│  Last check-in: 45 seconds ago      │
│  Pi last reading: 3 seconds ago     │
│                                     │
│  ┌─────────────────────────────┐    │
│  │      [ Start Service ]      │    │
│  └─────────────────────────────┘    │
│                                     │
├─────────────────────────────────────┤
│  Server: 192.168.4.100              │
│  Device: C8:F1:6B:56:7B:F1          │
│  Version: 1.0.0                     │
└─────────────────────────────────────┘
```

### When Active

```
┌─────────────────────────────────────┐
│  O2 Relay                      [≡]  │
├─────────────────────────────────────┤
│                                     │
│  ┌─────────────────────────────┐    │
│  │     Status: CONNECTED       │    │
│  │     Relaying to Pi          │    │
│  └─────────────────────────────┘    │
│                                     │
│  ┌───────────┬───────────┐          │
│  │  SpO2     │  Heart    │          │
│  │   97%     │   72 bpm  │          │
│  └───────────┴───────────┘          │
│                                     │
│  Battery: 85%                       │
│  Readings sent: 142                 │
│  Queued: 0                          │
│                                     │
│  ┌─────────────────────────────┐    │
│  │      [ Stop Service ]       │    │
│  └─────────────────────────────┘    │
│                                     │
├─────────────────────────────────────┤
│  Server: 192.168.4.100 ✓            │
└─────────────────────────────────────┘
```

### Settings Screen

```
┌─────────────────────────────────────┐
│  ← Settings                         │
├─────────────────────────────────────┤
│                                     │
│  Server URL                         │
│  ┌─────────────────────────────┐    │
│  │ http://192.168.4.100:5000   │    │
│  └─────────────────────────────┘    │
│                                     │
│  Oximeter MAC Address               │
│  ┌─────────────────────────────┐    │
│  │ C8:F1:6B:56:7B:F1           │    │
│  └─────────────────────────────┘    │
│                                     │
│  Check-in Interval                  │
│  ○ 30 seconds                       │
│  ● 60 seconds                       │
│  ○ 120 seconds                      │
│                                     │
│  ─────────────────────────────────  │
│                                     │
│  [ Check for Updates ]              │
│                                     │
│  App Version: 1.0.0 (build 1)       │
│                                     │
└─────────────────────────────────────┘
```

---

## Coordination Logic

### When Phone Takes Over

1. Phone checks in, sees `needs_relay = true`
2. Phone starts BLE scanning
3. Phone connects to oximeter (this kicks Pi off BLE if Pi was trying)
4. Phone starts relaying readings
5. Pi receives relay data, stops BLE attempts, enters RELAY state

### When Phone Stops

1. Phone loses BLE connection (oximeter out of range, turned off, etc.)
2. Phone checks Pi status
3. If Pi has recent readings (< 30s): Phone goes DORMANT
4. If Pi doesn't have readings: Phone goes back to SCANNING

### Avoiding BLE Contention

- BLE is single-connection - only one device can connect at a time
- When phone connects, Pi is automatically blocked
- When phone disconnects, Pi can reconnect
- No explicit coordination needed - just check-in status

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| Phone app killed by Android | Pi notices no relay data, resumes BLE attempts |
| Phone reboots | Service restarts, checks in, stays dormant if Pi is reading |
| Pi reboots | Phone gets errors, queues locally, resumes relay when Pi returns |
| WiFi goes down | Phone queues locally, flushes when WiFi returns |
| Dad leaves phone at home | Phone loses BLE, goes dormant. Pi takes over if in range. |
| Dad takes phone, leaves house | Phone relays over WireGuard VPN |
| Both lose oximeter | Both retry with backoff. Alert triggers after threshold. |

---

## Battery Optimization

### Strategy

1. **DORMANT state is cheap**: Just one HTTP GET every 60 seconds
2. **BLE scanning is moderate**: Only when actively looking (has timeout)
3. **BLE connected is cheap**: Low-power notifications
4. **Foreground service required**: Keeps app alive but uses notification

### Android Battery Optimization

Request user to disable battery optimization for reliable operation:

```kotlin
if (!isIgnoringBatteryOptimizations()) {
    val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
    intent.data = Uri.parse("package:$packageName")
    startActivity(intent)
}
```

### Estimated Battery Impact

| State | Estimated Daily Drain |
|-------|----------------------|
| DORMANT (WiFi) | ~3-5% |
| CONNECTED (WiFi) | ~5-10% |
| CONNECTED (LTE/WireGuard) | ~10-20% |

Dad is religious about charging, so this is acceptable.

---

## Auto-Update Mechanism

### Version Check Flow

1. App starts → Check `/api/relay/app-version`
2. If newer version available:
   - Show notification: "Update available: v1.2.0"
   - User taps → Download APK from `/static/app/o2relay-X.X.X.apk`
   - Android prompts to install (requires "Unknown sources" permission)

### Hosting APK on Pi

```
src/web/static/app/
├── o2relay-1.0.0.apk
├── o2relay-1.1.0.apk
└── o2relay-latest.apk -> o2relay-1.1.0.apk
```

### Version Metadata

Store in `src/web/static/app/version.json`:
```json
{
  "version": "1.1.0",
  "version_code": 2,
  "release_notes": "Added queue persistence",
  "min_version_code": 1,
  "apk_filename": "o2relay-1.1.0.apk"
}
```

---

## Security

### Authentication

- Phone uses Bearer token authentication (30-day validity)
- User logs in via in-app dialog (username/password)
- POST `/api/login` returns token and expiration timestamp
- Token stored in SharedPreferences (`authToken`, `authTokenExpires`, `authUsername`)
- All API requests include `Authorization: Bearer <token>` header
- Token checked on service start - login dialog shown if expired
- Logout clears stored token

**Login Flow:**
1. User taps "Start Service" button
2. If no valid token, login dialog is shown
3. User enters credentials (same as web UI)
4. App calls POST `/api/login` with username, password, device_name
5. On success, token saved and service starts
6. Token reused for 30 days until expiration

### Network Security

- **Home WiFi**: Direct connection to Pi (trusted network)
- **LTE**: WireGuard VPN (encrypted tunnel)
- No need for HTTPS on local network (WireGuard handles encryption)

### Data Privacy

- No data leaves local network (unless on WireGuard, still point-to-point)
- Phone only stores queued readings temporarily
- No analytics, no cloud services

---

## Testing Plan

### Unit Tests

- [ ] CRC calculation matches Python implementation
- [ ] Packet parsing handles all edge cases
- [ ] State machine transitions correctly
- [ ] Queue persists across app restarts

### Integration Tests

- [ ] Connect to real oximeter
- [ ] Post readings to Pi
- [ ] Queue and flush workflow

### Manual Test Scenarios

| Test | Steps | Expected |
|------|-------|----------|
| Normal dormant | Start app, Pi connected to oximeter | App shows DORMANT, checks in every 60s |
| Takeover | Move oximeter away from Pi | App detects needs_relay, scans, connects, relays |
| Return to Pi | Move oximeter back near Pi, disconnect phone BLE | App checks Pi status, goes DORMANT |
| WiFi loss | Disable WiFi while relaying | App queues locally, shows QUEUING |
| WiFi restore | Re-enable WiFi | App flushes queue, continues relaying |
| App killed | Force stop app while relaying | Pi takes over (no relay data) |
| Phone reboot | Reboot phone while relaying | App restarts, checks in, appropriate state |
| LTE relay | Leave house with phone and oximeter | App relays over WireGuard |

---

## Implementation Phases

### Phase 1: Core Relay (MVP)

**Pi-side:**
- [ ] `/api/relay/status` endpoint
- [ ] `/api/relay/reading` endpoint
- [ ] Track reading source in database
- [ ] Pi backs off BLE when receiving relay data

**Android:**
- [ ] Basic UI (status, start/stop)
- [ ] Foreground service
- [ ] BLE connection to oximeter
- [ ] POST readings to Pi
- [ ] State machine (DORMANT, SCANNING, CONNECTED)

### Phase 2: Reliability

**Android:**
- [ ] Local queue (SQLite)
- [ ] Batch upload
- [ ] QUEUING state
- [ ] Auto-reconnect on BLE drop
- [ ] Boot receiver (start on boot)

**Pi-side:**
- [ ] `/api/relay/batch` endpoint
- [ ] Handle backdated readings

### Phase 3: Polish

**Android:**
- [ ] Settings screen
- [ ] Better UI with stats
- [ ] Permission handling flow
- [ ] Error reporting

**Pi-side:**
- [ ] Show relay status on dashboard
- [ ] `/api/relay/app-version` endpoint

### Phase 4: Auto-Update

**Android:**
- [ ] Version check
- [ ] APK download
- [ ] Install prompt

**Pi-side:**
- [ ] Host APK files
- [ ] Version metadata endpoint

---

## Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| Who is primary? | **Pi is primary**. Phone is backup. |
| Queue on phone? | **Yes**. SQLite-backed queue for WiFi outages. |
| Battery impact? | **Acceptable**. Dad charges religiously. |
| LTE support? | **Yes, via WireGuard**. Dad's phone already can be added. |
| Auth mechanism? | **Bearer token** (30-day validity). Login dialog prompts for credentials on first run or token expiration. |
| When does phone stop relaying? | **On BLE disconnect only**. Phone decides, not Pi. |

---

## References

- Pi BLE implementation: `src/ble_reader.py`
- Pi API patterns: `src/web/api.py`
- Config: `config.yaml`
- Original draft: `android/DESIGN_DRAFT.md`

---

## Implementation Notes (Updated 2026-01-17)

### Actual SDK Versions Used

| Component | Planned | Actual | Notes |
|-----------|---------|--------|-------|
| Target SDK | 34 (Android 14) | 36 (Android 16) | Newer SDK available at setup time |
| Min SDK | 26 (Android 8.0) | 26 (Android 8.0) | As planned |
| Kotlin | - | 2.1.0 | Latest stable |
| AGP | - | 8.9.1 | Required for compileSdk=36 support |
| Gradle | - | 8.11.1 | Latest stable |

### Project Location

```
android/O2Relay/
├── app/
│   ├── src/main/
│   │   ├── java/com/o2monitor/relay/
│   │   │   ├── MainActivity.kt           # Basic UI - implemented
│   │   │   ├── O2RelayApplication.kt     # Application class - implemented
│   │   │   ├── OximeterProtocol.kt       # BLE protocol - implemented
│   │   │   ├── BleManager.kt             # BLE scanning/connection - implemented
│   │   │   ├── BlePermissions.kt         # Permission helper - implemented
│   │   │   ├── ApiClient.kt              # HTTP client - implemented
│   │   │   ├── RelayService.kt           # Foreground service - implemented
│   │   │   └── BootReceiver.kt           # Stub - Phase 2.4
│   │   ├── res/
│   │   │   ├── layout/activity_main.xml
│   │   │   ├── values/strings.xml
│   │   │   ├── values/colors.xml
│   │   │   └── values/themes.xml
│   │   └── AndroidManifest.xml
│   ├── src/test/
│   │   └── java/
│   │       ├── android/util/Log.kt           # Mock Log for tests
│   │       └── com/o2monitor/relay/
│   │           ├── OximeterProtocolTest.kt   # 14 tests
│   │           └── ApiClientTest.kt          # 15 tests
│   └── build.gradle.kts
├── gradle/
│   ├── wrapper/
│   └── libs.versions.toml           # Version catalog
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
├── local.properties                 # Not in git - SDK path
└── .gitignore
```

### Build Commands

```bash
# Set JAVA_HOME to Android Studio's bundled JDK
export JAVA_HOME="C:/Program Files/Android/Android Studio/jbr"

# Build debug APK
cd android/O2Relay
./gradlew.bat assembleDebug

# Install on connected device/emulator
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Launch app
adb shell am start -n com.o2monitor.relay/.MainActivity
```

### Development Environment

- **Android Studio**: 2025.2.3.9 (Otter)
- **SDK Location**: `C:\Users\dmatt\AppData\Local\Android\Sdk`
- **Emulator**: Medium Phone API 36.1 (x86_64, Google Play)
- **ADB**: 36.0.2

### OximeterProtocol Implementation (2026-01-17)

**Files Created:**
- `OximeterProtocol.kt` - Protocol implementation
- `OximeterProtocolTest.kt` - 14 unit tests (all passing)
- `O2RelayApplication.kt` - Application class with notification channels

**CRC Test Vectors:**
The CRC algorithm produces the following values (verified by running implementation):
| Input | CRC |
|-------|-----|
| `[0x00]` | `0x00` |
| `[0x01]` | `0x07` |
| `[0xFF]` | `0xF3` |
| `[0x55, 0x17]` | `0x28` |
| `[0xAA, 0x17, 0xE8, 0x00, 0x00, 0x00, 0x00]` (command) | `0x1B` |

**Packet Parsing Notes:**
- Minimum 7 bytes needed to read header + payload length
- If packet has valid header but incomplete data, returns `ParseResult.Incomplete`
- CRC verification covers all bytes except the final CRC byte
- Response header is `0x55` (vs command header `0xAA`)

**Run Tests:**
```bash
cd android/O2Relay
JAVA_HOME="C:/Program Files/Android/Android Studio/jbr" ./gradlew testDebugUnitTest
```

### BleManager Implementation (2026-01-17)

**Files Created:**
- `BleManager.kt` - BLE scanning, connection, GATT operations
- `BlePermissions.kt` - Permission checking/requesting helper

**BleManager Features:**
- State machine: IDLE → SCANNING → CONNECTING → DISCOVERING_SERVICES → ENABLING_NOTIFICATIONS → CONNECTED
- Scan with MAC address filter (falls back to name prefix if MAC invalid)
- Connection with 10-second timeout
- Automatic service discovery and notification setup
- Data buffering for fragmented BLE packets
- Uses OximeterProtocol for packet parsing
- Handles Android API level differences (API 33+ methods)

**BlePermissions Features:**
- Version-aware: Android 12+ uses BLUETOOTH_SCAN/CONNECT, older uses ACCESS_FINE_LOCATION
- Permission rationale text for user explanation
- Request code constant for result handling

**Testing Notes:**
- BLE code compiles successfully
- Unit tests still pass (14/14)
- Actual BLE testing requires physical device (emulator doesn't support BLE)
- GATT error 133 retry logic will be implemented in RelayService

**Known Limitations:**
- No reconnection retry logic yet (will be in RelayService)
- No MTU negotiation (uses default, should work for oximeter packets)
- Scan uses SCAN_MODE_BALANCED; may need LOW_LATENCY for faster discovery

### ApiClient Implementation (2026-01-17)

**Files Created:**
- `ApiClient.kt` - HTTP client with all API methods and data classes
- `ApiClientTest.kt` - 15 unit tests using MockWebServer
- `android/util/Log.kt` - Mock Log class for unit tests

**ApiClient Features:**
- OkHttp with configurable timeouts (connect: 10s, read/write: 30s)
- Coroutine-based suspend functions running on Dispatchers.IO
- Gson for JSON serialization with @SerializedName for snake_case mapping
- Methods: `getRelayStatus()`, `postReading()`, `postBatch()`, `getAppVersion()`, `isReachable()`
- Graceful error handling - returns null/false on failures, never throws

**Data Classes:**
- `RelayStatus` - Response from GET /api/relay/status
- `ReadingRequest` - Request body for POST /api/relay/reading
- `BatchRequest/BatchResponse` - Batch upload types
- `AppVersion` - Version info for updates
- `ApiResponse` - Generic status response

**Test Dependencies Added:**
- `mockwebserver:4.12.0` - OkHttp mock server for testing
- `kotlinx-coroutines-test:1.9.0` - Coroutine test utilities

**Total Unit Tests: 29** (14 OximeterProtocol + 15 ApiClient)

### RelayService Implementation (2026-01-17)

**File Updated:**
- `RelayService.kt` - Full foreground service implementation

**State Machine:**
```
STOPPED → DORMANT → SCANNING → CONNECTED ↔ QUEUING
                  ↑___________|          |
                  |_______________________|
```

**States and Behavior:**
| State | Timer | Interval | Action |
|-------|-------|----------|--------|
| DORMANT | Check-in | 60s | GET /api/relay/status, transition to SCANNING if needsRelay |
| SCANNING | BLE scan | 30s timeout | Scan for oximeter, auto-connect on found |
| CONNECTED | Reading | 5s | Request reading, POST to Pi |
| QUEUING | Pi retry | 10s | Check Pi reachability, transition to CONNECTED when available |

**Key Features:**
- `RelayBinder` for MainActivity binding
- `StateListener` interface for UI updates (onStateChanged, onReadingReceived, onStatusUpdate, onError)
- Handler-based timers for all intervals
- Coroutine scope for async API calls
- Foreground notification with dynamic content
- Proper state exit/enter cleanup
- BLE disconnect handling (checks Pi status before deciding next state)

**Notification Content by State:**
- DORMANT: "Pi is reading directly"
- SCANNING: "Looking for oximeter..."
- CONNECTED: "SpO2: X% HR: Y bpm" (or "Waiting for reading...")
- QUEUING: "SpO2: X% (Pi offline)" (or "Pi offline - storing locally")

**Default Settings (hardcoded for MVP):**
- Server URL: http://192.168.4.100:5000
- Oximeter MAC: C8:F1:6B:56:7B:F1
- Device ID: android_relay

**TODO for Phase 2:**
- Local queue for readings when Pi unreachable (currently just counts)
- Queue flush on Pi reconnect
