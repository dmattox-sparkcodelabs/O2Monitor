# O2 Monitoring System Design Document

> **DISCLAIMER: NOT FOR MEDICAL USE**
>
> This project is a proof of concept and educational exercise only. It is NOT a certified medical device and should NOT be relied upon for medical monitoring, diagnosis, or treatment decisions. This system has not been validated, tested, or approved for clinical use. Do not use this system as a substitute for professional medical care or FDA-approved monitoring equipment. The authors assume no liability for any use of this software.

---

## Life-Safety Monitoring for OHS Patient (Proof of Concept)

**Version:** 1.4
**Date:** 2026-01-14
**Status:** Implementation Complete (multi-adapter failover and enhanced alerting)

---

## 1. Executive Summary

This document describes the design of a life-safety monitoring system for a patient with Obesity Hypoventilation Syndrome (OHS). The patient has experienced two near-death respiratory events in three weeks. While compliant with AVAPS (BiPAP) therapy at night, the patient tends to fall asleep in a recliner during the day without the device. Due to blunted CO2 response, the patient will not wake naturally when oxygen saturation drops.

**Primary Goal:** Detect dangerous SpO2 drops when AVAPS therapy is not active and trigger immediate local and remote alerts.

---

## 2. System Architecture

### 2.1 High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           MONITORING LAYER                               │
├─────────────────────┬───────────────────────┬───────────────────────────┤
│   Checkme O2 Max    │    Kasa KP115         │     Raspberry Pi 4        │
│   (Wrist Oximeter)  │    (Smart Plug)       │     (Central Hub)         │
│        BLE ─────────┼──► WiFi ──────────────┼──►  State Machine         │
│   SpO2, HR, Battery │    AVAPS Power Draw   │      + Web Server         │
└─────────────────────┴───────────────────────┴───────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            ALERTING LAYER                                │
├─────────────────────┬───────────────────────┬───────────────────────────┤
│   Local Alert       │    Remote Alert       │     Dead-Man Switch       │
│   (Pi Speakers)     │    (PagerDuty)        │     (Healthchecks.io)     │
│   Loud audio alarm  │    Phone notifications│     60-sec heartbeat      │
└─────────────────────┴───────────────────────┴───────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PERSISTENCE LAYER                               │
│                     SQLite Database (history.db)                         │
│              SpO2/HR readings, alerts, system events                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Hardware Components

| Component | Model | Purpose | Connection |
|-----------|-------|---------|------------|
| Central Hub | Raspberry Pi 4 (4GB) | Run monitoring software | Ethernet/WiFi |
| Pulse Oximeter | Wellue Checkme O2 Max | SpO2 + HR readings | Bluetooth LE |
| BT Adapter (Primary) | Insignia USB Bluetooth | BLE connection - Hallway | USB (on extension) |
| BT Adapter (Backup) | Insignia USB Bluetooth | BLE connection - Bedroom | USB (direct) |
| Power Monitor | TP-Link Kasa KP115 | AVAPS on/off detection | WiFi (LAN) |
| Local Alert | Powered PC Speakers | Audible alarms | Pi 3.5mm audio jack |
| Remote Announce | Amazon Echo devices (optional) | Multi-room alerts | WiFi (Alexa API) |
| UPS | EcoFlow Delta 2 | Power backup | AC passthrough |

**Bluetooth Adapter Notes:**
- The Raspberry Pi 4's internal Bluetooth is disabled via `dtoverlay=disable-bt` in `/boot/firmware/config.txt`
- Two external USB Bluetooth adapters provide redundancy and location flexibility
- Insignia adapters are confirmed to work with BlueZ; ASUS adapters require additional drivers
- Adapters are named "Hallway" and "Bedroom" for dashboard display

### 2.3 Software Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| OS | Raspbian (Debian-based) | Stable Linux for Pi |
| Language | Python 3.9+ | Primary application language |
| BLE Library | BLE-GATT + pydbus | Checkme O2 Max communication (D-Bus based) |
| Event Loop | GLib (PyGObject) | Async BLE notifications |
| Smart Plug | python-kasa | Kasa KP115 power readings |
| Web Framework | Flask | Dashboard and API |
| Database | SQLite | Historical data storage |
| Auth | bcrypt + Flask-Login | Secure authentication |

**Important BLE Note:** Testing confirmed that common Python BLE libraries (bleak, bluepy, pygatt) fail to connect to the Checkme O2 Max due to its use of BLE Random Address type. The BLE-GATT library (which uses pydbus for D-Bus communication with BlueZ) is the only tested solution that works reliably on Raspberry Pi. The virtual environment must be created with `--system-site-packages` to access the system PyGObject/GLib bindings.

---

## 3. Component Design

### 3.1 BLE Reader (`ble_reader.py`)

**Purpose:** Maintain persistent BLE connection to Checkme O2 Max and stream SpO2/HR data.

**Architecture Note:** This module uses a synchronous, GLib event loop approach (not async/await) because the BLE-GATT library relies on the GLib main loop for BLE notification handling. The main monitoring loop runs within `ble.wait_for_notifications()`.

**BLE Characteristics (Viatom/Wellue Protocol):**
| UUID | Direction | Purpose |
|------|-----------|---------|
| `8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3` | TX (write) | Send commands to device |
| `0734594a-a8e7-4b1a-a6b1-cd5243059a57` | RX (notify) | Receive data from device |

**Responsibilities:**
- Connect to oximeter via MAC address with retry logic
- Send command 0x17 to request sensor readings on interval
- Parse incoming notification packets (Viatom protocol)
- Handle duplicate notifications (device sends multiple per request)
- Track device battery level and movement
- Detect sensor-off / idle states

**Key Classes:**
```python
class CheckmeO2Reader:
    def __init__(self, mac_address: str, read_interval: int = 10)
    def connect(self) -> bool           # Blocking with retry loop
    def request_reading(self) -> None   # Send command 0x17
    def run(self, num_readings: int = -1) -> List[OxiReading]

    # Internal methods
    def handle_notification(self, value: bytes) -> None
    def parse_reading(self, payload: bytes) -> Optional[OxiReading]
    def build_command(self, cmd: int) -> bytearray
    def calc_crc(self, data: bytes) -> int

@dataclass
class OxiReading:
    timestamp: datetime
    spo2: int              # 0-100 percentage
    heart_rate: int        # BPM
    battery_level: int     # 0-100 percentage
    movement: int          # Movement indicator
    is_valid: bool         # False if finger not detected (flag=0xFF)
```

**Connection Strategy:**
- Infinite retry loop with 2-second delay between attempts
- Device must be "trusted" in BlueZ (not "paired") - use `bluetoothctl trust <MAC>`
- Connection typically succeeds within 5-20 attempts on first run
- Subsequent connections are faster once device is trusted
- Device display does NOT need to stay on after initial connection

**Reading Interval:**
- Default: 5 seconds between readings (configurable)
- Device sends multiple notification packets per request; deduplication required
- Use 1-second minimum gap to filter duplicate notifications

### 3.1.1 Multi-Adapter Failover (AdapterManager)

The system supports multiple Bluetooth adapters for redundancy and location flexibility. The `AdapterManager` class handles automatic switching between adapters when connectivity issues occur.

**Key Classes:**
```python
@dataclass
class AdapterInfo:
    name: str                    # Human-readable name (e.g., "Hallway")
    mac_address: str             # Adapter MAC address
    hci: Optional[str] = None    # BlueZ interface (e.g., "hci0")
    is_up: bool = False          # Current interface state

class AdapterManager:
    def discover_adapters(self) -> List[AdapterInfo]
    def switch_to_next_adapter(self) -> Optional[AdapterInfo]
    def check_adapter_health(self) -> Dict[str, bool]
```

**Switching Logic:**
1. **Normal Mode**: Use the current adapter until readings stop arriving
2. **Switch Timeout**: After `switch_timeout_minutes` (default: 5) of no readings, switch to the next adapter
3. **Bounce Mode**: When switching, cycle through available adapters every `bounce_interval_minutes` (default: 1) until connection is restored
4. **Health Checks**: Every 60 seconds, run `hciconfig -a` to verify adapter availability

