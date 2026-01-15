# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Configuration loader for O2 Monitor.

Loads configuration from YAML file with environment variable substitution.
"""

import os
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Default config file locations (in order of priority)
CONFIG_PATHS = [
    "config.local.yaml",  # Local overrides (not in git)
    "config.yaml",        # Default config
]


@dataclass
class OximeterConfig:
    """Oximeter device configuration."""
    mac_address: str = ""
    name: str = "Checkme O2 Max"
    read_interval_seconds: int = 10


@dataclass
class SmartPlugConfig:
    """Smart plug configuration."""
    ip_address: str = ""
    name: str = "AVAPS Power Monitor"


@dataclass
class DevicesConfig:
    """Device configuration container."""
    oximeter: OximeterConfig = field(default_factory=OximeterConfig)
    smart_plug: SmartPlugConfig = field(default_factory=SmartPlugConfig)


@dataclass
class SpO2ThresholdConfig:
    """SpO2 monitoring thresholds."""
    alarm_level: int = 90
    alarm_duration_seconds: int = 30
    warning_level: int = 92


@dataclass
class AVAPSThresholdConfig:
    """AVAPS power thresholds."""
    on_watts: float = 30.0
    window_minutes: int = 5


@dataclass
class BLEThresholdConfig:
    """BLE connection thresholds."""
    reconnect_alert_minutes: int = 3
    max_reconnect_attempts: Optional[int] = None


@dataclass
class BluetoothAdapterConfig:
    """Configuration for a single Bluetooth adapter."""
    name: str = ""
    mac_address: str = ""


@dataclass
class BluetoothConfig:
    """Bluetooth adapter and timing configuration."""
    # Adapter definitions
    adapters: List[BluetoothAdapterConfig] = field(default_factory=list)
    # How often to poll for readings (seconds)
    read_interval_seconds: int = 5
    # Reading is "late" after this many seconds
    late_reading_seconds: int = 30
    # Switch to other adapter after this many minutes of no readings
    switch_timeout_minutes: int = 5
    # When in switching mode, try other adapter every X minutes
    bounce_interval_minutes: int = 1
    # Delay before respawning worker when device not found (seconds)
    respawn_delay_seconds: int = 15
    # Restart Bluetooth service after this many minutes of consecutive failures (0 = disabled)
    bt_restart_threshold_minutes: int = 5


@dataclass
class ThresholdsConfig:
    """Threshold configuration container (legacy - see AlertsConfig for new system)."""
    spo2: SpO2ThresholdConfig = field(default_factory=SpO2ThresholdConfig)
    avaps: AVAPSThresholdConfig = field(default_factory=AVAPSThresholdConfig)
    ble: BLEThresholdConfig = field(default_factory=BLEThresholdConfig)


# ==================== Unified Alert Configuration System ====================

@dataclass
class SleepHoursConfig:
    """Configuration for sleep hours.

    Attributes:
        start: Start time in HH:MM format (24-hour)
        end: End time in HH:MM format (24-hour)
    """
    start: str = "22:00"
    end: str = "07:00"

    def is_sleep_hours(self, hour: int, minute: int = 0) -> bool:
        """Check if a given time is within sleep hours.

        Handles overnight ranges (e.g., 22:00-07:00).
        """
        start_parts = self.start.split(":")
        end_parts = self.end.split(":")
        start_hour = int(start_parts[0])
        start_min = int(start_parts[1]) if len(start_parts) > 1 else 0
        end_hour = int(end_parts[0])
        end_min = int(end_parts[1]) if len(end_parts) > 1 else 0

        current = hour * 60 + minute
        start = start_hour * 60 + start_min
        end = end_hour * 60 + end_min

        if start <= end:
            # Same day range (e.g., 09:00-17:00)
            return start <= current < end
        else:
            # Overnight range (e.g., 22:00-07:00)
            return current >= start or current < end


@dataclass
class AlertItemConfig:
    """Unified configuration for a single alert type.

    All alerts follow the same pattern for consistency.

    Attributes:
        enabled: Whether this alert is active
        threshold: The threshold value (meaning depends on alert type)
        duration_seconds: How long condition must persist before alerting
        severity: Alert severity level (critical, high, warning, info)
        bypass_on_therapy: Skip this alert when AVAPS therapy is active
        resend_interval_seconds: Cooldown before re-sending the same alert (default 5 min)
    """
    enabled: bool = True
    threshold: int = 0
    duration_seconds: int = 30
    severity: str = "warning"
    bypass_on_therapy: bool = False
    resend_interval_seconds: int = 300  # Default 5 minutes


@dataclass
class AlertsConfig:
    """Container for all alert configurations.

    Each alert follows a unified pattern with:
    - enabled: on/off toggle
    - threshold: value that triggers the alert
    - duration_seconds: how long condition must persist
    - severity: critical/high/warning/info
    - bypass_on_therapy: skip during AVAPS therapy
    """
    # SpO2 alerts - separate thresholds for on/off therapy
    spo2_critical_off_therapy: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=90, duration_seconds=30,
        severity="critical", bypass_on_therapy=False  # N/A - only applies off therapy
    ))
    spo2_critical_on_therapy: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=85, duration_seconds=120,
        severity="critical", bypass_on_therapy=False  # N/A - only applies on therapy
    ))
    spo2_warning: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=92, duration_seconds=60,
        severity="warning", bypass_on_therapy=True
    ))
    hr_high: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=120, duration_seconds=60,
        severity="high", bypass_on_therapy=True
    ))
    hr_low: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=50, duration_seconds=60,
        severity="high", bypass_on_therapy=True
    ))
    disconnect: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=120, duration_seconds=0,  # threshold is minutes
        severity="warning", bypass_on_therapy=True
    ))
    # No therapy at night - two levels for escalation
    no_therapy_at_night_info: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=30, duration_seconds=0,  # threshold is minutes into sleep
        severity="info", bypass_on_therapy=False  # N/A - only fires when therapy is OFF
    ))
    no_therapy_at_night_high: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=60, duration_seconds=0,  # threshold is minutes into sleep
        severity="high", bypass_on_therapy=False  # N/A - only fires when therapy is OFF
    ))
    battery_warning: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=25, duration_seconds=0,
        severity="warning", bypass_on_therapy=False
    ))
    battery_critical: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=10, duration_seconds=0,
        severity="critical", bypass_on_therapy=False
    ))
    # Adapter disconnect - fires when a Bluetooth adapter is unplugged
    adapter_disconnect: AlertItemConfig = field(default_factory=lambda: AlertItemConfig(
        enabled=True, threshold=0, duration_seconds=0,
        severity="warning", bypass_on_therapy=False, resend_interval_seconds=3600
    ))
    # Sleep hours for no_therapy_at_night alerts
    sleep_hours: SleepHoursConfig = field(default_factory=SleepHoursConfig)


@dataclass
class PagerDutyConfig:
    """PagerDuty alerting configuration."""
    enabled: bool = True
    routing_key: str = ""
    service_name: str = "O2 Monitor"


@dataclass
class LocalAudioConfig:
    """Local audio alerting configuration."""
    enabled: bool = True
    alarm_sound: str = "sounds/alarm.wav"
    volume: int = 90
    use_tts: bool = True
    tts_message: str = "Medical alert. Check on Dad immediately."
    repeat_interval_seconds: int = 30


@dataclass
class AlexaConfig:
    """Alexa alerting configuration."""
    enabled: bool = False
    notify_me_access_code: str = ""


@dataclass
class HealthchecksConfig:
    """Healthchecks.io configuration."""
    enabled: bool = True
    ping_url: str = ""
    interval_seconds: int = 60


@dataclass
class AlertingConfig:
    """Alerting configuration container."""
    pagerduty: PagerDutyConfig = field(default_factory=PagerDutyConfig)
    local_audio: LocalAudioConfig = field(default_factory=LocalAudioConfig)
    alexa: AlexaConfig = field(default_factory=AlexaConfig)
    healthchecks: HealthchecksConfig = field(default_factory=HealthchecksConfig)


@dataclass
class MessagesConfig:
    """Alert message templates."""
    spo2_alarm: str = "Medical alert! Oxygen level critical. Check on Dad immediately."
    ble_disconnect: str = "O2 monitor disconnected. Please check the device."
    system_error: str = "O2 monitoring system error. Requires attention."


@dataclass
class WebConfig:
    """Web dashboard configuration."""
    host: str = "0.0.0.0"
    port: int = 5000
    secret_key: str = ""
    debug: bool = False


@dataclass
class UserConfig:
    """User account configuration."""
    username: str = ""
    password_hash: str = ""


@dataclass
class AuthConfig:
    """Authentication configuration."""
    session_timeout_minutes: int = 30
    max_login_attempts: int = 5
    lockout_minutes: int = 15
    users: List[UserConfig] = field(default_factory=list)


@dataclass
class RetentionConfig:
    """Data retention configuration."""
    readings_days: int = 30
    alerts_days: int = 365
    events_days: int = 90


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = "data/history.db"
    retention: RetentionConfig = field(default_factory=RetentionConfig)


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = "logs/o2monitor.log"
    max_size_mb: int = 10
    backup_count: int = 5


@dataclass
class Config:
    """Main configuration container.

    This is the root configuration object containing all settings.
    """
    mock_mode: bool = False
    devices: DevicesConfig = field(default_factory=DevicesConfig)
    bluetooth: BluetoothConfig = field(default_factory=BluetoothConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    alerting: AlertingConfig = field(default_factory=AlertingConfig)
    messages: MessagesConfig = field(default_factory=MessagesConfig)
    web: WebConfig = field(default_factory=WebConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Internal: base path for resolving relative paths
    _base_path: Path = field(default_factory=Path.cwd)

    def resolve_path(self, path: str) -> Path:
        """Resolve a path relative to the config file location."""
        p = Path(path)
        if p.is_absolute():
            return p
        return self._base_path / p


def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${VAR} patterns with environment variables.

    Args:
        value: Value to process (can be str, dict, list, or other)

    Returns:
        Value with environment variables substituted
    """
    if isinstance(value, str):
        # Pattern matches ${VAR_NAME}
        pattern = r'\$\{([^}]+)\}'

        def replace_env(match):
            var_name = match.group(1)
            env_value = os.environ.get(var_name, "")
            if not env_value:
                logger.warning(f"Environment variable {var_name} not set")
            return env_value

        return re.sub(pattern, replace_env, value)

    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}

    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]

    return value


