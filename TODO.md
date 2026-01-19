# O2 Monitor - Implementation Todo List

> **DISCLAIMER: NOT FOR MEDICAL USE**
>
> This project is a proof of concept and educational exercise only. It is NOT a certified medical device and should NOT be relied upon for medical monitoring, diagnosis, or treatment decisions. This system has not been validated, tested, or approved for clinical use. Do not use this system as a substitute for professional medical care or FDA-approved monitoring equipment. The authors assume no liability for any use of this software.

---

**Project:** O2 Monitoring System for OHS Patient (Proof of Concept)
**Created:** 2026-01-11
**Status:** Phase 14 (Vision Service) Implementation Complete - Hardware Testing Required

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
  - [x] Verify reconnection works after manual disconnect
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
- [x] Schedule cleanup to run daily (runs every 24h in state_machine.py)

---

## Phase 4: Alerting System

### 4.1 Local Audio Alerting
- [x] ~~Obtain/create alarm sound files~~ - Not needed, tones generated programmatically
- [x] Test pygame audio on Raspberry Pi
  - [x] Install SDL2 mixer: `sudo apt install libsdl2-mixer-2.0-0`
  - [x] Verify speakers connected and working
  - [x] Test volume control
- [x] Implement audio alert functions (AudioAlert class)
  - [x] `play_alarm()` - play loud repeating alarm with severity-based tones
  - [x] `play_alert()` - play single warning sound
  - [x] `stop_alarm()` - stop current playback
  - [x] `set_volume(level)` - adjust volume 0-100
  - [x] `_generate_tone()` - programmatic tone generation (no external files)
  - [x] Different tone patterns per severity (critical=fast high beeps, high=double beeps, etc.)
- [x] Implement TTS announcements
  - [x] Install espeak: `sudo apt install espeak`
  - [x] `speak()` method for TTS output
  - [x] Alert-specific messages ("Oxygen level critical at 85 percent")
  - [x] Repeating alarms include TTS every 30 seconds

### 4.2 PagerDuty Integration
- [x] Set up PagerDuty account/service
  - [x] Create service for O2 Monitor
  - [x] Get Events API v2 routing key
  - [x] Configure escalation policy
- [x] Implement PagerDuty client (PagerDutyClient class)
  - [x] `async trigger_incident(summary, severity, details)`
  - [x] `async acknowledge_incident(dedup_key)`
  - [x] `async resolve_incident(dedup_key)`
- [x] Create dedup key strategy
  - [x] SpO2 alarms: `o2-spo2-{date}`
  - [x] BLE disconnect: `o2-ble-{date}`
- [x] Test incident creation and resolution

### 4.3 Healthchecks.io Integration
- [x] Create Healthchecks.io account
  - [x] Create check with 1-minute period
  - [x] Set 3-minute grace period
  - [x] Configure alert channels (email, PagerDuty)
- [x] Implement heartbeat client (HealthchecksClient class)
  - [x] `async send_ping(status="ok")`
  - [x] `async send_fail(message)`
  - [x] `async send_start()` - signal check starting
- [x] Test ping delivery and failure detection

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

### 8.1 systemd Service ✅
- [x] Create service file `o2monitor.service`
- [x] Configure auto-restart on failure
- [x] Configure restart delay (10 seconds)
- [x] Set up environment (PYTHONUNBUFFERED)
- [x] Create install script `install-service.sh`
- [x] Install and test service
- [x] Verified working after reboot

### 8.2 Installation Script (`install.sh`)
- [x] Check prerequisites (Python, BlueZ, GLib, SDL2, espeak)
- [x] Create virtual environment with system-site-packages
- [x] Install Python dependencies
- [x] Create directory structure (data/, logs/)
- [x] Copy default configuration from config.example.yaml
- [x] Check for acknowledgment file
- [x] Prompt for BLE device trust
- [x] Optional systemd service install
- [x] Print setup instructions

### 8.3 Security Hardening
- [-] Set database file permissions (600) - Not needed for single-user home use
- [-] Set config file permissions (600) - Not needed for single-user home use
- [-] Set log directory permissions - Not needed for single-user home use
- [-] Configure firewall (if needed) - Router handles this
- [x] Review and remove debug settings - Flask runs in production mode

