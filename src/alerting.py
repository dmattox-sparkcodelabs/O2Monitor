"""Alerting system for O2 Monitor.

This module handles all alert delivery mechanisms:
- Local audio alarms via pygame
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
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logger.warning("pygame not available - audio alerts disabled")


class AudioAlert:
    """Local audio alerting via pygame.

    Handles playing alarm sounds through the Raspberry Pi audio output.
    Supports repeating alarms, volume control, and TTS announcements.
    """

    def __init__(
        self,
        alarm_sound: str = "sounds/alarm.wav",
        alert_sound: str = "sounds/alert.wav",
        volume: int = 90,
    ):
        """Initialize audio alerting.

        Args:
            alarm_sound: Path to loud alarm sound file
            alert_sound: Path to warning sound file
            volume: Default volume (0-100)
        """
        self.alarm_sound = alarm_sound
        self.alert_sound = alert_sound
        self._volume = volume / 100.0
        self._initialized = False
        self._alarm_playing = False
        self._alarm_task: Optional[asyncio.Task] = None

    async def initialize(self) -> bool:
        """Initialize pygame mixer.

        Returns:
            True if initialization successful
        """
        if not PYGAME_AVAILABLE:
            logger.warning("Cannot initialize audio - pygame not available")
            return False

        try:
            pygame.mixer.init()
            pygame.mixer.music.set_volume(self._volume)
            self._initialized = True
            logger.info("Audio alerting initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize pygame mixer: {e}")
            return False

    def close(self) -> None:
        """Stop audio and cleanup pygame."""
        self.stop_alarm()
        if self._initialized:
            pygame.mixer.quit()
            self._initialized = False

    def set_volume(self, level: int) -> None:
        """Set volume level.

        Args:
            level: Volume from 0-100
        """
        self._volume = max(0, min(100, level)) / 100.0
        if self._initialized:
            pygame.mixer.music.set_volume(self._volume)

    def play_sound(self, sound_path: str, loops: int = 0) -> bool:
        """Play a sound file.

        Args:
            sound_path: Path to sound file
            loops: Number of times to repeat (-1 for infinite)

        Returns:
            True if playback started
        """
        if not self._initialized:
            return False

        if not os.path.exists(sound_path):
            logger.error(f"Sound file not found: {sound_path}")
            return False

        try:
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play(loops=loops)
            return True
        except Exception as e:
            logger.error(f"Error playing sound: {e}")
            return False

    async def play_alarm(self, repeat_interval: float = 30.0) -> None:
        """Play loud alarm sound repeatedly.

        Args:
            repeat_interval: Seconds between repeats
        """
        self._alarm_playing = True
        while self._alarm_playing:
            if not self.play_sound(self.alarm_sound):
                # If sound file missing, wait and try again
                await asyncio.sleep(repeat_interval)
                continue

            # Wait for sound to finish or interval
            await asyncio.sleep(repeat_interval)

    def start_alarm(self, repeat_interval: float = 30.0) -> None:
        """Start alarm in background task.

        Args:
            repeat_interval: Seconds between repeats
        """
        if self._alarm_task and not self._alarm_task.done():
            return  # Already playing

        self._alarm_task = asyncio.create_task(self.play_alarm(repeat_interval))
        logger.info("Started alarm playback")

    def stop_alarm(self) -> None:
        """Stop alarm playback."""
        self._alarm_playing = False
        if self._alarm_task:
            self._alarm_task.cancel()
            self._alarm_task = None

        if self._initialized:
            pygame.mixer.music.stop()

        logger.info("Stopped alarm playback")

    def play_alert(self) -> bool:
        """Play single warning sound.

        Returns:
            True if playback started
        """
        return self.play_sound(self.alert_sound, loops=0)

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

    def __init__(self, routing_key: str, service_name: str = "O2 Monitor"):
        """Initialize PagerDuty client.

        Args:
            routing_key: PagerDuty Events API v2 routing key
            service_name: Service name for incident source
        """
        self.routing_key = routing_key
        self.service_name = service_name
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

    def _make_dedup_key(self, alert_type: str, date: Optional[datetime] = None) -> str:
        """Create deduplication key for alert.

        Args:
            alert_type: Type of alert (spo2, ble, etc.)
            date: Date for key (defaults to today)

        Returns:
            Dedup key string
        """
        date = date or datetime.now()
        return f"o2-{alert_type}-{date.strftime('%Y%m%d')}"

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
            session = await self._get_session()
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
            session = await self._get_session()
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
                alarm_sound=self.config.alerting.local_audio.alarm_sound,
                alert_sound="sounds/alert.wav",  # Use default
                volume=self.config.alerting.local_audio.volume,
            )
            await self._audio.initialize()

        # PagerDuty
        if self.config.alerting.pagerduty.routing_key:
            self._pagerduty = PagerDutyClient(
                routing_key=self.config.alerting.pagerduty.routing_key,
                service_name=self.config.alerting.pagerduty.service_name,
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

    async def trigger_alarm(self, alert: Alert) -> None:
        """Trigger full alarm (local + remote).

        Args:
            alert: Alert object with details
        """
        # Check for duplicate
        if alert.id in self._active_alerts:
            logger.debug(f"Alert {alert.id} already active, skipping")
            return

        self._active_alerts[alert.id] = alert
        logger.warning(f"ALARM: {alert.message}")

        # Local audio (unless silenced)
        if not self.is_silenced and self._audio:
            repeat_interval = self.config.alerting.local_audio.repeat_interval_seconds
            self._audio.start_alarm(repeat_interval)

        # PagerDuty
        if self._pagerduty:
            dedup_key = self._pagerduty._make_dedup_key(alert.alert_type.value)
            pd_key = await self._pagerduty.trigger_incident(
                summary=alert.message,
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

    async def trigger_local_only(self, alert: Alert) -> None:
        """Trigger local audio alert only.

        Args:
            alert: Alert object with details
        """
        if not self.is_silenced and self._audio:
            self._audio.play_alert()

        logger.info(f"Local alert: {alert.message}")

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
        mapping = {
            AlertSeverity.CRITICAL: "critical",
            AlertSeverity.WARNING: "warning",
            AlertSeverity.INFO: "info",
        }
        return mapping.get(severity, "warning")


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

        audio = AudioAlert()
        if not await audio.initialize():
            print("Failed to initialize audio")
            return

        print("Playing test sound...")
        # Try to play alert sound
        if os.path.exists("sounds/alert.wav"):
            audio.play_alert()
            await asyncio.sleep(2)
        else:
            print("Note: sounds/alert.wav not found")
            print("Create alarm sounds for full testing")

        audio.close()
        print("Audio test complete")

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
