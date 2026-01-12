# O2 Monitor - Implementation Todo List

**Project:** O2 Monitoring System for OHS Patient
**Created:** 2026-01-11
**Status:** Phase 6 Complete

---

## Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed
- `[!]` Blocked or needs attention
- `[-]` Skipped/Not needed
- `[H]` Requires hardware testing (user must run manually)

---

## Phase 1: Core Infrastructure

### 1.1 Environment Setup
- [x] Create Python virtual environment with `--system-site-packages`
- [x] Verify PyGObject/GLib available in venv
- [x] Install BLE-GATT and pydbus
- [x] Test BLE connectivity to Checkme O2 Max
- [x] Create working test script (`test_working.py`)
- [x] Install remaining Python dependencies
  - [x] python-kasa (smart plug)
  - [x] pygame (audio)
  - [x] flask, flask-login (web)
  - [x] bcrypt (auth)
  - [x] aiohttp, requests (HTTP)
  - [x] pyyaml, python-dotenv (config)
  - [x] aiosqlite (database)
- [x] Create project directory structure:
  ```
  O2Monitor/
  ├── src/
  │   ├── __init__.py
  │   ├── main.py
  │   ├── config.py
  │   ├── models.py
  │   ├── state_machine.py
  │   ├── ble_reader.py
  │   ├── avaps_monitor.py
  │   ├── alerting.py
  │   ├── heartbeat.py
  │   ├── database.py
  │   └── web/
  │       ├── __init__.py
  │       ├── app.py
  │       ├── routes.py
  │       ├── api.py
  │       ├── auth.py
  │       ├── static/
  │       │   ├── css/
  │       │   └── js/
  │       └── templates/
  ├── data/
  ├── logs/
  ├── sounds/
  ├── tests/
  ├── config.yaml
  ├── .env.example
  └── requirements.txt
  ```

### 1.2 Configuration System
- [x] Create `config.yaml` template with all settings
  - [x] Device settings (oximeter MAC, plug IP)
  - [x] Threshold settings (SpO2, AVAPS power)
  - [x] Alerting settings (PagerDuty, audio, Alexa)
  - [x] Web settings (host, port)
  - [x] Auth settings (users, session timeout)
  - [x] Database settings (path, retention)
  - [x] Logging settings
  - [x] mock_mode setting for testing
- [x] Create `.env.example` with placeholder secrets
- [x] Implement `config.py` configuration loader
  - [x] Load YAML file
  - [x] Substitute environment variables (${VAR} syntax)
  - [x] Validate required settings
  - [x] Provide typed access to config values (dataclasses)
  - [x] Support MOCK_HARDWARE env var override

### 1.3 Data Models
- [x] Create `models.py` with data classes
  - [x] `OxiReading` - SpO2, HR, battery, movement, timestamp, is_valid
  - [x] `AVAPSState` - Enum (ON, OFF, UNKNOWN)
  - [x] `MonitorState` - Enum (INITIALIZING, DISCONNECTED, THERAPY_ACTIVE, NORMAL, LOW_SPO2_WARNING, ALARM, SILENCED)
  - [x] `Alert` - id, type, severity, message, timestamp, vitals, acknowledged
  - [x] `AlertType` - Enum (SPO2_LOW, BLE_DISCONNECT, SYSTEM_ERROR, TEST)
  - [x] `AlertSeverity` - Enum (CRITICAL, WARNING, INFO)
  - [x] `SystemStatus` - comprehensive status snapshot
  - [x] `BLEStatus` - BLE connection status (added)

---

## Phase 2: Device Integration