### 8.4 Backup Strategy
- [-] Script to backup database - Not needed (30-day retention, not clinically relevant)
- [x] Script to backup configuration (`backup-config.sh`)
- [x] Auto-prunes to last 10 backups

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

## Phase 10: Enhanced Alerting System (NEW - Priority)

### 10.1 Alert Configuration Model Updates
- [x] Update `models.py` with new alert types
  - [x] Add `AlertType.SPO2_CRITICAL`, `AlertType.SPO2_WARNING`
  - [x] Add `AlertType.HR_HIGH`, `AlertType.HR_LOW`
  - [x] Add `AlertType.BATTERY_WARNING`, `AlertType.BATTERY_CRITICAL`
  - [x] Add `AlertType.NO_THERAPY_AT_NIGHT`
  - [x] Add `AlertSeverity.HIGH` (between CRITICAL and WARNING)
  - [x] Add `pagerduty_severity` property to AlertSeverity enum
  - [x] Update `alerting.py` to use new severity mapping
  - [x] Update `state_machine.py` to use SPO2_CRITICAL and DISCONNECT
  - [x] Removed legacy SPO2_LOW and BLE_DISCONNECT (no backward compat needed)
- [x] Update `config.py` with alert config structure
  - [x] Add `TherapyModeConfig` dataclass (threshold, duration, enabled)
  - [x] Add `SleepHoursConfig` dataclass with `is_sleep_hours()` method
  - [x] Add config classes: `SpO2CriticalAlertConfig`, `SpO2WarningAlertConfig`, `HRAlertConfig`, `DisconnectAlertConfig`, `NoTherapyAtNightAlertConfig`, `BatteryAlertConfig`
  - [x] Add `AlertsConfig` container with all alert configs
  - [x] Add `alerts` field to main `Config` class
  - [x] Verified nested dataclass loading works correctly
  - [x] Added `alerts` section to config.yaml with all defaults

### 10.2 Alert Evaluation Logic
- [x] Create `alert_evaluator.py` module
  - [x] `AlertEvaluator` class with `evaluate()` method
  - [x] `_evaluate_spo2()` - check SpO2 thresholds (critical/warning)
  - [x] `_evaluate_hr()` - check HR thresholds (high/low)
  - [x] `_evaluate_disconnect()` - check disconnect escalation
  - [x] `_evaluate_battery()` - check battery thresholds
  - [x] `_evaluate_no_therapy_at_night()` - check sleep hours compliance
- [x] Track duration counters via `AlertConditionTracker` class
  - [x] Start/reset/duration_seconds methods for each condition
  - [x] Deduplication via `fired_alerts` dict with cooldown
- [x] Implement sleep hours logic
  - [x] `SleepHoursConfig.is_sleep_hours()` handles overnight ranges
  - [x] Escalate severity: info_minutes → warning_minutes
  - [x] Reset when therapy turns ON or sleep hours end
- [x] All conditions auto-clear when values recover

### 10.3 AlertManager Updates
- [x] Update `AlertManager` to use new alert types
- [x] Map severity to PagerDuty using `AlertSeverity.pagerduty_severity` property
  - [x] critical → "critical"
  - [x] high → "error"
  - [x] warning → "warning"
  - [x] info → "info"
- [x] Alert deduplication handled in AlertEvaluator via `AlertConditionTracker`

### 10.4 State Machine Integration
- [x] Import `AlertEvaluator` in state_machine.py
- [x] Create `AlertEvaluator` instance in `__init__`
- [x] Add `_evaluate_alerts()` method that calls evaluator
- [x] Call `_evaluate_alerts()` in evaluation cycle
- [x] Store triggered alerts to database
- [x] Route alerts to AlertManager based on severity

### 10.5 Configuration Updates
- [x] Update `config.yaml` with new alerts section
- [x] Add example values for all alert thresholds
- [x] Update `save_config()` to persist alerts section to YAML
- [-] Maintain backward compatibility with old threshold format (not needed)
- [x] Update `config.example.yaml` as template