**Adapter States (Dashboard Display):**
| State | Color | Meaning |
|-------|-------|---------|
| Active | Green | Currently connected and receiving readings |
| Connecting | Amber (pulsing) | Attempting to connect |
| Standby | Blue | Available but intentionally down (not in use) |
| Offline | Gray | Not detected (unplugged or failed) |

**Configuration:**
```yaml
bluetooth:
  adapters:
    - name: Hallway
      mac_address: 10:A5:62:EC:E8:A5
    - name: Bedroom
      mac_address: 10:A5:62:79:03:8A
  read_interval_seconds: 5
  late_reading_seconds: 30
  switch_timeout_minutes: 5
  bounce_interval_minutes: 1
  respawn_delay_seconds: 15
  bt_restart_threshold_minutes: 5
```

### 3.1.2 BLE Connection Reliability

The Realtek RTL8761B chipset (used in ASUS BT500 adapters) requires special handling to maintain stable BLE connections on Raspberry Pi.

#### Ghost Connection Problem

When a BLE connection drops "dirty" (no disconnect packet sent), BlueZ may still believe the device is connected. This causes:
1. BlueZ filters out advertisement packets from the "connected" MAC address
2. The device appears undiscoverable even though it's still advertising
3. Only a Bluetooth service restart clears this state

**Solution - Surgical Device Removal:**
```python
def _clear_ghost_connection(self) -> bool:
    """Remove device from BlueZ cache to clear ghost connection state."""
    subprocess.run(['bluetoothctl', 'remove', self.mac_address], timeout=10)
    time.sleep(2)  # Allow BlueZ to propagate
```

This is called:
- After 3 consecutive connection failures (early intervention)
- Before any full Bluetooth service restart

#### USB Autosuspend Problem

The Realtek chipset crashes when Linux puts it into low-power mode during idle gaps, causing I/O errors and connection failures.

**Solution - Disable USB Autosuspend:**

1. **Udev Rule** (`/etc/udev/rules.d/50-bluetooth-power.rules`):
```
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="6655", ATTR{idProduct}=="8771", ATTR{power/autosuspend}="-1", ATTR{power/control}="on"
```

2. **Boot Config** (`/boot/cmdline.txt`):
```
usbcore.autosuspend=-1
```

#### Recovery Escalation

| Failures | Action | Purpose |
|----------|--------|---------|
| 1 | Wait respawn_delay (15s) | Allow transient issues to clear |
| 3 | Clear ghost connection | Surgical fix for stale BlueZ state |
| 5 min | Restart Bluetooth service | Nuclear option if surgical fix fails |

#### Connection Health Tracking

The BLE reader tracks:
- `_consecutive_failures`: Count of failed connection attempts
- `_disconnect_start_time`: When the outage began
- `_last_bt_restart_time`: Cooldown for service restarts

Recovery is logged with duration: `CONNECTION RECOVERED: 5 failures over 2m 30s outage`

### 3.2 AVAPS Monitor (`avaps_monitor.py`)

**Purpose:** Monitor AVAPS power state via smart plug power readings.

**Responsibilities:**
- Poll Kasa KP115 for real-time power consumption
- Determine AVAPS state based on power thresholds
- Debounce state transitions to avoid false triggers
- Handle network errors gracefully

**Key Classes:**
```python
class AVAPSMonitor:
    def __init__(self, plug_ip: str,
                 on_threshold_watts: float = 3.0,
                 off_threshold_watts: float = 2.0)
    async def get_power_watts(self) -> float
    async def is_avaps_on(self) -> bool

    @property
    def current_state(self) -> AVAPSState

class AVAPSState(Enum):
    ON = "on"           # Power > on_threshold
    OFF = "off"         # Power < off_threshold
    UNKNOWN = "unknown" # Network error or startup
```

**Power Thresholds:**
- AVAPS ON: > 3.0 watts (device actively running)
- AVAPS OFF: < 2.0 watts (standby or unplugged)
- Hysteresis band prevents oscillation at boundary

**Polling Interval:** 5 seconds

### 3.3 Alert System (`alerting.py`)

**Purpose:** Deliver alerts through multiple channels with appropriate urgency, with context-aware thresholds based on therapy state.

**Design Philosophy:**
- **Therapy-aware alerting**: Different thresholds when AVAPS is ON (night/therapy mode) vs OFF (day mode)
- **Configurable without code changes**: All alert types, thresholds, and behaviors defined in config.yaml
- **Multi-severity**: Maps to PagerDuty severity levels (critical, high/error, warning, info)
- **Graduated response**: Disconnect alerts escalate from info → warning → high over time

#### 3.3.1 Alert Types and Severity

| Alert Type | Severity | Description | Therapy OFF | Therapy ON |
|------------|----------|-------------|-------------|------------|
| `spo2_critical_off_therapy` | critical | Dangerously low SpO2 (no therapy) | <90% for 30s | N/A |
| `spo2_critical_on_therapy` | critical | Dangerously low SpO2 (during therapy) | N/A | <85% for 120s |
| `spo2_warning` | warning | SpO2 entering warning zone | <92% for 60s | Disabled |
| `hr_high` | high | Heart rate too high | >120 BPM for 60s | Disabled |
| `hr_low` | high | Heart rate too low | <50 BPM for 60s | Disabled |
| `disconnect` | warning | Oximeter disconnected | 120 min threshold | Disabled |
| `no_therapy_at_night_info` | info | Initial notice during sleep hours | 30 min | N/A |
| `no_therapy_at_night_high` | high | Escalated alert during sleep hours | 60 min | N/A |
| `battery_warning` | warning | Battery getting low | <25% | <25% |
| `battery_critical` | critical | Battery critically low | <10% | <10% |
| `adapter_disconnect` | warning | Bluetooth adapter unplugged | Always | Always |

**Resend Intervals:**
Each alert type has a configurable `resend_interval_seconds` that prevents the same alert from firing repeatedly. After an alert fires, it won't fire again until the resend interval has elapsed (even if the condition persists). This prevents alert fatigue while ensuring persistent conditions are re-notified periodically.

**Sleep Hours and Therapy Compliance:**

The system tracks "sleep hours" (configurable, default 10pm-7am). If AVAPS is OFF during sleep hours, alerts escalate over time to catch situations where the patient may have gone to bed without starting therapy.

| Condition | Duration | Alert Type | Severity |
|-----------|----------|------------|----------|
| Sleep hours + AVAPS OFF | 30 min | no_therapy_at_night | info |
| Sleep hours + AVAPS OFF | 60 min | no_therapy_at_night | warning |

**Rationale:**
- **30 min (info)**: Patient may still be awake or getting ready for bed
- **60 min (warning)**: More likely patient is sleeping without therapy - family should check

**Therapy Context Rationale:**
- **Therapy ON (night mode)**: Patient is using AVAPS BiPAP therapy, sensor may slip during sleep. Use more lenient SpO2 threshold (85%) with longer duration (120s) to avoid false alarms from sensor displacement. Disable HR and disconnect alerts since sensor charging is expected.
- **Therapy OFF (day mode)**: Patient may fall asleep without therapy. Strict thresholds are critical - any sustained desaturation requires immediate attention.
- **Sleep hours + no therapy**: Informational alert to notify family that patient may be sleeping without BiPAP.

#### 3.3.2 Alert Channels

**Local Alert (Pi Audio):**
- Powered PC speakers connected to Pi 3.5mm audio jack
- Programmatically generated alarm tones (no external sound files needed)
- Different tone patterns for each severity level:
  - **Critical**: Fast triple beeps at 880 Hz (high pitched, urgent)
  - **High**: Double beeps at 660 Hz
  - **Warning**: Slower single beeps at 440 Hz
  - **Info**: Low single tone at 330 Hz
- TTS announcements via espeak describe the issue:
  - "Warning! Oxygen level critical at 85 percent."
  - "Attention. Heart rate high at 130 beats per minute."
  - "Attention. Oxygen monitor disconnected."
- Critical/High alerts repeat (tones + TTS) every 30 seconds until resolved or silenced
- No internet dependency - works offline
- Can be silenced via dashboard
- Volume configurable in config.yaml

**Local Alert - Alexa (Optional):**
- Secondary/supplemental for announcements in other rooms
- Uses Alexa Routine triggers or Notify Me skill
- Not relied upon for primary alerting (requires internet)