### 2.1 BLE Reader Module (`ble_reader.py`)
- [x] Convert `test_working.py` to proper module
- [x] Create `CheckmeO2Reader` class
  - [x] `__init__(mac_address, callback, read_interval=10)`
  - [x] `connect()` - blocking with retry loop
  - [x] `disconnect()` - cleanup BLE connection
  - [x] `start()` - begin monitoring (blocking, runs GLib loop)
  - [x] `stop()` - signal stop and cleanup
  - [x] `request_reading()` - send command 0x17
  - [x] `handle_notification()` - parse incoming data
  - [x] `_process_reading()` - extract SpO2/HR from payload
  - [x] `_calc_crc()` - CRC-8 calculation
  - [x] `_build_command()` - construct command packet
- [x] Implement callback mechanism
  - [x] Call user callback with `OxiReading` on each valid reading
  - [x] Call error callback on connection loss
- [x] Add connection state tracking
  - [x] `is_connected` property
  - [x] `last_reading` property
  - [x] `battery_level` property
  - [x] `connection_attempts` counter
- [x] Add logging throughout
- [x] Handle graceful shutdown (signal handling)
- [x] Test module standalone
  - [x] Verify readings come through callback
  - [ ] Verify reconnection works after manual disconnect
  - [x] Verify clean shutdown
- [x] Add `get_reader()` factory function for mock/real selection

### 2.2 AVAPS Monitor Module (`avaps_monitor.py`)
- [H] Test Kasa KP115 connection
  - [H] Find plug IP address on network (use `python src/avaps_monitor.py --discover`)
  - [H] Verify python-kasa can connect
  - [H] Read power consumption
- [H] Determine AVAPS power thresholds
  - [H] Measure power when AVAPS is ON (active therapy)
  - [H] Measure power when AVAPS is OFF (standby)
  - [x] Set ON threshold (e.g., >3W) - configured in config.yaml
  - [x] Set OFF threshold (e.g., <2W) - configured in config.yaml
- [x] Create `AVAPSMonitor` class
  - [x] `__init__(plug_ip, on_threshold, off_threshold)`
  - [x] `async get_power_watts()` - read current power
  - [x] `async is_on()` - returns bool based on thresholds
  - [x] `async get_state()` - returns AVAPSState enum
- [x] Add error handling for network issues
  - [x] Return UNKNOWN state on timeout
  - [x] Implement retry logic
  - [x] Log network errors
- [x] Add caching to reduce poll frequency
  - [x] Cache reading for 2 seconds (CACHE_DURATION_SECONDS)
  - [x] Invalidate on explicit refresh
- [~] Test module standalone
  - [x] Mock mode tests pass
  - [H] Verify real power readings with hardware
  - [x] Verify state detection (mock)
  - [x] Verify network error handling
- [x] Add `get_monitor()` factory function for mock/real selection
- [x] Add `discover_plugs()` for network device discovery

---

## Phase 3: Database Layer

### 3.1 Database Schema (`database.py`)
- [x] Create SQLite database initialization
  - [x] Create `readings` table
  - [x] Create `alerts` table
  - [x] Create `system_events` table
  - [x] Create `users` table
  - [x] Create `sessions` table
  - [x] Add indexes for timestamp columns
- [x] Implement `Database` class
  - [x] `__init__(db_path)`
  - [x] `async initialize()` - create tables if not exist
  - [x] `async close()` - close connection pool

### 3.2 Reading Operations
- [x] `async insert_reading(reading: OxiReading, avaps_state: AVAPSState)`
- [x] `async get_readings(start_time, end_time, limit=1000)`
- [x] `async get_latest_reading()`
- [x] `async get_reading_stats(start_time, end_time)` - min, max, avg

### 3.3 Alert Operations
- [x] `async insert_alert(alert: Alert)`
- [x] `async get_alerts(start_time, end_time, limit=100)`
- [x] `async get_active_alerts()` - unacknowledged
- [x] `async acknowledge_alert(alert_id, acknowledged_by)`
- [x] `async resolve_alert(alert_id)`

### 3.4 System Event Operations
- [x] `async log_event(event_type, message, metadata=None)`
- [x] `async get_events(start_time, end_time, event_type=None)`