### 10.6 Web Dashboard Updates
- [x] Update Settings page for new alert configuration
  - [x] SpO2 Critical thresholds (therapy on/off)
  - [x] SpO2 Warning thresholds
  - [x] HR High/Low thresholds
  - [x] Disconnect escalation times
  - [x] Battery thresholds
  - [x] No Therapy at Night (sleep hours, escalation times)
  - [x] Resend interval per alert type
- [x] Add therapy mode enable/disable toggles
- [x] Update API endpoints for new config structure
  - [x] GET /api/config returns alerts config
  - [x] PUT /api/config accepts and saves alerts config
- [ ] Update dashboard to show current therapy mode

### 10.7 Testing
- [ ] Unit tests for alert evaluator
- [ ] Test therapy ON vs OFF threshold differences
- [ ] Test disconnect escalation timing
- [ ] Test battery alerts
- [ ] Integration test with mock data

---

## Phase 11: Documentation & Training

### 11.1 Documentation
- [x] Update DESIGN.md with alerting design
- [ ] Create README.md with quick start
- [ ] Document configuration options
- [ ] Document API endpoints
- [ ] Create troubleshooting guide

### 11.2 Operational Runbooks
- [ ] Daily monitoring checklist
- [ ] Responding to SpO2 alarm
- [ ] Responding to BLE disconnect
- [ ] Responding to system down
- [ ] Restarting the service
- [ ] Updating the software

### 11.3 Family Training
- [ ] Dashboard walkthrough
- [ ] Alert response procedure
- [ ] Oximeter placement/charging
- [ ] Who to call for technical issues

---

## Phase 12: Multi-Adapter Bluetooth Failover ✅ (NEW)

### 12.1 Internal Bluetooth Disabled
- [x] Identified "Zombie Adapter" issue (internal BT interfering with USB adapters)
- [x] Added `dtoverlay=disable-bt` to `/boot/firmware/config.txt`
- [x] Verified internal adapter disabled after reboot

### 12.2 Dual Adapter Hardware Setup
- [x] Selected Insignia USB Bluetooth adapters (BlueZ compatible)
- [x] Configured Hallway adapter (on USB extension): MAC 10:A5:62:EC:E8:A5
- [x] Configured Bedroom adapter (direct USB): MAC 10:A5:62:79:03:8A
- [-] ASUS USB-BT500 tested but requires manual driver build (not used)

### 12.3 AdapterManager Implementation
- [x] Created `AdapterInfo` dataclass for adapter state
- [x] Created `AdapterManager` class in `ble_reader.py`
  - [x] `discover_adapters()` - runs hciconfig and matches to config
  - [x] `switch_to_next_adapter()` - brings up next adapter, brings down current
  - [x] `check_adapter_health()` - periodic availability check
- [x] Integrated with `CheckmeO2Reader`
  - [x] Switch after `switch_timeout_minutes` of no readings
  - [x] Bounce every `bounce_interval_minutes` when in switching mode
  - [x] Health check every 60 seconds

### 12.4 Configuration Updates
- [x] Added `BluetoothConfig` and `BluetoothAdapterConfig` dataclasses
- [x] Updated `config.yaml` with bluetooth section
- [x] Added settings fields: adapter names, read interval, late reading, switch timeout, bounce interval
- [x] API endpoints updated to save/load bluetooth config

### 12.5 Dashboard Updates
- [x] Added dual adapter status display in status grid
- [x] Adapter indicators: active (green), connecting (amber pulse), standby (blue), offline (gray)
- [x] Made vitals display larger (7rem) for visibility
- [x] Put units (%, bpm) inline with numbers

### 12.6 Settings Page Updates
- [x] Added Bluetooth & Timeouts section
- [x] Adapter name fields (editable)
- [x] Read interval, late reading threshold, switch timeout, bounce interval
- [x] All settings persist to config.yaml

### 12.7 Adapter Disconnect Alert
- [x] Added `adapter_disconnect` alert type to config.py
- [x] Added alert row in Settings page table
- [x] Warning severity, 60-minute resend interval
- [x] Fires when configured adapter not detected in hciconfig output

---

## Immediate Next Steps

Priority order for next development session:

### Completed Phases
- ~~**Phases 1-6**: Core infrastructure, device integration, database, alerting, state machine, web dashboard~~ [x] All Done
- ~~**Phase 8**: Deployment - systemd service, installation scripts~~ [x] All Done
- ~~**Phase 10**: Enhanced Alerting System with therapy-aware thresholds~~ [x] All Done
- ~~**Phase 12**: Multi-Adapter Bluetooth Failover~~ [x] All Done
- **Phase 13**: Android Relay App - Pi-side API (In Progress)

## Phase 13: Android Relay App (NEW)

Pi-side API for Android backup relay app. When dad moves out of BLE range of the Pi, the phone takes over reading the oximeter and relays data to the Pi over WiFi/VPN.

### Pi-Side (This Instance) - COMPLETE
- [x] Create relay API blueprint (`src/web/relay_api.py`)
- [x] `GET /api/relay/status` - Phone checks if Pi needs help
- [x] `POST /api/relay/reading` - Phone posts individual reading
- [x] `POST /api/relay/batch` - Phone flushes queued readings
- [x] `GET /api/relay/app-version` - Phone checks for updates
- [x] Add `source` column to readings table ('ble' vs 'relay')
- [x] Create `android/version.json` for app updates
- [ ] Implement Pi BLE backoff when receiving relay data (optional)

### Android-Side (Separate Instance)
See `android/DESIGN.md` and `android/TODO.md` for Android app implementation.

### API Notes for Android Developer
The implemented Pi API has minor field name differences from the original design:
- `seconds_since_reading` instead of `last_reading_age_seconds`
- `ble_connected` instead of `pi_ble_connected`
- `battery_level` instead of `battery`
- No `device_id` or `queued` fields (can be added if needed)

### Remaining Tasks
- [ ] Update dashboard to show current therapy mode indicator
- [ ] Unit tests for alert evaluator
- [ ] Simulated failure testing (unplug adapters, network errors)
- [ ] Family training on dashboard
- [ ] Document operational runbooks

### Completed Setup Tasks
- [x] User account created for web dashboard
- [x] PagerDuty configured (routing key in config.yaml)
- [x] Healthchecks.io configured (ping URL in config.yaml)
- [x] Kasa smart plug discovered (192.168.4.126)
- [x] Power thresholds tuned (on: 25.0W, off: 20.0W for actual BiPAP)
- [x] Internal Bluetooth disabled, dual USB adapters configured
- [x] systemd service installed and verified working

---

## Phase 14: Vision-Based Sleep Monitoring (NEW)

Vision service to detect when dad falls asleep without AVAPS mask. Runs on Windows PC with RTX 3060 GPU, provides API for Pi to poll.

**Alert Logic:** `IF face_detected AND is_dad AND eyes_closed > 5min AND no_mask → ALERT`

### 14.1 Core Infrastructure
- [x] Create `vision/` directory structure and `__init__.py` files
- [x] Implement `vision/config.py` with Pydantic Settings
- [x] Implement `vision/models/camera.py` (CameraState enum, Camera, DetectionResult, VisionStatus)

### 14.2 Detection Pipeline
- [x] Implement `vision/detection/face_recognition.py` (InsightFace/ArcFace wrapper)
- [x] Implement `vision/detection/eye_state.py` (MediaPipe Face Mesh + EAR calculation)
- [x] Implement `vision/detection/mask_detection.py` (YOLO wrapper with heuristic fallback)
- [x] Implement `vision/detection/pipeline.py` (DetectionPipeline orchestrator)

### 14.3 Camera Management
- [x] Implement `vision/capture/rtsp_stream.py` (OpenCV RTSP capture)
- [x] Implement `vision/capture/camera_manager.py` (state machine + scheduler)
  - [x] Camera states: IDLE (5 min) → ACTIVE (1 min) → ALERT (1 min)
  - [x] Staggered scheduling across cameras
  - [x] Dad detection triggers ACTIVE mode
  - [x] Eyes closed + no mask > 5 min triggers ALERT