**Remote Alert (PagerDuty):**
- Severity-based incident creation
- Notifies primary contact (son) first
- Escalates to secondary (sister) if not acknowledged
- Includes: SpO2 level, HR, duration, AVAPS state, timestamp
- Severity mapping:
  - `critical` → PagerDuty critical (phone call immediately)
  - `high` → PagerDuty error (push notification, SMS)
  - `warning` → PagerDuty warning (push notification)
  - `info` → PagerDuty info (logged, no notification by default)

#### 3.3.3 Disconnect Alert Escalation

When the oximeter disconnects during therapy OFF mode:

| Duration | Severity | Action |
|----------|----------|--------|
| 0 min | info | Log event, dashboard shows disconnected |
| 2 hours | warning | PagerDuty warning - check on device |
| 3 hours | high | PagerDuty error - urgent check needed |

During therapy ON mode, disconnect alerts are disabled since the patient is expected to be charging the sensor while using AVAPS.

**Key Classes:**
```python
# AlertManager (alerting.py) - Handles alert delivery
class AlertManager:
    def __init__(self, config: Config)
    async def trigger_alarm(self, alert: Alert) -> None
    async def trigger_local_only(self, alert: Alert) -> None
    async def resolve_alert(self, alert_id: str) -> None
    def silence(self, duration_minutes: int) -> None
    def unsilence(self) -> None

    @property
    def is_silenced(self) -> bool
    @property
    def active_alerts(self) -> List[Alert]

# AlertEvaluator (alert_evaluator.py) - Evaluates conditions and generates alerts
class AlertEvaluator:
    def __init__(self, config: AlertsConfig)
    def evaluate(self, reading: OxiReading, avaps_state: AVAPSState,
                 ble_connected: bool) -> List[Alert]
    # Internal methods for each alert type:
    # _evaluate_spo2(), _evaluate_hr(), _evaluate_disconnect(),
    # _evaluate_battery(), _evaluate_no_therapy_at_night()

# AlertConditionTracker (alert_evaluator.py) - Tracks duration-based conditions
class AlertConditionTracker:
    def start_condition(self, condition_key: str)
    def reset_condition(self, condition_key: str)
    def duration_seconds(self, condition_key: str) -> float
    def can_fire(self, alert_type: AlertType) -> bool  # Deduplication with cooldown

@dataclass
class AlertItemConfig:
    enabled: bool = True
    threshold: int = 0
    duration_seconds: int = 30
    severity: str = "warning"
    bypass_on_therapy: bool = False
    resend_interval_seconds: int = 300  # Cooldown before re-alerting

@dataclass
class Alert:
    id: str
    severity: AlertSeverity
    alert_type: AlertType
    message: str
    timestamp: datetime
    spo2: Optional[int]
    heart_rate: Optional[int]
    avaps_state: AVAPSState

class AlertSeverity(Enum):
    CRITICAL = "critical"  # SpO2 critical - immediate phone call
    HIGH = "high"          # HR out of range, extended disconnect
    WARNING = "warning"    # SpO2 warning, battery low
    INFO = "info"          # Reconnected, system notifications

    @property
    def pagerduty_severity(self) -> str:
        # Maps HIGH -> "error", others map directly

class AlertType(Enum):
    SPO2_CRITICAL = "spo2_critical"
    SPO2_WARNING = "spo2_warning"
    HR_HIGH = "hr_high"
    HR_LOW = "hr_low"
    DISCONNECT = "disconnect"
    NO_THERAPY_AT_NIGHT = "no_therapy_at_night"
    BATTERY_WARNING = "battery_warning"
    BATTERY_CRITICAL = "battery_critical"
    SYSTEM_ERROR = "system_error"
    TEST = "test"
```

### 3.4 Heartbeat Monitor (`heartbeat.py`)

**Purpose:** Dead-man's switch to detect if monitoring system fails.

**Behavior:**
- Pings Healthchecks.io every 60 seconds
- If pings stop, Healthchecks.io alerts family after grace period
- Sends system status metadata with each ping

**Implementation:**
```python
class HeartbeatMonitor:
    def __init__(self, healthchecks_url: str, interval_seconds: int = 60)
    async def start(self) -> None
    async def stop(self) -> None
    async def send_ping(self, status: str = "ok") -> bool
```

**Healthchecks.io Configuration:**
- Period: 1 minute
- Grace period: 3 minutes
- Alert channels: Email + PagerDuty integration

### 3.5 Database Layer (`database.py`)

**Purpose:** Persist readings and alerts for historical analysis.

**Schema:**

```sql
-- SpO2/HR readings (sampled every 5 seconds)
CREATE TABLE readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    spo2 INTEGER,
    heart_rate INTEGER,
    perfusion_index REAL,
    is_valid BOOLEAN,
    battery_level INTEGER,
    avaps_state TEXT,
    INDEX idx_timestamp (timestamp)
);

-- Alert history
CREATE TABLE alerts (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT,
    spo2 INTEGER,
    heart_rate INTEGER,
    avaps_state TEXT,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at DATETIME,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at DATETIME,
    INDEX idx_timestamp (timestamp)
);

-- System events (connections, errors, etc.)
CREATE TABLE system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT,
    metadata TEXT,  -- JSON blob
    INDEX idx_timestamp (timestamp)
);

-- User accounts
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    last_login DATETIME
);

-- Active sessions
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    last_activity DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**Data Retention (automated daily cleanup):**
- Readings: 30 days
- Alerts: 1 year
- System events: 90 days
- Cleanup runs automatically every 24 hours via state machine

### 3.6 Authentication (`auth.py`)

**Purpose:** Secure access to web dashboard and APIs.

**Features:**
- Username/password authentication
- bcrypt password hashing (cost factor 12)
- Session-based auth with secure cookies (web dashboard)
- **API token authentication** (30-day tokens for mobile/API access)
- Auto-logout after 30 minutes of inactivity (session-based)
- Rate limiting: 5 failed attempts = 15-minute lockout
- All credentials stored hashed in config.yaml

#### 3.6.1 API Token Authentication

For mobile apps and API clients, the system supports long-lived bearer tokens that don't require maintaining browser sessions.

**Token Characteristics:**
- 64-character hex tokens (256-bit entropy)
- 30-day expiration by default
- Stored in database with username, created_at, expires_at, device_name
- Last-used timestamp tracked for auditing

**API Endpoints:**

```
POST /auth/api/login
Request (JSON):
{
  "username": "admin",
  "password": "yourpassword",
  "device_name": "Android App"  // optional
}
Response:
{
  "success": true,
  "token": "47f27100fda020fb2408efb5aade0f2b...",
  "expires_at": "2024-02-15T10:30:00",
  "username": "admin",
  "expires_in_days": 30
}

POST /auth/api/logout
Header: Authorization: Bearer <token>
Response: {"success": true, "message": "Token revoked"}
```

**Using Tokens:**

All API endpoints (including relay API) accept token authentication via the Authorization header:

```
Authorization: Bearer <token>
```

Example:
```bash
curl -H "Authorization: Bearer 47f27100fda020fb2408..." \
  http://pi.local:5000/api/relay/status
```

**Unified Auth Decorator:**

The `api_login_required` decorator accepts both session and token auth:
1. First checks for session-based auth (web dashboard)
2. If no session, checks for Bearer token in Authorization header
3. Sets `g.api_user` to authenticated username

**Implementation:**
```python
class AuthManager:
    def __init__(self, config: AuthConfig)
    def verify_password(self, username: str, password: str) -> bool
    def create_session(self, user_id: int) -> str
    def validate_session(self, session_id: str) -> Optional[User]
    def invalidate_session(self, session_id: str) -> None
    def check_rate_limit(self, ip_address: str) -> bool

    @staticmethod
    def hash_password(password: str) -> str