### 3.5 User/Session Operations
- [x] `async get_user(username)`
- [x] `async create_session(user_id)` (also added create_user)
- [x] `async get_session(session_id)`
- [x] `async delete_session(session_id)`
- [x] `async cleanup_expired_sessions()`

### 3.6 Data Retention
- [x] `async cleanup_old_data()`
  - [x] Delete readings older than 30 days
  - [x] Delete alerts older than 365 days
  - [x] Delete events older than 90 days
- [ ] Schedule cleanup to run daily (will be done in main.py)

---

## Phase 4: Alerting System

### 4.1 Local Audio Alerting
- [ ] Obtain/create alarm sound files
  - [ ] `sounds/alarm.wav` - loud, attention-getting alarm
  - [ ] `sounds/alert.wav` - warning/notification sound
- [H] Test pygame audio on Raspberry Pi
  - [H] Install SDL2 mixer: `sudo apt install libsdl2-mixer-2.0-0`
  - [H] Verify speakers connected and working
  - [H] Test volume control
- [x] Implement audio alert functions (AudioAlert class)
  - [x] `play_alarm()` - play loud repeating alarm
  - [x] `play_alert()` - play single warning sound
  - [x] `stop_alarm()` - stop current playback
  - [x] `set_volume(level)` - adjust volume 0-100
- [ ] Implement TTS announcements (optional/future)
  - [ ] Use espeak or pyttsx3
  - [ ] "Medical alert. Check on Dad immediately."

### 4.2 PagerDuty Integration
- [ ] Set up PagerDuty account/service
  - [ ] Create service for O2 Monitor
  - [ ] Get Events API v2 routing key
  - [ ] Configure escalation policy (son -> sister)
- [x] Implement PagerDuty client (PagerDutyClient class)
  - [x] `async trigger_incident(summary, severity, details)`
  - [x] `async acknowledge_incident(dedup_key)`
  - [x] `async resolve_incident(dedup_key)`
- [x] Create dedup key strategy
  - [x] SpO2 alarms: `o2-spo2-{date}`
  - [x] BLE disconnect: `o2-ble-{date}`
- [ ] Test incident creation and resolution (requires PagerDuty account)

### 4.3 Healthchecks.io Integration
- [ ] Create Healthchecks.io account
  - [ ] Create check with 1-minute period
  - [ ] Set 3-minute grace period
  - [ ] Configure alert channels (email, PagerDuty)
- [x] Implement heartbeat client (HealthchecksClient class)
  - [x] `async send_ping(status="ok")`
  - [x] `async send_fail(message)`
  - [x] `async send_start()` - signal check starting
- [ ] Test ping delivery and failure detection (requires account)

### 4.4 Alert Manager (`alerting.py`)
- [x] Create `AlertManager` class
  - [x] `__init__(config)`
  - [x] `async trigger_alarm(alert)` - local + PagerDuty
  - [x] `async trigger_local_only(alert)` - local audio only
  - [x] `async resolve_alert(alert_id)`
  - [x] `silence(duration_minutes)` - temporary silence
  - [x] `unsilence()` - cancel silence
- [x] Implement silence logic
  - [x] Track silence end time
  - [x] `is_silenced` property
  - [x] `silence_remaining_seconds` property
- [x] Track active alerts
  - [x] `active_alerts` property
  - [x] Prevent duplicate alerts for same condition

### 4.5 Alexa Integration (Optional/Future)
- [ ] Research Alexa notification options
  - [ ] Notify Me skill
  - [ ] Alexa Routines
  - [ ] Home Assistant integration
- [ ] Implement if viable

---

## Phase 5: State Machine

### 5.1 Core State Machine (`state_machine.py`)
- [x] Create `O2MonitorStateMachine` class
  - [x] `__init__(config, ble_reader, avaps_monitor, alert_manager, database)`
  - [x] `async run()` - main monitoring loop
  - [x] `async evaluate_state()` - determine current state
  - [x] `async handle_state_transition(old, new)` - side effects
  - [x] `stop()` - signal shutdown