def _dict_to_dataclass(cls, data: Dict[str, Any]):
    """Convert a dictionary to a dataclass, handling nested structures.

    Args:
        cls: The dataclass type to create
        data: Dictionary of values

    Returns:
        Instance of cls populated with data
    """
    if data is None:
        return cls()

    # Get field types from dataclass
    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}

    kwargs = {}
    for field_name, field_type in field_types.items():
        if field_name.startswith('_'):
            continue

        if field_name not in data:
            continue

        value = data[field_name]

        # Handle nested dataclasses
        if hasattr(field_type, '__dataclass_fields__'):
            kwargs[field_name] = _dict_to_dataclass(field_type, value)

        # Handle List[UserConfig] special case
        elif field_name == 'users' and isinstance(value, list):
            kwargs[field_name] = [
                _dict_to_dataclass(UserConfig, u) if isinstance(u, dict) else u
                for u in value
            ]

        # Handle List[BluetoothAdapterConfig] special case
        elif field_name == 'adapters' and isinstance(value, list):
            kwargs[field_name] = [
                _dict_to_dataclass(BluetoothAdapterConfig, a) if isinstance(a, dict) else a
                for a in value
            ]

        # Handle Optional types
        elif hasattr(field_type, '__origin__') and field_type.__origin__ is type(None):
            kwargs[field_name] = value

        else:
            kwargs[field_name] = value

    # Special handling for AlertsConfig - convert alert items
    if cls == AlertsConfig and data:
        alert_fields = ['spo2_critical_off_therapy', 'spo2_critical_on_therapy', 'spo2_warning',
                        'hr_high', 'hr_low', 'disconnect',
                        'no_therapy_at_night_info', 'no_therapy_at_night_high',
                        'battery_warning', 'battery_critical', 'adapter_disconnect']
        for alert_name in alert_fields:
            if alert_name in data and isinstance(data[alert_name], dict):
                kwargs[alert_name] = _dict_to_dataclass(AlertItemConfig, data[alert_name])
        if 'sleep_hours' in data and isinstance(data['sleep_hours'], dict):
            kwargs['sleep_hours'] = _dict_to_dataclass(SleepHoursConfig, data['sleep_hours'])

    return cls(**kwargs)