# Token operations (via Database class)
async def create_api_token(username, token, expires_days, device_name)
async def get_api_token(token) -> Optional[Dict]
async def delete_api_token(token) -> bool
async def cleanup_expired_tokens() -> int
```

---

## 4. State Machine

### 4.1 Core Logic

The central state machine evaluates conditions every monitoring cycle (1 second) and determines appropriate actions.

```
                    ┌─────────────────┐
                    │     START       │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
              ┌─────│  BLE Connected? │─────┐
              │ NO  └─────────────────┘ YES │
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │ DISCONNECTED    │           │  AVAPS State?   │
    │ Start reconnect │           └────────┬────────┘
    │ Alert if >3 min │                    │
    └─────────────────┘         ┌──────────┴──────────┐
                                │                     │
                          AVAPS ON              AVAPS OFF
                                │                     │
                                ▼                     ▼
                    ┌─────────────────┐   ┌─────────────────┐
                    │ THERAPY_ACTIVE  │   │  Check SpO2     │
                    │ Monitor only    │   └────────┬────────┘
                    │ Suppress alarms │            │
                    └─────────────────┘   ┌────────┴────────┐
                                          │                 │
                                     SpO2 ≥ 90%        SpO2 < 90%
                                          │                 │
                                          ▼                 ▼
                              ┌─────────────────┐  ┌─────────────────┐
                              │    NORMAL       │  │  LOW_SPO2       │
                              │ Continue monitor│  │  Start 30s timer│
                              └─────────────────┘  └────────┬────────┘
                                                           │
                                                   Timer expires?
                                                   Still <90%?
                                                           │
                                                    ┌──────┴──────┐
                                                    │             │
                                                   NO            YES
                                                    │             │
                                                    ▼             ▼
                                        ┌───────────────┐ ┌───────────────┐
                                        │ Return to     │ │ 🚨 ALARM      │
                                        │ NORMAL        │ │ Local + Remote│
                                        └───────────────┘ └───────────────┘
```

### 4.2 State Definitions

| State | Condition | Action |
|-------|-----------|--------|
| `INITIALIZING` | System starting up | Wait for sensor connections |
| `DISCONNECTED` | BLE not connected | Attempt reconnect, alert if prolonged |
| `THERAPY_ACTIVE` | AVAPS on (>3W) | Monitor silently, no SpO2 alarms |
| `NORMAL` | AVAPS off, SpO2 ≥ 90% | Passive monitoring |
| `LOW_SPO2_WARNING` | AVAPS off, SpO2 < 90% | Start 30-second countdown |
| `ALARM` | SpO2 < 90% for 30+ sec, AVAPS off | Active alarm state |
| `SILENCED` | User silenced alerts | Temporary suppression |

### 4.3 State Machine Implementation

```python
class MonitorState(Enum):
    INITIALIZING = "initializing"
    DISCONNECTED = "disconnected"
    THERAPY_ACTIVE = "therapy_active"
    NORMAL = "normal"
    LOW_SPO2_WARNING = "low_spo2_warning"
    ALARM = "alarm"
    SILENCED = "silenced"

class O2MonitorStateMachine:
    def __init__(self, config: MonitorConfig,
                 ble_reader: CheckmeO2Reader,
                 avaps_monitor: AVAPSMonitor,
                 alert_manager: AlertManager,
                 database: Database)

    async def run(self) -> None:
        """Main monitoring loop"""

    async def evaluate_state(self) -> MonitorState:
        """Evaluate current conditions and return appropriate state"""

    async def handle_state_transition(self,
                                       old_state: MonitorState,
                                       new_state: MonitorState) -> None:
        """Handle side effects of state changes"""

    @property
    def current_state(self) -> MonitorState

    @property
    def low_spo2_duration(self) -> Optional[timedelta]
```

### 4.4 Decision Matrix (Therapy-Aware)

**Therapy OFF (AVAPS off - daytime/no treatment):**

| Condition | Duration | Alert Type | Severity |
|-----------|----------|------------|----------|
| SpO2 < 90% | ≥30s | spo2_critical | critical |
| SpO2 < 92% | ≥60s | spo2_warning | high |
| HR > 120 | ≥60s | hr_high | high |
| HR < 50 | ≥60s | hr_low | high |
| BLE disconnected | 0 min | disconnect | info |
| BLE disconnected | 2 hours | disconnect | warning |
| BLE disconnected | 3 hours | disconnect | high |
| Battery < 25% | immediate | battery_warning | warning |
| Battery < 10% | immediate | battery_critical | high |

**Therapy ON (AVAPS on - nighttime treatment):**

| Condition | Duration | Alert Type | Severity |
|-----------|----------|------------|----------|
| SpO2 < 85% | ≥120s | spo2_critical | critical |
| SpO2 warning | - | *disabled* | - |
| HR alerts | - | *disabled* | - |
| BLE disconnected | - | *disabled* | - |
| Battery < 25% | immediate | battery_warning | warning |
| Battery < 10% | immediate | battery_critical | high |

**Rationale:**
- During therapy ON, the patient is connected to AVAPS BiPAP and likely sleeping
- The SpO2 sensor may slip during sleep, so we use a more lenient threshold (85% vs 90%)
- HR monitoring is disabled during therapy as readings may be affected by sleep position
- Disconnect alerts are disabled since the sensor is expected to be charging
- Battery alerts remain active at all times

---

## 5. Configuration

### 5.1 Configuration File (`config.yaml`)

```yaml
# O2 Monitor Configuration
# SECURITY: Do not commit this file with real credentials

# Device Settings
devices:
  oximeter:
    mac_address: "C8:F1:6B:56:7B:F1"  # Checkme O2 Max MAC (actual device)
    name: "Checkme O2 Max"

  smart_plug:
    ip_address: "192.168.50.10"       # Kasa KP115 IP (actual network)
    name: "AVAPS Power Monitor"

# Monitoring Thresholds (legacy - see alerts section for new config)
thresholds:
  avaps:
    on_watts: 5.0                      # Power level = AVAPS on (tuned for BiPAP)
    off_watts: 4.0                     # Power level = AVAPS off

  ble:
    read_interval_seconds: 5           # How often to request readings
    max_reconnect_attempts: null       # null = infinite

# Alert Configuration - Therapy-Aware Multi-Severity System
# Each alert can have different thresholds for therapy ON (night) vs OFF (day)
alerts:
  # CRITICAL: SpO2 dangerously low - requires immediate intervention
  spo2_critical:
    enabled: true
    severity: critical
    therapy_off:
      threshold: 90                    # Trigger below this SpO2 %
      duration_seconds: 30             # Must be sustained for this duration
    therapy_on:
      enabled: true                    # Still alert during therapy, but lenient
      threshold: 85                    # Lower threshold (sensor may slip)
      duration_seconds: 120            # Longer duration (2 min)

  # HIGH: SpO2 warning zone - early warning before critical
  spo2_warning:
    enabled: true
    severity: high
    therapy_off:
      threshold: 92                    # Warn below this SpO2 %
      duration_seconds: 60             # 1 minute sustained
    therapy_on:
      enabled: false                   # Disable during therapy

  # HIGH: Heart rate too high
  hr_high:
    enabled: true
    severity: high
    therapy_off:
      threshold: 120                   # BPM upper limit
      duration_seconds: 60
    therapy_on:
      enabled: false                   # Disable during therapy

  # HIGH: Heart rate too low
  hr_low:
    enabled: true
    severity: high
    therapy_off:
      threshold: 50                    # BPM lower limit
      duration_seconds: 60
    therapy_on:
      enabled: false                   # Disable during therapy

  # ESCALATING: Oximeter disconnected - escalates over time
  disconnect:
    enabled: true
    therapy_off:
      info_minutes: 0                  # Immediate info-level notification
      warning_minutes: 120             # After 2 hours: warning
      high_minutes: 180                # After 3 hours: high priority
    therapy_on:
      enabled: false                   # Disable during therapy (charging)

  # WARNING: Battery getting low
  battery_warning:
    enabled: true
    threshold_percent: 25
    severity: warning

  # HIGH: Battery critically low
  battery_critical:
    enabled: true
    threshold_percent: 10
    severity: high

  # ESCALATING: No therapy during sleep hours
  no_therapy_at_night:
    enabled: true
    sleep_hours:
      start: "22:00"                   # 10 PM
      end: "07:00"                     # 7 AM
    info_minutes: 30                   # Info alert after 30 min
    warning_minutes: 60                # Warning alert after 1 hour

# Alerting Channels
alerting:
  pagerduty:
    routing_key: "${PAGERDUTY_ROUTING_KEY}"  # From env or config
    service_name: "O2 Monitor"

  local_audio:
    enabled: true
    alarm_sound: "sounds/alarm.wav"      # Loud alarm tone
    volume: 90                            # 0-100
    use_tts: true                         # Text-to-speech announcements
    tts_message: "Medical alert. Check on Dad immediately."
    repeat_interval_seconds: 30           # Repeat until acknowledged

  alexa:  # Optional - for multi-room announcements
    enabled: false
    notify_me_access_code: "${ALEXA_NOTIFY_CODE}"

  healthchecks:
    ping_url: "${HEALTHCHECKS_PING_URL}"
    interval_seconds: 60