- [x] Implement state properties
  - [x] `current_state` - MonitorState enum
  - [x] `low_spo2_start_time` - when SpO2 dropped below threshold
  - [x] `low_spo2_duration` - timedelta since drop
  - [x] `get_status()` - comprehensive status snapshot

### 5.2 State Evaluation Logic
- [x] INITIALIZING -> DISCONNECTED/NORMAL/THERAPY_ACTIVE
  - [x] Wait for BLE connection
  - [x] Check AVAPS state
- [x] DISCONNECTED handling
  - [x] Track disconnect duration
  - [x] Alert after 3 minutes
  - [x] Transition to other states on reconnect
- [x] THERAPY_ACTIVE handling
  - [x] Suppress SpO2 alarms when AVAPS on
  - [x] Continue monitoring silently
  - [x] Log readings to database
- [x] NORMAL -> LOW_SPO2_WARNING
  - [x] Trigger when SpO2 < 90% AND AVAPS off
  - [x] Start 30-second countdown
- [x] LOW_SPO2_WARNING -> ALARM
  - [x] Trigger when 30 seconds elapsed
  - [x] SpO2 still < 90%
  - [x] AVAPS still off
- [x] LOW_SPO2_WARNING -> NORMAL
  - [x] Cancel if SpO2 >= 90%
  - [x] Cancel if AVAPS turned on
- [x] ALARM handling
  - [x] Trigger local + remote alerts
  - [x] Continue alarming until resolved
  - [x] Resolve when SpO2 recovers or AVAPS on
- [x] SILENCED handling
  - [x] Suppress local audio
  - [x] Still send PagerDuty for critical
  - [x] Auto-unsilence after duration (via AlertManager)

### 5.3 Integration with Components
- [x] BLE reader callback integration
  - [x] Receive readings from callback
  - [x] Update current vitals
  - [x] Log to database
- [x] AVAPS polling integration
  - [x] Poll every 5 seconds
  - [x] Update current state
- [x] Heartbeat integration
  - [x] Send ping every 60 seconds
  - [x] Include status metadata

### 5.4 Error Handling
- [x] Handle BLE disconnect during operation
- [x] Handle AVAPS monitor network failure
- [x] Handle database write failure
- [x] Handle PagerDuty API failure (in AlertManager)
- [x] Log all errors with context

---

## Phase 6: Web Dashboard

### 6.1 Flask Application Setup (`web/app.py`)
- [x] Create Flask application factory
- [x] Configure session management
- [x] Set up CSRF protection (via session secret)
- [x] Configure logging
- [x] Set up static file serving
- [x] Configure template rendering

### 6.2 Authentication (`web/auth.py`)
- [x] Implement login route
  - [x] Username/password form
  - [x] bcrypt password verification
  - [x] Session creation
  - [x] Rate limiting (5 attempts = 15-min lockout)
- [x] Implement logout route
  - [x] Session destruction
  - [x] Redirect to login
- [x] Implement `@login_required` decorator
- [x] Implement session validation middleware
- [x] Create password hashing utility script (see config.yaml comment)

### 6.3 Dashboard Routes (`web/routes.py`)
- [x] `/` - Redirect to dashboard or login
- [x] `/login` - Login page (via auth blueprint)
- [x] `/logout` - Logout action (via auth blueprint)
- [x] `/dashboard` - Main real-time display
- [x] `/history` - Historical graphs
- [x] `/alerts` - Alert log
- [x] `/settings` - Configuration panel (all logged-in users)

### 6.4 API Endpoints (`web/api.py`)
- [x] `GET /api/status` - Current system status
  - [x] State, vitals, AVAPS, BLE status, uptime
- [x] `GET /api/readings` - Recent readings
  - [x] Pagination support
  - [x] Time range filtering