### 14.4 FastAPI Service
- [x] Implement `vision/api/server.py` (FastAPI app factory with lifespan)
- [x] Implement API routes:
  - [x] `GET /health` - Health check
  - [x] `GET /status` - Overall status (Pi polls this)
  - [x] `GET /cameras` - List all cameras
  - [x] `POST /cameras` - Add camera
  - [x] `GET /cameras/{id}/status` - Single camera status
  - [x] `GET /cameras/{id}/snapshot` - Current frame as JPEG
  - [x] `PUT /cameras/{id}` - Update camera
  - [x] `DELETE /cameras/{id}` - Remove camera
  - [x] `POST /cameras/{id}/enable` - Enable camera
  - [x] `POST /cameras/{id}/disable` - Disable camera
  - [x] `POST /enroll` - Upload dad's face photos
  - [x] `POST /config` - Update thresholds

### 14.5 Entry Point and Dependencies
- [x] Implement `vision/main.py` (service entry point)
- [x] Create `vision/requirements.txt` with pinned dependencies
- [x] Create `vision/data/.gitkeep` and update `.gitignore`

### 14.6 Pi Integration
- [x] Implement `src/vision_client.py` (async client for Pi to poll vision service)
- [x] Update `src/models.py` with `VISION_SLEEP_NO_MASK` alert type
- [x] Add vision alert config to `config.yaml`

### 14.7 Documentation
- [x] Create `VISION.md` design document with:
  - [x] Architecture overview
  - [x] Camera state machine diagram
  - [x] API endpoint documentation
  - [x] Detection pipeline details
  - [x] Configuration reference
  - [x] Deployment instructions
  - [x] Troubleshooting guide
- [x] Update `README.md` with vision service section
- [x] Update `.env.example` with vision config vars

### 14.8 Testing
- [H] Test vision service startup and health endpoint (requires Windows PC with GPU)
- [H] Test RTSP capture from Reolink cameras (requires cameras on network)
- [H] Test face enrollment and recognition (requires GPU dependencies)
- [H] Test eye state detection (EAR calculation) (requires GPU dependencies)
- [H] Test camera state transitions (requires full setup)
- [H] Test Pi client polling `/status` (requires running vision service)
- [H] End-to-end: alert triggers when eyes closed + no mask > 5 min (requires full setup)

### Hardware
- **Cameras:** TP-Link Tapo C210 (WiFi, native RTSP: `rtsp://user:pass@ip:554/stream1`)
  - Note: Reolink E1 Pro does NOT have standalone RTSP - requires hub/NVR
- **Compute:** Windows 11 PC, RTX 3060 12GB (GPU 0), Python 3.10

### Configuration Defaults
```yaml
# Detection thresholds
eyes_closed_alert_seconds: 300    # 5 min
dad_gone_timeout_seconds: 600     # 10 min
face_similarity_threshold: 0.6
ear_closed_threshold: 0.2

# Polling intervals
idle_poll_seconds: 300            # 5 min
active_poll_seconds: 60           # 1 min

# Server
api_host: 0.0.0.0
api_port: 8100
```

### Key Dependencies
- fastapi, uvicorn (web framework)
- opencv-python (RTSP capture)
- insightface, onnxruntime-gpu (face recognition)
- mediapipe (eye landmarks)
- ultralytics (YOLO mask detection)
- torch+cu121 (GPU compute)

---

## Notes

- Device MAC: `C8:F1:6B:56:7B:F1`
- Kasa Smart Plug IP: `192.168.4.126`
- BLE library: BLE-GATT (not bleak/bluepy)
- Device must be "trusted" not "paired" in bluetoothctl
- Virtual env needs `--system-site-packages` for GLib
- Working test script: `test_working.py`
- **Bluetooth adapters:**
  - Internal Pi Bluetooth: DISABLED (`dtoverlay=disable-bt`)
  - Hallway adapter: Insignia USB, MAC 10:A5:62:EC:E8:A5
  - Bedroom adapter: Insignia USB, MAC 10:A5:62:79:03:8A
- **vext workaround**: vext.gi blocks system packages. Had to install `cffi==1.17.1` and `cryptography==42.0.8` with `--only-binary :all:` to get prebuilt ARM wheels
- **pip upgrade**: Upgraded pip to 25.3 (old 20.3.4 had TOML parsing bugs)
- **BLE command 0x17**: Returns current real-time reading only (not stored data)
- **Trend analysis important**: Gradual SpO2 decline (94→93→92→91→90) more clinically significant than sudden drop (97→82 = likely sensor artifact)
- **Flask caching**: Always restart app after modifying web files
- **GitHub repo**: https://github.com/dmattox-sparkcodelabs/02Monitor

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

