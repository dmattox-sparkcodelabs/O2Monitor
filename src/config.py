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
    on_watts: float = 3.0
    off_watts: float = 2.0


@dataclass
class BLEThresholdConfig:
    """BLE connection thresholds."""
    reconnect_alert_minutes: int = 3
    max_reconnect_attempts: Optional[int] = None


@dataclass
class ThresholdsConfig:
    """Threshold configuration container."""
    spo2: SpO2ThresholdConfig = field(default_factory=SpO2ThresholdConfig)
    avaps: AVAPSThresholdConfig = field(default_factory=AVAPSThresholdConfig)
    ble: BLEThresholdConfig = field(default_factory=BLEThresholdConfig)


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
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
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

        # Handle Optional types
        elif hasattr(field_type, '__origin__') and field_type.__origin__ is type(None):
            kwargs[field_name] = value

        else:
            kwargs[field_name] = value

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
        errors.append("thresholds.spo2.alarm_level must be 0-100")

    if config.thresholds.spo2.alarm_duration_seconds < 0:
        errors.append("thresholds.spo2.alarm_duration_seconds must be positive")

    if config.thresholds.avaps.on_watts <= config.thresholds.avaps.off_watts:
        errors.append("thresholds.avaps.on_watts must be greater than off_watts")

    # Validate audio volume
    if config.alerting.local_audio.volume < 0 or config.alerting.local_audio.volume > 100:
        errors.append("alerting.local_audio.volume must be 0-100")

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
        'off_watts': config.thresholds.avaps.off_watts,
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

    # Write back
    with open(config_file, 'w') as f:
        yaml.dump(existing, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Configuration saved to {config_path}")