- [x] `GET /api/readings/range` - Readings for date range
- [x] `GET /api/alerts` - Alert history
- [x] `POST /api/alerts/test` - Trigger test alert
- [x] `POST /api/alerts/silence` - Silence alerts
- [x] `POST /api/alerts/unsilence` - Cancel silence
- [x] `GET /api/config` - Current thresholds
- [x] `PUT /api/config` - Update thresholds (persists to config.yaml)
- [x] `POST /api/alerts/<id>/acknowledge` - Acknowledge alert
- [x] `POST /api/devices/discover` - Discover Kasa smart plugs

### 6.5 Templates
- [x] `base.html` - Base template with navigation
- [x] `login.html` - Login form
- [x] `dashboard.html` - Real-time dashboard
  - [x] SpO2 gauge/display
  - [x] Heart rate display
  - [x] AVAPS status indicator
  - [x] BLE connection status
  - [x] Battery level
  - [x] System state indicator
  - [x] Live chart (last hour)
  - [x] Test/silence buttons
- [x] `history.html` - Historical charts
  - [x] Date range picker
  - [x] SpO2 trend chart
  - [x] Heart rate trend chart
  - [x] Event markers
- [x] `alerts.html` - Alert log table
  - [x] Filter by type/severity
  - [x] Acknowledge buttons
- [x] `settings.html` - Configuration panel
  - [x] Threshold adjustments
  - [x] Alert settings (PagerDuty, Healthchecks)
  - [x] Settings persist to config.yaml
  - [-] User management (not implemented - add via config file)

### 6.6 Static Assets
- [x] `static/css/style.css` - Dashboard styling
  - [x] Responsive design
  - [x] Color coding for states
  - [x] Touch-friendly buttons
- [x] `static/js/dashboard.js` - Real-time updates
  - [x] Polling for live data (5-second interval)
  - [x] Chart.js for graphs
  - [x] Auto-refresh
  - [x] Refresh progress bar indicator
  - [x] 12-hour time format (not military time)
- [x] `static/js/history.js` - Historical charts
  - [x] 12-hour time format
  - [x] Stats display (avg, min, max)
- [x] `static/js/alerts.js` - Alert management
- [x] `static/js/settings.js` - Configuration management

### 6.7 Real-time Updates
- [-] Implement SSE (Server-Sent Events) endpoint - chose polling instead
- [x] Implement polling approach
  - [x] Poll `/api/status` every 5 seconds
- [x] Update dashboard without page refresh

---

## Phase 7: Main Application

### 7.1 Entry Point (`main.py`)
- [x] Parse command-line arguments
  - [x] `--config` - config file path
  - [x] `--debug` - enable debug mode
  - [x] `--mock` - force mock mode
- [x] Load configuration
- [x] Initialize logging
- [x] Initialize database
- [x] Initialize components
  - [x] BLE reader
  - [x] AVAPS monitor
  - [x] Alert manager
  - [x] Heartbeat (via AlertManager)
- [x] Start web server (Phase 6 - integrated)
  - [x] Flask runs in background thread
  - [x] Accessible at http://0.0.0.0:5000 (configurable)
- [x] Start state machine (main loop)
- [x] Handle signals (SIGTERM, SIGINT)
- [x] Graceful shutdown sequence

### 7.2 Threading/Concurrency Model
- [x] Determined concurrency approach
  - [x] Option C: asyncio with threads where needed
  - [x] BLE reader uses separate thread for mock, GLib for real
  - [x] State machine runs in asyncio event loop
- [x] Implement thread-safe data sharing
  - [x] Current vitals (via state machine properties)
  - [x] Current state
  - [x] Alert status
- [x] Handle component communication

### 7.3 Logging Configuration
- [x] Set up rotating file handler
  - [x] `logs/o2monitor.log`
  - [x] Max 10MB per file
  - [x] Keep 5 backups (configurable)
- [x] Set log levels per module
- [x] Include timestamp, level, module, message
- [x] Log to console in debug mode

---

## Phase 8: Deployment