---

### Session 2026-01-12 - Kasa Integration & Alerting Design
- Discovered Kasa smart plug at 192.168.50.10 (config had wrong IP)
- Tuned AVAPS power thresholds: on_watts=5.0, off_watts=4.0 (tested with CPAP)
- Changed BLE read interval from 10s to 5s for faster response
- Changed late reading threshold from 15s to 30s to reduce false warnings
- Set up GitHub repository and pushed code
- Configured PagerDuty (routing key) and Healthchecks.io (ping URL)
- Fixed Settings page to show PagerDuty/Healthchecks values
- Fixed test alert to use `trigger_alarm()` instead of `trigger_local_only()`
- Removed unnecessary "Configured/Not Configured" indicators from Settings
- Added Test Alert button to Settings page
- **Designed therapy-aware multi-severity alerting system:**
  - Different thresholds for therapy ON (night) vs OFF (day)
  - Alert types: spo2_critical, spo2_warning, hr_high, hr_low, disconnect, battery
  - Severity levels: critical, high, warning, info
  - Disconnect alerts escalate over time (info → warning → high)
  - All configurable via config.yaml without code changes
- Updated DESIGN.md with new alerting design
- Added Phase 10 to TODO.md with implementation plan

**Completed**: Installed libsdl2-mixer-2.0-0 and espeak for audio alerts

---

### Session 2026-01-12 Afternoon - Enhanced Alerting Implementation
- Implemented Phase 10 therapy-aware alerting system:
  - **models.py**: Added new AlertType enums (SPO2_CRITICAL, SPO2_WARNING, HR_HIGH, HR_LOW, DISCONNECT, NO_THERAPY_AT_NIGHT, BATTERY_WARNING, BATTERY_CRITICAL), added HIGH severity, removed legacy SPO2_LOW and BLE_DISCONNECT
  - **config.py**: Added TherapyModeConfig, SleepHoursConfig (with is_sleep_hours() for overnight ranges), and all alert config dataclasses. Updated save_config() to persist alerts section.
  - **alert_evaluator.py**: New module with AlertConditionTracker for duration tracking and AlertEvaluator for threshold evaluation with deduplication
  - **state_machine.py**: Integrated AlertEvaluator, added _evaluate_alerts() method
  - **alerting.py**: Updated severity mapping to use pagerduty_severity property
- Updated Settings page (settings.html, settings.js) with all new alert configuration fields:
  - SpO2 Critical/Warning with therapy ON/OFF thresholds
  - HR High/Low thresholds
  - Disconnect alert escalation times
  - No Therapy at Night with sleep hours and escalation
  - Battery warning/critical thresholds
- Updated API endpoints (api.py):
  - GET /api/config now returns full alerts config structure
  - PUT /api/config now accepts and saves alerts config
- Tested config save/load cycle - all fields persist correctly

---

### Session 2026-01-12 Evening - Settings Table & Audio Alerts
- Refactored Settings page to use table format for all alerts
- Created unified AlertItemConfig pattern: enabled, threshold, duration, severity, bypass_on_therapy
- Split SpO2 Critical into two alerts:
  - **SpO2 Critical (Off Therapy)**: 90% threshold, 30s duration
  - **SpO2 Critical (On Therapy)**: 85% threshold, 120s duration (more lenient during AVAPS)
- Split No Therapy at Night into two escalation levels:
  - **No Therapy at Night (Info)**: 30 min, info severity
  - **No Therapy at Night (Urgent)**: 60 min, high severity
- Fixed table CSS for better layout (no more wrapping units)
- Created start.sh and stop.sh scripts for easier app management
- **Implemented audio alerts with programmatic tone generation:**
  - No external sound files needed - tones generated using pygame + pure Python
  - Different tone patterns per severity:
    - Critical: Fast triple beeps at 880 Hz
    - High: Double beeps at 660 Hz
    - Warning: Slower single beeps at 440 Hz
    - Info: Low single tone at 330 Hz
  - Installed espeak for TTS
  - Alert messages spoken: "Warning! Oxygen level critical at 85 percent."
  - Critical/High alerts repeat (tones + TTS) every 30 seconds until resolved