# Alert Messages
messages:
  spo2_alarm: "Medical alert! Oxygen level critical. Check on Dad immediately."
  ble_disconnect: "O2 monitor disconnected. Please check the device."
  system_error: "O2 monitoring system error. Requires attention."

# Web Dashboard
web:
  host: "0.0.0.0"
  port: 5000
  secret_key: "${FLASK_SECRET_KEY}"   # For session encryption

# Authentication
auth:
  session_timeout_minutes: 30
  max_login_attempts: 5
  lockout_minutes: 15
  users:
    - username: "admin"
      # Generate with: python -c "import bcrypt; print(bcrypt.hashpw(b'password', bcrypt.gensalt()).decode())"
      password_hash: "$2b$12$..."
    - username: "family"
      password_hash: "$2b$12$..."

# Database
database:
  path: "data/history.db"
  retention:
    readings_days: 30
    alerts_days: 365
    events_days: 90

# Logging
logging:
  level: "INFO"
  file: "logs/o2monitor.log"
  max_size_mb: 10
  backup_count: 5
```

### 5.2 Environment Variables

For sensitive values, use environment variables:

```bash
# /home/pi/o2-monitor/.env
PAGERDUTY_ROUTING_KEY=your_routing_key_here
ALEXA_NOTIFY_CODE=your_code_here
HEALTHCHECKS_PING_URL=https://hc-ping.com/your-uuid
FLASK_SECRET_KEY=your_random_secret_key
```

---

## 6. Web Dashboard

### 6.1 Page Structure

```
/                     → Redirect to /dashboard (if authenticated)
/login                → Login page
/logout               → Logout action
/dashboard            → Main real-time display
/history              → Historical graphs
/alerts               → Alert log
/settings             → Configuration panel
/api/                 → JSON API endpoints
```

### 6.2 Dashboard Page (`/dashboard`)

**Real-time Display:**
```
┌─────────────────────────────────────────────────────────────┐
│  O2 Monitor Dashboard                    [User ▼] [Logout]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │    SpO2     │  │ Heart Rate  │  │    AVAPS Status     │  │
│  │             │  │             │  │                     │  │
│  │    97%      │  │   72 BPM    │  │    ⚫ OFF           │  │
│  │   ● Good    │  │   ● Normal  │  │   Power: 0.8W       │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ System Status                                           ││
│  │ • BLE: ● Connected (Battery: 85%)                       ││
│  │ • Last reading: 2 seconds ago                           ││
│  │ • Uptime: 3d 14h 22m                                    ││
│  │ • Last heartbeat: 45 seconds ago                        ││
│  │ • State: NORMAL                                         ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ SpO2 Last Hour                          [24h] [7d]      ││
│  │ 100├────────────────────────────────────                ││
│  │  95├─────────────────────██████████████                 ││
│  │  90├──────────────────────────────────── ← Alarm        ││
│  │  85├────────────────────────────────────                ││
│  │    └────────────────────────────────────                ││
│  │     12:00    12:15    12:30    12:45    13:00           ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  [Test Local Alarm]  [Test PagerDuty]  [Silence 30 min]    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 API Endpoints

```
GET  /api/status          → Current system status (JSON)
GET  /api/readings        → Recent readings (with pagination)
GET  /api/readings/range  → Readings for date range
GET  /api/alerts          → Alert history
POST /api/alerts/test     → Trigger test alert
POST /api/alerts/silence  → Silence alerts temporarily
GET  /api/config          → Current thresholds
PUT  /api/config          → Update thresholds (admin only)
```

**Example `/api/status` Response:**
```json
{
  "timestamp": "2026-01-11T14:30:00Z",
  "state": "normal",
  "ble": {
    "connected": true,
    "device_name": "Checkme O2 Max",
    "battery_level": 85,
    "last_reading_age_seconds": 2
  },
  "vitals": {
    "spo2": 97,
    "heart_rate": 72,
    "perfusion_index": 3.2,
    "is_valid": true
  },
  "avaps": {
    "state": "off",
    "power_watts": 0.8
  },
  "system": {
    "uptime_seconds": 310932,
    "last_heartbeat_age_seconds": 45,
    "alerts_silenced": false,
    "silence_remaining_seconds": null
  }
}
```

### 6.4 Mobile Responsiveness

- Responsive CSS (flexbox/grid)
- Touch-friendly button sizes (min 44px)
- Readable fonts on small screens
- Key metrics visible without scrolling
- Progressive Web App (PWA) capable for home screen install

---

## 7. Alerting Flow

### 7.1 SpO2 Alarm Sequence

```
1. SpO2 drops below 90%
   │
   ▼
2. State → LOW_SPO2_WARNING
   Start 30-second timer
   Log warning event
   │
   ▼
3. [Every second for 30 seconds]
   Check: Is SpO2 still <90%?
   Check: Is AVAPS still off?
   │
   ├─ If SpO2 ≥90% OR AVAPS on → Cancel timer, return to NORMAL
   │
   ▼
4. Timer expires, conditions still met
   │
   ▼
5. State → ALARM
   │
   ├──► Trigger local audio alarm (immediate)
   │    Loud alarm sound via Pi speakers
   │    Optional TTS: "Medical alert! Oxygen level critical..."
   │    Repeats every 30 seconds until acknowledged
   │
   ├──► Create PagerDuty incident (immediate)
   │    High urgency, includes all context
   │
   ├──► Log alert to database
   │
   ▼
6. Continue alarming until:
   - SpO2 recovers ≥90% for 60+ seconds
   - AVAPS turned on
   - User silences via dashboard
   - PagerDuty incident acknowledged
```

### 7.2 BLE Disconnect Sequence

```
1. BLE connection lost
   │
   ▼
2. Immediate reconnection attempt
   │
   ├─ Success → Resume monitoring
   │
   ▼
3. Exponential backoff reconnection
   2s → 4s → 8s → 16s → 32s → 60s (max)
   │
   ▼
4. After 3 minutes disconnected:
   │
   ├──► Log warning event
   │
   ├──► PagerDuty alert (medium urgency)
   │    "O2 monitor disconnected. Check device."
   │
   ├──► Optional: Alexa notification
   │
   ▼
5. Continue reconnection attempts indefinitely
   │
   ▼
6. On reconnection:
   - Resolve PagerDuty incident
   - Log reconnection event
   - Resume normal monitoring
```

### 7.3 PagerDuty Integration

**Incident Creation:**
```python
{
  "routing_key": "your_routing_key",
  "event_action": "trigger",
  "dedup_key": "o2-monitor-spo2-alarm-{timestamp}",
  "payload": {
    "summary": "O2 Alert: SpO2 at 85% for 30+ seconds (AVAPS off)",
    "severity": "critical",
    "source": "o2-monitor.local",
    "timestamp": "2026-01-11T14:30:00.000Z",
    "custom_details": {
      "spo2": 85,
      "heart_rate": 88,
      "avaps_state": "off",
      "duration_seconds": 30,
      "patient": "Dad",
      "location": "Living Room"
    }
  }
}
```

**Escalation Policy:**
1. Primary: Son (immediate)
2. Secondary: Sister (after 5 minutes if not acknowledged)

---

## 8. Error Handling & Resilience

### 8.1 Failure Modes

| Failure | Detection | Response |
|---------|-----------|----------|
| BLE disconnect | Connection state | Reconnect with backoff, alert after 3 min |
| Kasa plug unreachable | Network timeout | Assume AVAPS unknown, continue SpO2 monitoring |
| PagerDuty API down | HTTP error | Retry with backoff, log locally |
| Audio output fails | Playback error | Log error, continue with PagerDuty |
| Alexa unavailable | API error | Local audio still works, PagerDuty continues |
| Database full | Write error | Rotate old data, alert admin |
| Healthchecks.io down | HTTP error | Log warning, continue operation |
| Pi power loss | - | EcoFlow UPS provides runtime, Healthchecks.io alerts |

### 8.2 Graceful Degradation