### 8.1 systemd Service
- [ ] Create service file `/etc/systemd/system/o2monitor.service`
- [ ] Configure auto-restart on failure
- [ ] Configure restart delay (10 seconds)
- [ ] Set up environment file loading
- [ ] Enable service for boot start
- [ ] Test service start/stop/restart

### 8.2 Installation Script (`scripts/install.sh`)
- [ ] Check prerequisites (Python, BlueZ)
- [ ] Create virtual environment
- [ ] Install Python dependencies
- [ ] Create directory structure
- [ ] Copy default configuration
- [ ] Set file permissions
- [ ] Trust BLE device
- [ ] Install systemd service
- [ ] Print setup instructions

### 8.3 Security Hardening
- [ ] Set database file permissions (600)
- [ ] Set config file permissions (600)
- [ ] Set log directory permissions
- [ ] Configure firewall (if needed)
- [ ] Review and remove debug settings

### 8.4 Backup Strategy
- [ ] Script to backup database
- [ ] Script to backup configuration
- [ ] Document restore procedure

---

## Phase 9: Testing

### 9.1 Unit Tests
- [ ] Test state machine transitions
- [ ] Test threshold calculations
- [ ] Test CRC calculation
- [ ] Test packet parsing
- [ ] Test authentication logic
- [ ] Test database operations

### 9.2 Integration Tests
- [ ] Test BLE connection/reconnection
- [ ] Test AVAPS state detection
- [ ] Test PagerDuty incident creation
- [ ] Test Healthchecks.io ping
- [ ] Test database persistence

### 9.3 End-to-End Tests
- [ ] Simulate SpO2 drop -> alarm sequence
- [ ] Simulate BLE disconnect -> reconnect
- [ ] Test dashboard login flow
- [ ] Test alert silence functionality
- [ ] Test web API endpoints

### 9.4 Failure Simulation
- [ ] Kill BLE connection unexpectedly
- [ ] Block network to Kasa plug
- [ ] Invalid PagerDuty key
- [ ] Database disk full simulation

### 9.5 Load/Duration Testing
- [ ] Run for 24+ hours continuously
- [ ] Verify no memory leaks
- [ ] Verify database growth is reasonable
- [ ] Verify reconnection works over time

---

## Phase 10: Documentation & Training

### 10.1 Documentation
- [ ] Update DESIGN.md with final implementation
- [ ] Create README.md with quick start
- [ ] Document configuration options
- [ ] Document API endpoints
- [ ] Create troubleshooting guide

### 10.2 Operational Runbooks
- [ ] Daily monitoring checklist
- [ ] Responding to SpO2 alarm
- [ ] Responding to BLE disconnect
- [ ] Responding to system down
- [ ] Restarting the service
- [ ] Updating the software

### 10.3 Family Training
- [ ] Dashboard walkthrough
- [ ] Alert response procedure
- [ ] Oximeter placement/charging
- [ ] Who to call for technical issues

---

## Immediate Next Steps

Priority order for next development session:

1. ~~**Create project structure** - Set up src/ directory and requirements.txt~~ [x] Done
2. ~~**Install dependencies** - Get python-kasa, pygame, flask, etc.~~ [x] Done
3. ~~**Implement models.py** - Data classes and enums~~ [x] Done
4. ~~**Implement config.py** - Configuration loader with config.yaml template~~ [x] Done
5. ~~**Create mock/simulation framework** - `src/mocks.py`~~ [x] Done
   - `MockBLEReader` - Generates realistic SpO2 (92-99%), HR (60-90 bpm) with occasional dips below 90%
   - `MockAVAPSMonitor` - Simulates power readings, can toggle state
   - `MockScenarioRunner` - Pre-built scenarios for testing alarm conditions
   - Enable via `MOCK_HARDWARE=true` env var or `mock_mode: true` in config