- Installed libsdl2-mixer-2.0-0 for pygame audio support
- Updated config.py, alert_evaluator.py, api.py, settings.js for new alert structure

---

### Session 2026-01-12 Night - Bug Fixes & Maintenance
- **Fixed dashboard chart timezone issue:**
  - API was using `time.daylight` to check DST, but this only indicates if DST is defined, not if it's active
  - In January (CST, UTC-6), code was incorrectly using CDT offset (UTC-5), causing 1-hour shift
  - Fixed to use `time.localtime().tm_gmtoff` for correct current offset
- **Increased chart data limits:**
  - Dashboard: 2000/8000/30000 for 1hr/6hr/24hr views
  - History page: 200000 to support 30 days of data retention
  - API max limit increased from 5000 to 200000
- **Added daily database cleanup:**
  - Runs automatically every 24 hours via state machine
  - Deletes readings >30 days, alerts >365 days, events >90 days
- **Fixed history page layout:**
  - Added CSS for date controls and stats grid
  - Fixed readings table to show newest first
- **Fixed page centering:**
  - Settings page now centered with max-width 900px
  - Login page uses flex column layout for proper centering
  - Flash messages display above login box correctly

---

### Session 2026-01-13/14 - Bluetooth Adapter Issues & Multi-Adapter Failover

**Problem Identified:**
- BLE connections were failing after Pi 5 to Pi 4 migration
- Root cause: "Zombie Adapter" problem where internal Bluetooth (hci0) was interfering with USB adapters
- BlueZ prioritizes hci0 even when it's not the desired adapter

**Solution Implemented:**
1. **Disabled internal Bluetooth:**
   - Added `dtoverlay=disable-bt` to `/boot/firmware/config.txt`
   - Verified disabled after reboot

2. **Selected working USB adapters:**
   - ASUS USB-BT500 tested but requires manual driver build (kernel headers, make)
   - Insignia USB Bluetooth adapters work out of the box with BlueZ
   - Chose two Insignia adapters: Hallway (USB extension) and Bedroom (direct)

3. **Implemented multi-adapter failover:**
   - Created `AdapterManager` class to manage multiple adapters
   - Automatic switching after 5 minutes of no readings
   - "Bounce mode" cycles through adapters every 1 minute when in switching mode
   - Health checks every 60 seconds via `hciconfig -a`

4. **Dashboard updates:**
   - Added dual adapter status display with colored indicators
   - Active=green, Connecting=amber (pulsing), Standby=blue, Offline=gray
   - Made vitals display larger (7rem) for dad's visibility
   - Put units inline with numbers (96% instead of 96 / %)

5. **Settings page updates:**
   - Added Bluetooth & Timeouts section
   - Editable adapter names
   - Configurable timeouts: read interval, late reading, switch timeout, bounce interval

6. **New alert type:**
   - Added `adapter_disconnect` alert (warning severity)
   - Fires when a configured Bluetooth adapter is not detected
   - 60-minute resend interval

7. **Resend intervals:**
   - Added `resend_interval_seconds` to all alert types
   - Prevents alert fatigue from repeated notifications
   - Configurable per alert type in Settings

**Files Modified:**
- `src/ble_reader.py` - AdapterManager class and switching logic
- `src/config.py` - BluetoothConfig, BluetoothAdapterConfig, adapter_disconnect alert
- `config.yaml` - bluetooth section with adapter definitions
- `src/web/api.py` - /api/adapters endpoint, config save/load
- `src/web/templates/dashboard.html` - adapter status display
- `src/web/templates/settings.html` - Bluetooth & Timeouts section
- `src/web/static/css/style.css` - adapter indicator styles
- `src/web/static/js/dashboard.js` - adapter status fetching
- `src/web/static/js/settings.js` - bluetooth settings handling

**Cleanup:**
- Removed stray files: `cat`, `echo`, `on`, `New power settings:`, `test_asus.py`
- Removed ASUS driver downloads from ~/Downloads

*Last Updated: 2026-01-14*