def load_config(config_path: Optional[str] = None, base_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file. If None, searches default locations.
        base_path: Base path for resolving relative paths. Defaults to cwd.

    Returns:
        Config object with all settings loaded

    Raises:
        FileNotFoundError: If no config file is found
        yaml.YAMLError: If config file is invalid YAML
    """
    # Load .env file if present
    env_path = Path(base_path or Path.cwd()) / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.debug(f"Loaded environment from {env_path}")

    # Also check MOCK_HARDWARE env var
    if os.environ.get("MOCK_HARDWARE", "").lower() in ("true", "1", "yes"):
        logger.info("MOCK_HARDWARE environment variable set - enabling mock mode")

    # Find config file
    if config_path:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
    else:
        base = base_path or Path.cwd()
        config_file = None
        for path in CONFIG_PATHS:
            candidate = base / path
            if candidate.exists():
                config_file = candidate
                break

        if config_file is None:
            raise FileNotFoundError(
                f"No config file found. Searched: {', '.join(CONFIG_PATHS)}"
            )

    logger.info(f"Loading config from {config_file}")

    # Load YAML
    with open(config_file, 'r') as f:
        raw_config = yaml.safe_load(f)

    if raw_config is None:
        raw_config = {}

    # Substitute environment variables
    config_data = _substitute_env_vars(raw_config)

    # Check for MOCK_HARDWARE env var override
    if os.environ.get("MOCK_HARDWARE", "").lower() in ("true", "1", "yes"):
        config_data["mock_mode"] = True

    # Convert to Config dataclass
    config = _dict_to_dataclass(Config, config_data)
    config._base_path = config_file.parent

    # Validate required settings
    _validate_config(config)

    return config


def _validate_config(config: Config) -> None:
    """Validate configuration settings.

    Args:
        config: Config object to validate

    Raises:
        ValueError: If required settings are missing or invalid
    """
    errors = []

    # Check oximeter MAC if not in mock mode
    if not config.mock_mode and not config.devices.oximeter.mac_address:
        errors.append("devices.oximeter.mac_address is required (or enable mock_mode)")

    # Check web secret key
    if not config.web.secret_key:
        logger.warning("web.secret_key not set - sessions will not persist across restarts")

    # Validate thresholds
    if config.thresholds.spo2.alarm_level < 0 or config.thresholds.spo2.alarm_level > 100:
        logger.warning("thresholds.spo2.alarm_level must be 0-100, clamping to valid range")
        config.thresholds.spo2.alarm_level = max(0, min(100, config.thresholds.spo2.alarm_level))

    if config.thresholds.spo2.alarm_duration_seconds < 0:
        logger.warning("thresholds.spo2.alarm_duration_seconds must be positive, using 0")
        config.thresholds.spo2.alarm_duration_seconds = 0

    if config.thresholds.avaps.window_minutes < 1:
        logger.warning("thresholds.avaps.window_minutes must be at least 1, using 1")
        config.thresholds.avaps.window_minutes = 1

    # Validate audio volume
    if config.alerting.local_audio.volume < 0 or config.alerting.local_audio.volume > 100:
        logger.warning("alerting.local_audio.volume must be 0-100, clamping to valid range")
        config.alerting.local_audio.volume = max(0, min(100, config.alerting.local_audio.volume))

    # Only fail on critical errors (missing required hardware config when not in mock mode)
    if errors:
        raise ValueError("Configuration errors:\n  " + "\n  ".join(errors))


def get_default_config() -> Config:
    """Get a Config object with all default values.

    Useful for testing or when no config file exists.

    Returns:
        Config with default values
    """
    return Config()


def save_config(config: Config, config_path: str = "config.yaml") -> None:
    """Save configuration changes back to YAML file.

    Reads the existing file to preserve comments and structure,
    then updates only the changed values.

    Args:
        config: Config object with current settings
        config_path: Path to config file to update
    """
    config_file = Path(config_path)

    # Read existing file to preserve comments
    if config_file.exists():
        with open(config_file, 'r') as f:
            existing = yaml.safe_load(f) or {}
    else:
        existing = {}

    # Update values from config object
    existing['thresholds'] = existing.get('thresholds', {})
    existing['thresholds']['spo2'] = {
        'alarm_level': config.thresholds.spo2.alarm_level,
        'alarm_duration_seconds': config.thresholds.spo2.alarm_duration_seconds,
        'warning_level': config.thresholds.spo2.warning_level,
    }
    existing['thresholds']['avaps'] = {
        'on_watts': config.thresholds.avaps.on_watts,
        'window_minutes': config.thresholds.avaps.window_minutes,
    }

    # Save alerts configuration (unified format)
    def _save_alert_item(alert_cfg):
        return {
            'enabled': alert_cfg.enabled,
            'threshold': alert_cfg.threshold,
            'duration_seconds': alert_cfg.duration_seconds,
            'severity': alert_cfg.severity,
            'bypass_on_therapy': alert_cfg.bypass_on_therapy,
            'resend_interval_seconds': alert_cfg.resend_interval_seconds,
        }

    existing['alerts'] = {
        'spo2_critical_off_therapy': _save_alert_item(config.alerts.spo2_critical_off_therapy),
        'spo2_critical_on_therapy': _save_alert_item(config.alerts.spo2_critical_on_therapy),
        'spo2_warning': _save_alert_item(config.alerts.spo2_warning),
        'hr_high': _save_alert_item(config.alerts.hr_high),
        'hr_low': _save_alert_item(config.alerts.hr_low),
        'disconnect': _save_alert_item(config.alerts.disconnect),
        'no_therapy_at_night_info': _save_alert_item(config.alerts.no_therapy_at_night_info),
        'no_therapy_at_night_high': _save_alert_item(config.alerts.no_therapy_at_night_high),
        'battery_warning': _save_alert_item(config.alerts.battery_warning),
        'battery_critical': _save_alert_item(config.alerts.battery_critical),
        'adapter_disconnect': _save_alert_item(config.alerts.adapter_disconnect),
        'sleep_hours': {
            'start': config.alerts.sleep_hours.start,
            'end': config.alerts.sleep_hours.end,
        },
    }

    existing['alerting'] = existing.get('alerting', {})
    existing['alerting']['local_audio'] = existing['alerting'].get('local_audio', {})
    existing['alerting']['local_audio']['volume'] = config.alerting.local_audio.volume

    # Only save routing_key/ping_url if they're not env var placeholders
    if config.alerting.pagerduty.routing_key and not config.alerting.pagerduty.routing_key.startswith('${'):
        existing['alerting']['pagerduty'] = existing['alerting'].get('pagerduty', {})
        existing['alerting']['pagerduty']['routing_key'] = config.alerting.pagerduty.routing_key

    if config.alerting.healthchecks.ping_url and not config.alerting.healthchecks.ping_url.startswith('${'):
        existing['alerting']['healthchecks'] = existing['alerting'].get('healthchecks', {})
        existing['alerting']['healthchecks']['ping_url'] = config.alerting.healthchecks.ping_url

    existing['devices'] = existing.get('devices', {})
    existing['devices']['smart_plug'] = existing['devices'].get('smart_plug', {})
    existing['devices']['smart_plug']['ip_address'] = config.devices.smart_plug.ip_address

    # Save bluetooth configuration
    existing['bluetooth'] = {
        'adapters': [
            {'name': a.name, 'mac_address': a.mac_address}
            for a in config.bluetooth.adapters
        ],
        'read_interval_seconds': config.bluetooth.read_interval_seconds,
        'late_reading_seconds': config.bluetooth.late_reading_seconds,
        'switch_timeout_minutes': config.bluetooth.switch_timeout_minutes,
        'bounce_interval_minutes': config.bluetooth.bounce_interval_minutes,
        'respawn_delay_seconds': config.bluetooth.respawn_delay_seconds,
        'bt_restart_threshold_minutes': config.bluetooth.bt_restart_threshold_minutes,
    }

    # Write back
    with open(config_file, 'w') as f:
        yaml.dump(existing, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Configuration saved to {config_path}")
