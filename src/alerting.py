# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Alerting system for O2 Monitor.

This module handles all alert delivery mechanisms:
- Local audio alarms via pygame (with generated tones)
- Text-to-speech announcements via espeak
- PagerDuty incident management
- Healthchecks.io heartbeat monitoring
- Alert silencing and deduplication

Usage:
    from src.alerting import AlertManager
    from src.models import Alert, AlertType, AlertSeverity

    manager = AlertManager(config)
    await manager.initialize()
    await manager.trigger_alarm(alert)
    await manager.close()
"""

import asyncio
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

# Add project root to path when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp

from src.models import Alert, AlertSeverity, AlertType, AVAPSState

logger = logging.getLogger(__name__)

# Try to import pygame for audio
try:
    import pygame
    import array
    import math
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logger.warning("pygame not available - audio alerts disabled")

# Check for espeak
ESPEAK_AVAILABLE = os.path.exists("/usr/bin/espeak") or os.path.exists("/usr/bin/espeak-ng")


class AudioAlert:
    """Local audio alerting via pygame with generated tones and TTS.

    Handles playing alarm sounds through the Raspberry Pi audio output.
    Generates alarm tones programmatically - no external sound files needed.
    Supports TTS announcements via espeak.
    """

    # Tone configurations for different severities
    TONE_CONFIGS = {
        'critical': {
            'frequency': 880,      # High A note
            'duration_ms': 200,    # Short beeps
            'pause_ms': 100,       # Quick pause between beeps
            'pattern': [1, 1, 1, 0, 1, 1, 1],  # Fast triple-beep pattern
        },
        'high': {
            'frequency': 660,      # E note
            'duration_ms': 400,    # Medium beeps
            'pause_ms': 200,       # Medium pause
            'pattern': [1, 1, 0, 1, 1],  # Double-beep pattern
        },
        'warning': {
            'frequency': 440,      # A note
            'duration_ms': 500,    # Longer beeps
            'pause_ms': 500,       # Longer pause
            'pattern': [1, 0, 1],  # Single beeps
        },
        'info': {
            'frequency': 330,      # E note (lower)
            'duration_ms': 300,
            'pause_ms': 700,
            'pattern': [1],        # Single tone
        },
    }

    def __init__(
        self,
        volume: int = 90,
        use_tts: bool = True,
    ):
        """Initialize audio alerting.

        Args:
            volume: Default volume (0-100)
            use_tts: Whether to use text-to-speech
        """
        self._volume = volume / 100.0
        self._use_tts = use_tts and ESPEAK_AVAILABLE
        self._initialized = False
        self._alarm_playing = False
        self._alarm_task: Optional[asyncio.Task] = None
        self._current_severity: str = "warning"
        self._current_message: str = ""
        self._generated_sounds: Dict[str, pygame.mixer.Sound] = {}

    async def initialize(self) -> bool:
        """Initialize pygame mixer and generate alarm tones.

        Returns:
            True if initialization successful
        """
        if not PYGAME_AVAILABLE:
            logger.warning("Cannot initialize audio - pygame not available")
            return False

        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            self._initialized = True

            # Pre-generate alarm tones for each severity
            for severity, config in self.TONE_CONFIGS.items():
                self._generated_sounds[severity] = self._generate_tone(
                    config['frequency'],
                    config['duration_ms']
                )

            logger.info("Audio alerting initialized")
            if self._use_tts:
                logger.info("TTS enabled (espeak)")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize pygame mixer: {e}")
            return False

    def _generate_tone(self, frequency: int, duration_ms: int) -> 'pygame.mixer.Sound':
        """Generate a tone programmatically using pure Python.

        Args:
            frequency: Tone frequency in Hz
            duration_ms: Duration in milliseconds

        Returns:
            pygame Sound object
        """
        sample_rate = 44100
        n_samples = int(sample_rate * duration_ms / 1000)
        fade_samples = min(int(sample_rate * 0.01), n_samples // 4)  # 10ms fade

        # Generate sine wave with envelope
        samples = array.array('h')  # signed short (16-bit)
        for i in range(n_samples):
            t = i / sample_rate
            # Sine wave
            value = math.sin(2 * math.pi * frequency * t)

            # Apply envelope (fade in/out)
            if i < fade_samples:
                value *= i / fade_samples
            elif i >= n_samples - fade_samples:
                value *= (n_samples - i) / fade_samples

            # Scale to 16-bit and apply volume
            samples.append(int(value * 32767 * self._volume))

        # Create sound from bytes
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def close(self) -> None:
        """Stop audio and cleanup pygame."""
        self.stop_alarm()
        if self._initialized:
            pygame.mixer.quit()
            self._initialized = False
            self._generated_sounds.clear()

    def set_volume(self, level: int) -> None:
        """Set volume level.

        Args:
            level: Volume from 0-100
        """
        self._volume = max(0, min(100, level)) / 100.0
        # Regenerate tones with new volume
        if self._initialized:
            for severity, config in self.TONE_CONFIGS.items():
                self._generated_sounds[severity] = self._generate_tone(
                    config['frequency'],
                    config['duration_ms']
                )

    def speak(self, message: str, blocking: bool = False) -> None:
        """Speak a message using TTS.

        Args:
            message: Text to speak
            blocking: Whether to wait for speech to complete
        """
        if not self._use_tts:
            return

        try:
            cmd = ["espeak", "-s", "150", "-a", str(int(self._volume * 200)), message]
            if blocking:
                subprocess.run(cmd, capture_output=True, timeout=30)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.debug(f"TTS: {message}")
        except Exception as e:
            logger.error(f"TTS error: {e}")

    def _speak_sync(self, message: str) -> None:
        """Speak a message synchronously (blocking).

        Args:
            message: Text to speak
        """
        self.speak(message, blocking=True)

    async def play_alarm_pattern(self, severity: str = "critical") -> None:
        """Play alarm pattern for given severity.

        Args:
            severity: One of critical, high, warning, info
        """
        if not self._initialized:
            return

        config = self.TONE_CONFIGS.get(severity, self.TONE_CONFIGS['warning'])
        sound = self._generated_sounds.get(severity)

        if not sound:
            return

        # Play the pattern
        for beep in config['pattern']:
            if not self._alarm_playing:
                break
            if beep:
                sound.play()
                await asyncio.sleep(config['duration_ms'] / 1000)
            else:
                await asyncio.sleep(config['pause_ms'] / 1000)

    async def play_alarm(self, severity: str = "critical", message: str = "", repeat_interval: float = 30.0) -> None:
        """Play alarm with TTS message repeatedly.

        Args:
            severity: Alert severity level
            message: Message to speak
            repeat_interval: Seconds between full repeats (pattern + TTS)
        """
        self._alarm_playing = True
        first_play = True

        while self._alarm_playing:
            # Play alarm tones
            await self.play_alarm_pattern(severity)

            if not self._alarm_playing:
                break

            # Speak message (always on first play, then periodically)
            if message and (first_play or repeat_interval >= 30):
                await asyncio.sleep(0.5)  # Brief pause before speaking
                self.speak(message, blocking=True)
                first_play = False

            if not self._alarm_playing:
                break

            # Wait before repeating
            await asyncio.sleep(repeat_interval)

    def start_alarm(self, severity: str = "critical", message: str = "", repeat_interval: float = 30.0) -> None:
        """Start alarm in background task.

        Args:
            severity: Alert severity level
            message: Message to speak via TTS
            repeat_interval: Seconds between repeats
        """
        # Always play immediate TTS for every new alert
        if self._use_tts and message:
            self._speak_sync(message)

        if self._alarm_task and not self._alarm_task.done():
            # Already playing - update severity/message if different
            if severity != self._current_severity or message != self._current_message:
                self.stop_alarm()
            else:
                logger.info(f"Alarm already active, TTS played for: {message}")
                return

        self._current_severity = severity
        self._current_message = message

        self._alarm_task = asyncio.create_task(self.play_alarm(severity, message, repeat_interval))
        logger.info(f"Started {severity} alarm: {message}")

    def stop_alarm(self) -> None:
        """Stop alarm playback."""
        self._alarm_playing = False
        if self._alarm_task:
            self._alarm_task.cancel()
            self._alarm_task = None

        if self._initialized:
            pygame.mixer.stop()

        logger.info("Stopped alarm playback")

    def play_alert(self, severity: str = "info", message: str = "") -> None:
        """Play single alert tone with optional TTS.

        Args:
            severity: Alert severity
            message: Optional message to speak
        """
        if not self._initialized:
            return

        sound = self._generated_sounds.get(severity, self._generated_sounds.get('info'))
        if sound:
            sound.play()

        if message:
            self.speak(message)

    @property
    def is_playing(self) -> bool:
        """Whether alarm is currently playing."""
        return self._alarm_playing


class PagerDutyClient:
    """PagerDuty Events API v2 client.

    Handles creating, acknowledging, and resolving PagerDuty incidents.
    Uses deduplication keys to prevent duplicate incidents.
    """

    EVENTS_API_URL = "https://events.pagerduty.com/v2/enqueue"
    REST_API_URL = "https://api.pagerduty.com"

    def __init__(self, routing_key: str, service_name: str = "O2 Monitor", api_token: str = ""):
        """Initialize PagerDuty client.

        Args:
            routing_key: PagerDuty Events API v2 routing key
            service_name: Service name for incident source
            api_token: PagerDuty REST API token for querying incidents
        """
        self.routing_key = routing_key
        self.service_name = service_name
        self.api_token = api_token
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _make_dedup_key(self, alert_type: str, alert_id: Optional[str] = None) -> str:
        """Create deduplication key for alert.

        Args:
            alert_type: Type of alert (spo2, ble, etc.)
            alert_id: Unique alert ID (each alert gets its own incident)

        Returns:
            Dedup key string
        """
        if alert_id:
            return f"o2-{alert_type}-{alert_id}"
        # Fallback with timestamp for uniqueness
        return f"o2-{alert_type}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    async def trigger_incident(
        self,
        summary: str,
        severity: str = "critical",
        dedup_key: Optional[str] = None,
        custom_details: Optional[Dict] = None,
    ) -> Optional[str]:
        """Create a new PagerDuty incident.

        Args:
            summary: Short incident description
            severity: One of critical, error, warning, info
            dedup_key: Deduplication key (optional)
            custom_details: Additional incident details

        Returns:
            Dedup key if successful, None on failure
        """
        if not self.routing_key:
            logger.warning("PagerDuty routing key not configured")
            return None

        payload = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": summary,
                "severity": severity,
                "source": self.service_name,
                "timestamp": datetime.now().isoformat(),
                "custom_details": custom_details or {},
            },
        }

        if dedup_key:
            payload["dedup_key"] = dedup_key

        try:
            # Create fresh session to avoid event loop issues with Flask
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.EVENTS_API_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 202:
                        data = await resp.json()
                        logger.info(f"PagerDuty incident triggered: {summary}")
                        return data.get("dedup_key", dedup_key)
                    else:
                        text = await resp.text()
                        logger.error(f"PagerDuty API error {resp.status}: {text}")
                        return None
        except Exception as e:
            logger.error(f"PagerDuty API request failed: {e}")
            return None

    async def acknowledge_incident(self, dedup_key: str) -> bool:
        """Acknowledge a PagerDuty incident.

        Args:
            dedup_key: Deduplication key of incident

        Returns:
            True if successful
        """
        return await self._send_event(dedup_key, "acknowledge")

    async def resolve_incident(self, dedup_key: str) -> bool:
        """Resolve a PagerDuty incident.

        Args:
            dedup_key: Deduplication key of incident

        Returns:
            True if successful
        """
        return await self._send_event(dedup_key, "resolve")

    async def _send_event(self, dedup_key: str, action: str) -> bool:
        """Send event action to PagerDuty.

        Args:
            dedup_key: Deduplication key
            action: Event action (acknowledge, resolve)

        Returns:
            True if successful
        """
        if not self.routing_key:
            return False

        payload = {
            "routing_key": self.routing_key,
            "event_action": action,
            "dedup_key": dedup_key,
        }

        try:
            # Create fresh session to avoid event loop issues with Flask
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.EVENTS_API_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 202:
                        logger.info(f"PagerDuty incident {action}d: {dedup_key}")
                        return True
                    else:
                        text = await resp.text()
                        logger.error(f"PagerDuty API error {resp.status}: {text}")
                        return False
        except Exception as e:
            logger.error(f"PagerDuty API request failed: {e}")
            return False

    async def get_incident_status(self, dedup_key: str) -> Optional[Dict]:
        """Get incident status from PagerDuty REST API.

        Args:
            dedup_key: Deduplication key of incident

        Returns:
            Dict with 'status' (triggered/acknowledged/resolved) and 'acknowledged_by',
            or None if not found or API unavailable
        """
        if not self.api_token:
            return None

        try:
            headers = {
                "Authorization": f"Token token={self.api_token}",
                "Content-Type": "application/json",
            }

            # Query incidents by incident_key (dedup_key)
            params = {
                "incident_key": dedup_key,
                "statuses[]": ["triggered", "acknowledged", "resolved"],
            }

            # Create fresh session to avoid event loop issues
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.REST_API_URL}/incidents",
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        incidents = data.get("incidents", [])
                        if incidents:
                            incident = incidents[0]  # Get most recent
                            status = incident.get("status", "unknown")
                            acknowledged_by = None

                            # Try to get who acknowledged
                            if status in ("acknowledged", "resolved"):
                                assignments = incident.get("assignments", [])
                                if assignments:
                                    assignee = assignments[0].get("assignee", {})
                                    acknowledged_by = assignee.get("summary", "PagerDuty")

                            return {
                                "status": status,
                                "acknowledged_by": acknowledged_by,
                                "incident_id": incident.get("id"),
                            }
                        return None
                    elif resp.status == 401:
                        logger.error("PagerDuty API token invalid or expired")
                        return None
                    else:
                        text = await resp.text()
                        logger.error(f"PagerDuty REST API error {resp.status}: {text}")
                        return None
        except Exception as e:
            logger.error(f"PagerDuty REST API request failed: {e}")
            return None


class HealthchecksClient:
    """Healthchecks.io heartbeat client.

    Sends periodic pings to Healthchecks.io to indicate the monitoring
    system is alive and functioning.
    """

    def __init__(self, ping_url: str):
        """Initialize Healthchecks client.

        Args:
            ping_url: Full ping URL including UUID
        """
        self.ping_url = ping_url
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def send_ping(self, status: str = "ok") -> bool:
        """Send heartbeat ping.

        Args:
            status: Status message to include

        Returns:
            True if ping was delivered
        """
        if not self.ping_url:
            logger.debug("Healthchecks URL not configured")
            return False

        try:
            session = await self._get_session()
            async with session.get(
                self.ping_url,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    logger.debug("Healthchecks ping sent")
                    return True
                else:
                    logger.warning(f"Healthchecks ping failed: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"Healthchecks ping error: {e}")
            return False

    async def send_fail(self, message: str = "") -> bool:
        """Send failure signal.

        Args:
            message: Failure description

        Returns:
            True if signal was delivered
        """
        if not self.ping_url:
            return False

        fail_url = f"{self.ping_url}/fail"
        try:
            session = await self._get_session()
            async with session.post(
                fail_url,
                data=message,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Healthchecks fail signal error: {e}")
            return False

    async def send_start(self) -> bool:
        """Signal check is starting.

        Returns:
            True if signal was delivered
        """
        if not self.ping_url:
            return False

        start_url = f"{self.ping_url}/start"
        try:
            session = await self._get_session()
            async with session.get(
                start_url,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Healthchecks start signal error: {e}")
            return False


class AlertManager:
    """Central alert management for O2 Monitor.

    Coordinates all alerting mechanisms:
    - Local audio alarms
    - PagerDuty incidents
    - Alert silencing
    - Deduplication
    """

    def __init__(self, config):
        """Initialize alert manager.

        Args:
            config: Config object with alerting settings
        """
        self.config = config

        # Initialize components based on config
        self._audio: Optional[AudioAlert] = None
        self._pagerduty: Optional[PagerDutyClient] = None
        self._healthchecks: Optional[HealthchecksClient] = None

        # Silence state
        self._silence_until: Optional[datetime] = None

        # Active alerts tracking
        self._active_alerts: Dict[str, Alert] = {}
        self._pagerduty_keys: Dict[str, str] = {}  # alert_id -> dedup_key

        logger.info("AlertManager initialized")

    async def initialize(self) -> None:
        """Initialize all alerting components."""
        # Audio alerting
        if self.config.alerting.local_audio.enabled:
            self._audio = AudioAlert(
                volume=self.config.alerting.local_audio.volume,
                use_tts=self.config.alerting.local_audio.use_tts,
            )
            await self._audio.initialize()

        # PagerDuty
        if self.config.alerting.pagerduty.routing_key:
            self._pagerduty = PagerDutyClient(
                routing_key=self.config.alerting.pagerduty.routing_key,
                service_name=self.config.alerting.pagerduty.service_name,
                api_token=getattr(self.config.alerting.pagerduty, 'api_token', ''),
            )

        # Healthchecks.io
        if self.config.alerting.healthchecks.ping_url:
            self._healthchecks = HealthchecksClient(
                ping_url=self.config.alerting.healthchecks.ping_url,
            )

        logger.info("AlertManager components initialized")

    async def close(self) -> None:
        """Close all alerting components."""
        if self._audio:
            self._audio.close()

        if self._pagerduty:
            await self._pagerduty.close()

        if self._healthchecks:
            await self._healthchecks.close()

        logger.info("AlertManager closed")

    # ==================== Alert Triggering ====================

    async def trigger_alarm(self, alert: Alert) -> Optional[str]:
        """Trigger full alarm (local + remote).

        Args:
            alert: Alert object with details

        Returns:
            PagerDuty dedup_key if incident was created, None otherwise
        """
        # Check for duplicate
        if alert.id in self._active_alerts:
            logger.debug(f"Alert {alert.id} already active, skipping")
            return self._pagerduty_keys.get(alert.id)

        self._active_alerts[alert.id] = alert
        logger.warning(f"ALARM: {alert.message}")

        # Local audio (unless silenced)
        if not self.is_silenced and self._audio:
            repeat_interval = self.config.alerting.local_audio.repeat_interval_seconds
            severity = alert.severity.value  # critical, high, warning, info
            # Create spoken message
            tts_message = self._create_tts_message(alert)
            self._audio.start_alarm(severity=severity, message=tts_message, repeat_interval=repeat_interval)

        # PagerDuty
        pd_key = None
        if self._pagerduty:
            dedup_key = self._pagerduty._make_dedup_key(alert.alert_type.value, alert.id)
            pd_key = await self._pagerduty.trigger_incident(
                summary=f"[{alert.id}] {alert.message}",
                severity=self._severity_to_pd(alert.severity),
                dedup_key=dedup_key,
                custom_details={
                    "alert_id": alert.id,
                    "spo2": alert.spo2,
                    "heart_rate": alert.heart_rate,
                    "avaps_state": alert.avaps_state.value if alert.avaps_state else None,
                    "timestamp": alert.timestamp.isoformat(),
                },
            )
            if pd_key:
                self._pagerduty_keys[alert.id] = pd_key

        return pd_key

    async def trigger_local_only(self, alert: Alert) -> None:
        """Trigger local audio alert only (single tone, no repeat).

        Args:
            alert: Alert object with details
        """
        if not self.is_silenced and self._audio:
            severity = alert.severity.value
            tts_message = self._create_tts_message(alert)
            self._audio.play_alert(severity=severity, message=tts_message)

        logger.info(f"Local alert: {alert.message}")

    def _create_tts_message(self, alert: Alert) -> str:
        """Create a spoken message for an alert.

        Args:
            alert: Alert object

        Returns:
            Message suitable for TTS
        """
        messages = {
            AlertType.SPO2_CRITICAL: f"Warning! Oxygen level critical at {alert.spo2} percent.",
            AlertType.SPO2_WARNING: f"Attention. Oxygen level low at {alert.spo2} percent.",
            AlertType.HR_HIGH: f"Attention. Heart rate high at {alert.heart_rate} beats per minute.",
            AlertType.HR_LOW: f"Attention. Heart rate low at {alert.heart_rate} beats per minute.",
            AlertType.DISCONNECT: "Attention. Oxygen monitor disconnected.",
            AlertType.NO_THERAPY_AT_NIGHT: "Attention. Therapy not in use during sleep hours.",
            AlertType.BATTERY_WARNING: f"Attention. Monitor battery low at {alert.spo2 if alert.spo2 else 'unknown'} percent.",
            AlertType.BATTERY_CRITICAL: f"Warning! Monitor battery critical.",
            AlertType.SYSTEM_ERROR: "Warning! System error detected.",
            AlertType.TEST: "This is a test alert.",
        }
        return messages.get(alert.alert_type, alert.message)

    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an active alert.

        Args:
            alert_id: ID of alert to resolve

        Returns:
            True if alert was found and resolved
        """
        if alert_id not in self._active_alerts:
            return False

        del self._active_alerts[alert_id]

        # Stop audio if no more active alarms
        if not self._active_alerts and self._audio:
            self._audio.stop_alarm()

        # Resolve PagerDuty incident
        if alert_id in self._pagerduty_keys and self._pagerduty:
            dedup_key = self._pagerduty_keys.pop(alert_id)
            await self._pagerduty.resolve_incident(dedup_key)

        logger.info(f"Alert resolved: {alert_id}")
        return True

    async def check_pagerduty_status(self, dedup_key: str) -> Optional[Dict]:
        """Check PagerDuty incident status.

        Args:
            dedup_key: PagerDuty deduplication key

        Returns:
            Dict with status info or None if unavailable
        """
        if not self._pagerduty:
            return None
        return await self._pagerduty.get_incident_status(dedup_key)

    async def resolve_all(self) -> None:
        """Resolve all active alerts."""
        alert_ids = list(self._active_alerts.keys())
        for alert_id in alert_ids:
            await self.resolve_alert(alert_id)

    # ==================== Silencing ====================

    def silence(self, duration_minutes: int) -> None:
        """Silence local audio alerts temporarily.

        Args:
            duration_minutes: How long to silence
        """
        self._silence_until = datetime.now() + timedelta(minutes=duration_minutes)

        # Stop current audio
        if self._audio:
            self._audio.stop_alarm()

        logger.info(f"Alerts silenced for {duration_minutes} minutes")

    def unsilence(self) -> None:
        """Cancel silence and resume alerting."""
        self._silence_until = None
        logger.info("Alerts unsilenced")

    @property
    def is_silenced(self) -> bool:
        """Whether alerts are currently silenced."""
        if self._silence_until is None:
            return False
        if datetime.now() >= self._silence_until:
            self._silence_until = None
            return False
        return True

    @property
    def silence_remaining_seconds(self) -> Optional[int]:
        """Seconds remaining in silence period, or None if not silenced."""
        if not self.is_silenced or self._silence_until is None:
            return None
        remaining = (self._silence_until - datetime.now()).total_seconds()
        return max(0, int(remaining))

    # ==================== Active Alerts ====================

    @property
    def active_alerts(self) -> List[Alert]:
        """List of currently active alerts."""
        return list(self._active_alerts.values())

    @property
    def has_active_alarms(self) -> bool:
        """Whether any alarms are currently active."""
        return len(self._active_alerts) > 0

    # ==================== Heartbeat ====================

    async def send_heartbeat(self, status: str = "ok") -> bool:
        """Send heartbeat ping to Healthchecks.io.

        Args:
            status: Status string

        Returns:
            True if ping was sent successfully
        """
        if self._healthchecks:
            return await self._healthchecks.send_ping(status)
        return False

    async def send_heartbeat_fail(self, message: str) -> bool:
        """Send failure signal to Healthchecks.io.

        Args:
            message: Failure description

        Returns:
            True if signal was sent
        """
        if self._healthchecks:
            return await self._healthchecks.send_fail(message)
        return False

    # ==================== Helpers ====================

    @staticmethod
    def _severity_to_pd(severity: AlertSeverity) -> str:
        """Convert AlertSeverity to PagerDuty severity string."""
        # Use the pagerduty_severity property from the enum
        return severity.pagerduty_severity