6. ~~**Convert test_working.py to ble_reader.py** - Real implementation `[H]`~~ [x] Done
7. ~~**Implement avaps_monitor.py** - Real Kasa integration~~ [x] Done
   - AVAPSMonitor class with python-kasa
   - discover_plugs() for network discovery
   - get_monitor() factory function
   - Mock tests pass, hardware tests pending `[H]`
8. ~~**Implement database.py** - SQLite persistence layer~~ [x] Done
9. ~~**Implement alerting.py** - Audio + PagerDuty integration~~ [x] Done
    - AudioAlert class for local audio
    - PagerDutyClient for remote alerting
    - HealthchecksClient for heartbeat
    - AlertManager to coordinate all
10. ~~**Implement state_machine.py** - Core monitoring logic~~ [x] Done
    - O2MonitorStateMachine class
    - All state transitions implemented
    - Component integration
11. ~~**Implement main.py** - Entry point and integration~~ [x] Done
    - Full application startup
    - Signal handling
    - Graceful shutdown
    - Web server integration
12. ~~**Web dashboard** (Phase 6)~~ [x] Done
    - Flask application with blueprints
    - Authentication with bcrypt + rate limiting
    - Dashboard, History, Alerts, Settings pages
    - REST API for real-time data
    - Chart.js visualizations
    - Responsive design

**Remaining tasks requiring user action:**

13. **Create user account** for web dashboard login
    - Generate password hash: `python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"`
    - Add to config.yaml under `auth.users`
14. **Set up external services** (accounts needed)
    - PagerDuty account and routing key (optional - configure via Settings page)
    - Healthchecks.io account and ping URL (optional - configure via Settings page)
15. **Hardware testing** `[H]`
    - Test Kasa KP115 plug: `python src/avaps_monitor.py --discover`
    - Test audio playback: `sudo apt install libsdl2-mixer-2.0-0`
16. **Create alarm sounds** `[H]`
    - Place alarm.wav and alert.wav in sounds/ directory
17. **Phase 8: Deployment** - systemd service, installation script

---

## Notes

- Device MAC: `C8:F1:6B:56:7B:F1`
- BLE library: BLE-GATT (not bleak/bluepy)
- Device must be "trusted" not "paired" in bluetoothctl
- Virtual env needs `--system-site-packages` for GLib
- Working test script: `test_working.py`
- **vext workaround**: vext.gi blocks system packages. Had to install `cffi==1.17.1` and `cryptography==42.0.8` with `--only-binary :all:` to get prebuilt ARM wheels
- **pip upgrade**: Upgraded pip to 25.3 (old 20.3.4 had TOML parsing bugs)
- **BLE command 0x17**: Returns current real-time reading only (not stored data)
- **Trend analysis important**: Gradual SpO2 decline (94→93→92→91→90) more clinically significant than sudden drop (97→82 = likely sensor artifact)

---

### Session 2026-01-11 Evening Fixes
- Fixed BLE reader to run in background thread for real hardware (GLib main loop blocking issue)
- Fixed signal handler error in threads (can't set signals in non-main thread)
- Added refresh progress bar on dashboard
- Fixed history page stats not showing (field name mismatch: avg_spo2 vs spo2_avg)
- Fixed dashboard chart timezone mismatch (JS sends UTC, DB stores local time)
- Changed from 24-hour to 12-hour time format per user request
- Removed role-based access for Settings page (simplified - no user roles needed)
- Fixed logout button visibility (white text on navbar)
- Added settings persistence to config.yaml
- Added SpO2 threshold zones on charts (red <90%, yellow 90-92%)
- Added HR threshold zones on charts (red <50/>120, yellow 50-60/100-120)
- **Added automatic BLE reconnection** - reconnects within 5 seconds if connection drops
- **Pending**: Kasa smart plug IP needs configuration (192.168.1.100 timing out)
- **Pending**: Install libsdl2-mixer for audio alerts: `sudo apt install libsdl2-mixer-2.0-0`

*Last Updated: 2026-01-11*