**Priority Order (if components fail):**
1. **SpO2 Monitoring** - Core function, never degraded
2. **Local Alarm** - Critical for in-home alert
3. **Remote Alert** - Critical for family notification
4. **AVAPS Detection** - Important for alarm suppression
5. **Web Dashboard** - Useful but not life-safety
6. **Heartbeat** - Useful but not life-safety

**If AVAPS monitoring fails:**
- Treat AVAPS as "unknown"
- Lower SpO2 alarm threshold to 88% (more conservative)
- Log warning about degraded mode

### 8.3 Startup Sequence

```
1. Load configuration
2. Initialize database
3. Start web server (async)
4. Connect to Kasa plug
5. Connect to BLE oximeter
6. Start heartbeat monitor
7. Enter main monitoring loop
8. State = INITIALIZING until all connections ready
```

### 8.4 Shutdown Handling

- Graceful shutdown on SIGTERM/SIGINT
- Close BLE connection properly
- Flush pending database writes
- Send final healthcheck ping with "shutdown" status
- Log shutdown event

---

## 9. Security Considerations

### 9.1 Authentication Security

- Passwords hashed with bcrypt (cost factor 12)
- Session tokens: cryptographically random, 32 bytes
- Secure cookies: `HttpOnly`, `SameSite=Strict`
- HTTPS recommended (Let's Encrypt via reverse proxy)
- Rate limiting prevents brute force
- No password recovery (manual reset only)

### 9.2 Network Security

- Web dashboard bound to LAN by default
- Kasa plug communication over local network only
- PagerDuty/Healthchecks over HTTPS
- No inbound ports from internet required
- Consider firewall rules on Pi

### 9.3 Data Privacy

- Health data stored locally only
- PagerDuty receives minimal alert context
- No cloud analytics or telemetry
- Database file permissions: 600 (owner only)

---

## 10. Directory Structure

```
/home/pi/o2-monitor/
├── start.sh                # Start the application
├── stop.sh                 # Stop the application (kills all python)
├── main.py                 # Entry point, main loop
├── state_machine.py        # Core monitoring state machine
├── ble_reader.py           # Checkme O2 Max BLE integration
├── avaps_monitor.py        # Kasa smart plug monitoring
├── alerting.py             # PagerDuty + Alexa alerts
├── heartbeat.py            # Healthchecks.io integration
├── database.py             # SQLite operations
├── auth.py                 # Authentication helpers
├── config.py               # Configuration loader
├── models.py               # Data classes and enums
├── requirements.txt        # Python dependencies
├── config.yaml             # Configuration file
├── .env                    # Environment variables (secrets)
├── web/
│   ├── app.py              # Flask application
│   ├── routes.py           # Route handlers
│   ├── api.py              # JSON API endpoints
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css
│   │   └── js/
│   │       └── dashboard.js
│   └── templates/
│       ├── base.html
│       ├── login.html
│       ├── dashboard.html
│       ├── history.html
│       ├── alerts.html
│       └── settings.html
├── data/
│   └── history.db          # SQLite database
├── sounds/                 # (Empty - tones generated programmatically)
├── start.sh                # Start the application
├── stop.sh                 # Stop the application
├── logs/
│   └── o2monitor.log       # Application logs
└── scripts/
    ├── install.sh          # Installation script
    ├── setup_service.sh    # systemd service setup
    └── hash_password.py    # Utility to hash passwords
```

---

## 11. Implementation Phases

### Phase 1: Core Monitoring ✅
- [x] Set up Raspberry Pi environment
- [x] Test BLE connection to Checkme O2 Max *(Completed 2026-01-11 - see Appendix D)*
- [x] Test Kasa KP115 power reading *(Completed 2026-01-12 - IP: 192.168.50.10)*
- [x] Implement basic state machine
- [x] Add SQLite database for readings

### Phase 2: Alerting ✅
- [x] Integrate PagerDuty API
- [-] Implement Alexa alerting (optional, deferred)
- [x] Set up Healthchecks.io heartbeat
- [x] Implement local audio with generated tones + TTS
- [x] **Implement therapy-aware multi-severity alerting**

### Phase 3: Web Dashboard ✅
- [x] Create Flask application structure
- [x] Implement authentication
- [x] Build real-time dashboard
- [x] Add historical graphs
- [x] Create settings panel

### Phase 4: Hardening ✅
- [x] Add comprehensive error handling
- [x] Implement graceful degradation (partial)
- [x] Set up systemd service for auto-start
- [x] Configure log rotation
- [ ] Security audit

### Phase 5: Testing & Deployment
- [x] Integration testing (basic - hardware verified working)
- [ ] Simulated failure testing
- [ ] Family training on dashboard
- [x] Go-live monitoring (in production)
- [ ] Document runbooks

### Phase 6: Enhanced Alerting ✅
- [x] Implement therapy-aware alert evaluation
- [x] Add HR monitoring alerts (high/low)
- [x] Implement disconnect alert escalation
- [x] Add battery level alerts
- [x] Update config structure for new alert types
- [x] Update Settings page for new alert configuration
- [x] Add resend interval configuration per alert type

### Phase 7: Multi-Adapter Failover ✅ (New)
- [x] Disable internal Raspberry Pi Bluetooth
- [x] Add support for dual USB Bluetooth adapters
- [x] Implement AdapterManager with automatic switching
- [x] Add adapter status display on dashboard
- [x] Add Bluetooth & Timeouts settings section
- [x] Implement periodic adapter health checks
- [x] Add adapter_disconnect alert type

### Phase 8: Android Relay App (In Progress)
Pi-side API implementation for Android backup relay app.

**Completed:**
- [x] Create relay API blueprint (`src/web/relay_api.py`)
- [x] Implement `GET /api/relay/status` endpoint
- [x] Implement `POST /api/relay/reading` endpoint
- [x] Implement `POST /api/relay/batch` endpoint
- [x] Implement `GET /api/relay/app-version` endpoint
- [x] Add `source` column to readings table (tracks 'ble' vs 'relay')
- [x] Create `android/version.json` for app updates
- [x] **Implement API token authentication** (30-day bearer tokens)
- [x] Add `api_tokens` table to database
- [x] Add `POST /auth/api/login` endpoint (returns 30-day token)
- [x] Add `POST /auth/api/logout` endpoint (token revocation)
- [x] Unified auth decorator accepts both session and token auth

**Pending:**
- [ ] Implement Pi BLE backoff when receiving relay data
- [ ] Android app implementation (separate instance)

**Authentication:**
All relay API endpoints require authentication via either:
1. Session cookie (from web login)
2. Bearer token in Authorization header

To obtain a token:
```bash
curl -X POST http://pi:5000/auth/api/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "yourpassword", "device_name": "Android App"}'
# Returns: {"success": true, "token": "abc123...", "expires_in_days": 30}
```

**Relay API Endpoints (Implemented):**

```
GET /api/relay/status
Header: Authorization: Bearer <token>
Response: {
  "needs_relay": false,
  "ble_connected": true,
  "seconds_since_reading": 5,
  "relay_active": false,
  "pi_timestamp": "2024-01-15T10:30:00",
  "late_reading_threshold_seconds": 30
}

POST /api/relay/reading
Request: {
  "spo2": 97,
  "heart_rate": 72,
  "battery_level": 85,
  "timestamp": "2024-01-15T10:30:00",
  "is_valid": true
}
Response: {"success": true, "message": "Reading accepted", "reading_id": 1}

POST /api/relay/batch
Request: {"readings": [...]}
Response: {"success": true, "accepted": 3, "rejected": 0, "errors": []}

GET /api/relay/app-version
Response: {
  "latest_version": "1.0.0",
  "latest_version_code": 1,
  "min_supported_version": "1.0.0",
  "min_supported_version_code": 1,
  "download_url": "",
  "release_notes": "..."
}
```

**Note for Android Developer:**
The implemented API has minor field name differences from `android/DESIGN.md`:
- Status: `seconds_since_reading` (not `last_reading_age_seconds`)
- Status: `ble_connected` (not `pi_ble_connected`)
- Reading: `battery_level` (not `battery`)
- Reading: No `device_id` or `queued` fields (can be added if needed)
- Version: `latest_version` (not `version`), `download_url` (not `apk_url`)

---

## 12. Testing Plan

### 12.1 Mock Framework (`src/mocks.py`)

The system includes a comprehensive mock framework for testing without hardware:

**MockBLEReader:**
- Generates realistic SpO2 (92-99%) and HR (60-90 bpm) readings
- Simulates connection/disconnection
- Controllable low SpO2 events for alarm testing
- Sensor-off simulation

**MockAVAPSMonitor:**
- Simulates power readings (0.8W off, 15W on)
- Toggle state for testing
- Network error simulation

**MockScenarioRunner:**
- Pre-built scenarios: normal, therapy_active, low_spo2_alarm, ble_disconnect, sensor_off, network_error

Enable mock mode via:
- `MOCK_HARDWARE=true` environment variable, OR
- `mock_mode: true` in config.yaml

### 12.2 Unit Tests
- State machine transitions
- Threshold calculations
- Authentication logic
- Database operations

### 12.3 Integration Tests
- BLE connection/reconnection
- Kasa plug communication
- PagerDuty incident creation
- Healthchecks ping delivery

### 12.4 End-to-End Tests
- Simulate SpO2 drop → alarm sequence
- Simulate BLE disconnect → reconnect
- Dashboard login flow
- Alert silence functionality

### 12.4 Failure Simulation
- Kill BLE connection unexpectedly
- Block network to Kasa plug
- Disable PagerDuty routing key
- Simulate database corruption

---

## 13. Operational Runbooks

### 13.1 Daily Checks
1. Verify oximeter battery level (replace at <20%)
2. Check dashboard for any warnings
3. Confirm heartbeat is green on Healthchecks.io

### 13.2 Responding to Alerts
1. **SpO2 Alarm**: Physically check on patient immediately
2. **BLE Disconnect**: Check oximeter placement, battery, restart if needed
3. **Heartbeat Failure**: SSH to Pi, check service status, restart if needed

### 13.3 Common Issues
- **Oximeter shows invalid readings**: Ensure finger placement, check for cold hands
- **AVAPS shows wrong state**: Verify power thresholds match actual device draw
- **Dashboard not loading**: Check Flask service, view logs

---

## 14. Future Enhancements

### 14.1 Trend-Based Alerting (High Priority)
Current alerting uses simple threshold (SpO2 < 90% for 30 seconds). A gradual decline pattern is more clinically significant than a sudden drop:

- **Gradual decline** (97→95→93→91→89 over minutes): Likely true hypoxemia - high priority alert
- **Sudden drop** (97→82 instantly): Likely sensor artifact (finger moved, poor placement) - may warrant different handling

Enhancement: Implement trend analysis that considers the rate of SpO2 decline and pattern of recent readings to reduce false alarms while catching true desaturation events earlier.

### 14.2 Historical Recording Download
The Checkme O2 Max stores overnight recording sessions internally. Current implementation only reads real-time values (command 0x17). Future enhancement could:
- Download stored recording sessions via BLE
- Fill gaps when BLE connection was lost
- Provide complete overnight SpO2 trend for physician review

### 14.3 Other Enhancements
- **Additional sensors**: Room temperature, motion detection
- **Family mobile app**: Native iOS/Android with push notifications
- **Voice control**: "Alexa, what's Dad's oxygen level?"
- **EMR integration**: Export data for physician review
- **Redundant monitoring**: Second oximeter as backup

---

## 15. References

- [ble_spo2 GitHub Repository](https://github.com/mhgue/ble_spo2) - **Primary reference for BLE protocol and working implementation**
- [BLE-GATT Python Library](https://github.com/ukBaz/BLE_GATT) - D-Bus based BLE library that works with Checkme O2 Max
- [pydbus Documentation](https://github.com/LEW21/pydbus) - D-Bus bindings used by BLE-GATT
- [python-kasa Documentation](https://python-kasa.readthedocs.io/)
- [PagerDuty Events API v2](https://developer.pagerduty.com/docs/events-api-v2/overview/)
- [Healthchecks.io Documentation](https://healthchecks.io/docs/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Wellue Checkme O2 Max Product Page](https://www.wellue.com/)
- [BlueZ D-Bus API](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc) - Low-level BlueZ documentation

---

## Appendix A: systemd Service File

```ini
# /etc/systemd/system/o2monitor.service
[Unit]
Description=O2 Monitoring System
After=network.target bluetooth.target
Wants=bluetooth.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/o2-monitor
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/home/pi/o2-monitor/.env
ExecStart=/home/pi/o2-monitor/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## Appendix B: Requirements

### B.1 System Requirements

The virtual environment **must** be created with system site packages:
```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
```

This is required for PyGObject/GLib access (D-Bus BLE communication).

### B.2 System Packages (apt)

```bash
# Required for BLE-GATT/pydbus
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
sudo apt install libdbus-1-dev libglib2.0-dev

# BlueZ (usually pre-installed on Raspbian)
sudo apt install bluez
```

### B.3 Python Requirements

```
# requirements.txt

# BLE Communication (D-Bus based - works with Checkme O2 Max)
BLE_GATT>=0.5.0         # BLE GATT via D-Bus
pydbus>=0.6.0           # D-Bus bindings

# Smart Plug
python-kasa>=0.5.0      # Kasa KP115 power readings

# Audio
pygame>=2.5.0           # Audio playback for local alarms

# Web Framework
flask>=2.3.0            # Web framework
flask-login>=0.6.0      # Session management

# Security
bcrypt>=4.0.0           # Password hashing

# HTTP/API
aiohttp>=3.8.0          # Async HTTP (PagerDuty, Healthchecks)
requests>=2.31.0        # Sync HTTP fallback

# Configuration
python-dotenv>=1.0.0    # Environment variables
pyyaml>=6.0             # Configuration parsing
ruamel.yaml>=0.17.0     # YAML processing (vext dependency)

# Scheduling
apscheduler>=3.10.0     # Scheduled tasks

# Database
aiosqlite>=0.19.0       # Async SQLite

# Templating
jinja2>=3.1.0           # Templating
```

### B.4 BlueZ Configuration

Ensure BlueZ service is running:
```bash
sudo systemctl status bluetooth
sudo systemctl enable bluetooth
```

Trust the device (one-time):
```bash
bluetoothctl
> scan on
> trust C8:F1:6B:56:7B:F1
> quit
```

---

## Appendix C: BLE Protocol Details (Viatom/Wellue)

This appendix documents the proprietary BLE protocol used by Viatom/Wellue devices including the Checkme O2 Max. This information was derived from the [ble_spo2 project](https://github.com/mhgue/ble_spo2) and confirmed through testing.

### C.1 Command Packet Format (TX)

Commands sent to the device use this format:

```
Byte 0:     0xAA (start byte)
Byte 1:     Command code
Byte 2:     Command complement (0xFF ^ cmd)
Bytes 3-4:  Block ID (0x0000 for simple commands)
Bytes 5-6:  Payload length (little-endian, 0x0000 for simple commands)
Byte 7:     CRC-8
```

**Known Commands:**
| Code | Purpose |
|------|---------|
| 0x17 | Request current sensor values (SpO2, HR, battery, etc.) |

### C.2 Response Packet Format (RX)

Responses received from the device:

```
Byte 0:     0x55 (start byte)
Byte 1:     Response type
Byte 2:     Response complement
Bytes 3-4:  Block ID
Bytes 5-6:  Payload length (little-endian)
Bytes 7+:   Payload data
Last byte:  CRC-8
```

### C.3 Sensor Reading Payload (Command 0x17 Response)

When payload length = 0x0D (13 bytes):

```
Byte 0:  SpO2 (0-100, percentage)
Byte 1:  Heart Rate (BPM)
Byte 2:  Status flag:
           0xFF = sensor off (no finger detected)
           0x00 = idle (valid sensor but no reading yet)
           Other = valid reading
Bytes 3-6: Reserved/unknown
Byte 7:  Battery level (0-100, percentage)
Byte 8:  Reserved/unknown
Byte 9:  Movement indicator
Bytes 10-12: Reserved/unknown
```

### C.4 CRC-8 Calculation

```python
def calc_crc(data: bytes) -> int:
    """Calculate CRC-8 for Viatom protocol."""
    crc = 0x00
    for b in data:
        chk = (crc ^ b) & 0xFF
        crc = 0x00
        if chk & 0x01: crc ^= 0x07
        if chk & 0x02: crc ^= 0x0e
        if chk & 0x04: crc ^= 0x1c
        if chk & 0x08: crc ^= 0x38
        if chk & 0x10: crc ^= 0x70
        if chk & 0x20: crc ^= 0xe0
        if chk & 0x40: crc ^= 0xc7
        if chk & 0x80: crc ^= 0x89
    return crc
```

### C.5 Notification Handling

The device sends notifications in response to command 0x17. Important behaviors:

1. **Multiple Notifications Per Request**: The device may send 2-3 notification packets for a single request. Implement deduplication with a minimum time gap (1 second recommended).

2. **Packet Fragmentation**: Notifications may arrive fragmented. Buffer incoming data and look for complete packets starting with 0x55.

3. **Reading Interval**: Request readings at 10-second intervals to avoid overwhelming the device while maintaining adequate monitoring granularity.

---

## Appendix D: BLE Device Notes and Lessons Learned

This appendix documents critical findings from BLE testing that are essential for reliable operation.

### D.1 Device Characteristics

| Property | Value |
|----------|-------|
| Device Name | Checkme O2 Max |
| MAC Address Type | Random (LE Random) |
| Service UUID | Device uses custom Viatom service |
| Pairing | Not required - use "trust" instead |

### D.2 Why Common BLE Libraries Fail

Testing showed that **bleak**, **bluepy**, and **pygatt** all fail with "Software caused connection abort" when connecting to this device. This is due to:

1. **Random Address Handling**: The device uses BLE Random Address type, which some libraries don't handle correctly
2. **BlueZ D-Bus Timing**: Direct BlueZ D-Bus communication (via BLE-GATT/pydbus) works where higher-level abstractions fail
3. **Connection State Management**: The BLE-GATT library properly manages the D-Bus connection state

### D.3 First-Time Device Setup

Before the monitoring software can connect:

1. **Scan and Trust** (one-time setup):
   ```bash
   bluetoothctl
   > scan on
   # Wait for device to appear
   > trust C8:F1:6B:56:7B:F1
   > quit
   ```

2. **Do NOT Pair**: Using `pair` command causes connection issues. Only `trust` is needed.

3. **Device Display**: The device display does NOT need to stay on after initial connection. Testing confirmed 45+ readings captured with display off.

### D.4 Connection Reliability

- **Expect Retries**: Initial connections typically require 5-20 attempts
- **Retry Delay**: 2-second delay between attempts works well
- **Subsequent Connections**: Once trusted, connections are faster on subsequent runs
- **No Pairing Mode Needed**: Device does not need to be in pairing mode

### D.5 Virtual Environment Requirements

The Python virtual environment MUST be created with `--system-site-packages`:

```bash
python3 -m venv --system-site-packages venv
```

This is required because:
- PyGObject (GLib bindings) is complex to install via pip
- System packages provide the necessary D-Bus and GLib integration
- The BLE-GATT library depends on these system bindings

### D.6 Known Working Test Script

The file `test_working.py` in the project root contains a verified working implementation. Use this as the basis for `ble_reader.py`:

```bash
# Run with venv python directly:
./test_working.py C8:F1:6B:56:7B:F1 10 10

# Or activate venv first:
source venv/bin/activate && python test_working.py
```

---

## Appendix E: Development Session Learnings (2026-01-12)

This appendix documents key findings and tuned values from the development and testing session.

### E.1 Device Configuration

**Kasa Smart Plug:**
- Discovered IP: `192.168.50.10` (initial config had wrong IP 192.168.1.100)
- Use `kasa discover` or web Settings page to find plug on network

**Power Thresholds (tested with BiPAP/CPAP):**
- Standby power: ~3.2W
- Running power: ~6.4W
- Tuned thresholds: `on_watts: 5.0`, `off_watts: 4.0`

**BLE Polling:**
- Changed from 10-second to 5-second interval for more responsive monitoring
- Late reading threshold set to 30 seconds in dashboard (was 15s)

### E.2 Flask Caching Behavior

Flask caches templates and static files. After modifying any files in `src/web/`, the application must be restarted:

```bash
./stop.sh && sleep 2 && ./start.sh
```

Or manually:
```bash
pkill -f "src.main"; sleep 2; source venv/bin/activate && nohup python -m src.main --config config.yaml > /tmp/o2monitor.log 2>&1 &
```

### E.3 Chart Data Limits

Dashboard chart data limits were adjusted based on time range:
- 1 hour: 500 readings (5-second intervals)
- 6 hours: 3000 readings
- 24 hours: 10000 readings

### E.4 External Service Integration

**PagerDuty:**
- Uses Events API v2
- Test alerts must use `trigger_alarm()` not `trigger_local_only()` to send to PagerDuty
- Severity levels map: critical, error (high), warning, info

**Healthchecks.io:**
- Ping URL configured in Settings page
- Heartbeat sent every 60 seconds

### E.5 GitHub Repository

- Repository: https://github.com/dmattox-sparkcodelabs/O2Monitor
- `config.yaml` is gitignored (contains secrets)
- `config.example.yaml` provides template for new installations

### E.6 Bluetooth Adapter Configuration (2026-01-14)

- **Internal Bluetooth disabled**: `dtoverlay=disable-bt` in `/boot/firmware/config.txt`
- **Hallway adapter**: Insignia USB, MAC 10:A5:62:EC:E8:A5 (on USB extension cable)
- **Bedroom adapter**: Insignia USB, MAC 10:A5:62:79:03:8A (direct connection)
- **Kasa Smart Plug IP**: 192.168.4.126 (updated from 192.168.50.10)
- **AVAPS thresholds tuned**: on_watts=25.0, off_watts=20.0 (actual BiPAP power draw)

---

---

## Appendix F: Multi-Adapter Bluetooth Setup (2026-01-14)

This appendix documents the Bluetooth adapter configuration for reliable multi-adapter failover.

### F.1 Disabling Internal Bluetooth

The Raspberry Pi 4's internal Bluetooth can interfere with external USB adapters (the "Zombie Adapter" problem). BlueZ may prioritize hci0 even when it's not the desired adapter.

**Solution:** Add to `/boot/firmware/config.txt`:
```
dtoverlay=disable-bt
```

Reboot required after this change.

### F.2 USB Bluetooth Adapter Selection

**Confirmed Working:**
- Insignia USB Bluetooth adapters (work out of the box with BlueZ)

**Not Recommended:**
- ASUS USB-BT500 (requires manual driver installation, driver build fails on ARM)

### F.3 Adapter Configuration

After plugging in adapters, verify with:
```bash
hciconfig -a
```

Example output:
```
hci0:   Type: Primary  Bus: USB
        BD Address: 10:A5:62:EC:E8:A5  ACL MTU: 1021:8  SCO MTU: 64:1
        UP RUNNING
        ...

hci1:   Type: Primary  Bus: USB
        BD Address: 10:A5:62:79:03:8A  ACL MTU: 1021:8  SCO MTU: 64:1
        DOWN
        ...
```

### F.4 Configuration in config.yaml

```yaml
bluetooth:
  adapters:
    - name: Hallway           # Display name on dashboard
      mac_address: 10:A5:62:EC:E8:A5
    - name: Bedroom
      mac_address: 10:A5:62:79:03:8A
  read_interval_seconds: 5    # How often to poll oximeter
  late_reading_seconds: 30    # Reading considered "late" after this
  switch_timeout_minutes: 5   # Switch adapters after no readings for this long
  bounce_interval_minutes: 1  # When switching, try each adapter this often
```

### F.5 Dashboard Status Indicators

The dashboard displays both adapters with color-coded status:
- **Green (Active)**: Connected and receiving readings
- **Amber pulsing (Connecting)**: Attempting to connect
- **Blue (Standby)**: Detected but intentionally down
- **Gray (Offline)**: Not detected (unplugged or failed)

### F.6 Adapter Switching Behavior

1. System starts with first configured adapter
2. If no readings received for `switch_timeout_minutes`, enters "switching mode"
3. In switching mode, cycles to next adapter every `bounce_interval_minutes`
4. Continues bouncing until connection is restored
5. Health check runs every 60 seconds to detect unplugged adapters
6. `adapter_disconnect` alert fires if a configured adapter is not detected

---

*This document should be reviewed and updated as implementation progresses and requirements evolve.*