# Command-line interface for testing
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    parser = argparse.ArgumentParser(description="Test alerting module")
    parser.add_argument("--test-audio", action="store_true",
                        help="Test audio playback")
    parser.add_argument("--test-pagerduty", action="store_true",
                        help="Test PagerDuty (requires config)")
    parser.add_argument("--config", default="config.yaml",
                        help="Config file path")
    args = parser.parse_args()

    async def test_audio():
        print("=" * 50)
        print("Audio Alert Test")
        print("=" * 50)

        audio = AudioAlert(volume=80, use_tts=True)
        if not await audio.initialize():
            print("Failed to initialize audio")
            return

        print("\nTesting INFO tone...")
        audio.play_alert(severity="info", message="This is an info alert")
        await asyncio.sleep(3)

        print("\nTesting WARNING tone...")
        audio.play_alert(severity="warning", message="This is a warning alert")
        await asyncio.sleep(3)

        print("\nTesting HIGH tone...")
        audio.play_alert(severity="high", message="This is a high priority alert")
        await asyncio.sleep(3)

        print("\nTesting CRITICAL alarm pattern (5 seconds)...")
        audio._alarm_playing = True
        await audio.play_alarm_pattern("critical")
        audio._alarm_playing = False
        await asyncio.sleep(1)

        print("\nTesting TTS with critical alarm...")
        audio.speak("Warning! Oxygen level critical at 85 percent.", blocking=True)
        await asyncio.sleep(1)

        audio.close()
        print("\nAudio test complete")

    async def test_with_config():
        from src.config import load_config

        print("=" * 50)
        print("AlertManager Test with Config")
        print("=" * 50)

        config = load_config(args.config)

        manager = AlertManager(config)
        await manager.initialize()

        # Test silencing
        print("\nTesting silence...")
        manager.silence(1)
        print(f"  Is silenced: {manager.is_silenced}")
        print(f"  Remaining: {manager.silence_remaining_seconds}s")

        manager.unsilence()
        print(f"  After unsilence: {manager.is_silenced}")

        # Test alert creation (local only for safety)
        print("\nTesting local alert...")
        alert = Alert(
            id="test-001",
            timestamp=datetime.now(),
            alert_type=AlertType.TEST,
            severity=AlertSeverity.INFO,
            message="Test alert from alerting.py",
        )
        await manager.trigger_local_only(alert)

        await manager.close()
        print("\nTest complete")

    async def main():
        if args.test_audio:
            await test_audio()
        else:
            await test_with_config()

    asyncio.run(main())
