# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""State machine for O2 Monitor.

This module implements the core monitoring logic that:
- Evaluates current conditions (SpO2, AVAPS state, BLE connection)
- Determines appropriate system state
- Triggers alerts when conditions warrant
- Handles state transitions and side effects

State Flow:
    INITIALIZING -> DISCONNECTED | NORMAL | THERAPY_ACTIVE
    DISCONNECTED -> NORMAL | THERAPY_ACTIVE (on reconnect)
    NORMAL -> LOW_SPO2_WARNING (SpO2 < 90%, AVAPS off)
    LOW_SPO2_WARNING -> ALARM (30s elapsed, still low)
    LOW_SPO2_WARNING -> NORMAL (SpO2 recovers or AVAPS on)
    ALARM -> NORMAL (SpO2 recovers or AVAPS on)
    * -> THERAPY_ACTIVE (AVAPS turned on)

Usage:
    from src.state_machine import O2MonitorStateMachine

    sm = O2MonitorStateMachine(
        config, ble_reader, avaps_monitor, alert_manager, database
    )
    await sm.run()
"""

import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Optional

# Add project root to path when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import (
    Alert, AlertSeverity, AlertType, AVAPSState,
    MonitorState, OxiReading, SystemStatus
)
from src.alert_evaluator import AlertEvaluator

logger = logging.getLogger(__name__)


class O2MonitorStateMachine:
    """Core state machine for O2 monitoring system.

    Coordinates all components and implements the monitoring logic:
    - Receives SpO2/HR readings from BLE reader
    - Polls AVAPS power state
    - Evaluates conditions and determines system state
    - Triggers appropriate alerts
    - Logs data to database

    Attributes:
        current_state: Current MonitorState
        current_reading: Most recent OxiReading
        avaps_state: Current AVAPS power state
    """

    # Timing constants
    EVALUATION_INTERVAL = 1.0      # Seconds between state evaluations
    AVAPS_POLL_INTERVAL = 5.0      # Seconds between AVAPS power checks
    HEARTBEAT_INTERVAL = 60.0      # Seconds between heartbeat pings
    DISCONNECT_ALERT_DELAY = 180   # Seconds before alerting on disconnect
    CLEANUP_INTERVAL = 86400       # Seconds between database cleanups (24 hours)

    def __init__(
        self,
        config,
        ble_reader,
        avaps_monitor,
        alert_manager,
        database,
    ):
        """Initialize state machine.

        Args:
            config: Configuration object
            ble_reader: BLE reader instance (real or mock)
            avaps_monitor: AVAPS monitor instance (real or mock)
            alert_manager: AlertManager instance
            database: Database instance
        """
        self.config = config
        self.ble_reader = ble_reader
        self.avaps_monitor = avaps_monitor
        self.alert_manager = alert_manager
        self.database = database

        # Alert evaluator for therapy-aware alerting
        self.alert_evaluator = AlertEvaluator(config.alerts)

        # State tracking
        self._current_state = MonitorState.INITIALIZING
        self._previous_state: Optional[MonitorState] = None
        self._state_changed_at = datetime.now()

        # Vitals tracking
        self._current_reading: Optional[OxiReading] = None
        self._last_stored_reading: Optional[OxiReading] = None
        self._avaps_state = AVAPSState.UNKNOWN
        self._last_avaps_poll = datetime.min

        # Low SpO2 tracking
        self._low_spo2_start: Optional[datetime] = None
        self._alarm_alert_id: Optional[str] = None

        # BLE tracking
        self._disconnect_start: Optional[datetime] = None
        self._disconnect_alert_sent = False

        # Heartbeat tracking
        self._last_heartbeat = datetime.min

        # Database cleanup tracking
        self._last_cleanup = datetime.min

        # Control
        self._running = False
        self._shutdown_event = asyncio.Event()

        # System start time
        self._start_time = datetime.now()

        logger.info("O2MonitorStateMachine initialized")

    # ==================== Properties ====================

    @property
    def current_state(self) -> MonitorState:
        """Current monitoring state."""
        return self._current_state

    @property
    def current_reading(self) -> Optional[OxiReading]:
        """Most recent SpO2/HR reading."""
        return self._current_reading

    @property
    def avaps_state(self) -> AVAPSState:
        """Current AVAPS power state."""
        return self._avaps_state

    @property
    def low_spo2_start_time(self) -> Optional[datetime]:
        """When SpO2 first dropped below threshold."""
        return self._low_spo2_start

    @property
    def low_spo2_duration(self) -> Optional[timedelta]:
        """Duration of current low SpO2 event."""
        if self._low_spo2_start is None:
            return None
        return datetime.now() - self._low_spo2_start

    @property
    def uptime(self) -> timedelta:
        """How long the monitor has been running."""
        return datetime.now() - self._start_time

    def get_status(self) -> SystemStatus:
        """Get comprehensive system status snapshot."""
        from src.models import BLEStatus

        reading = self._current_reading
        ble_status = BLEStatus(
            connected=self.ble_reader.is_connected,
            battery_level=self.ble_reader.battery_level,
            last_reading_time=reading.timestamp if reading else None,
        )

        return SystemStatus(
            timestamp=datetime.now(),
            state=self._current_state,
            current_reading=reading,
            ble_status=ble_status,
            avaps_state=self._avaps_state,
            alerts_silenced=self.alert_manager.is_silenced,
            silence_remaining_seconds=self.alert_manager.silence_remaining_seconds,
            active_alert_count=len(self.alert_manager.active_alerts),
            uptime_seconds=self.uptime.total_seconds(),
            low_spo2_start_time=self._low_spo2_start,
        )

    # ==================== Main Loop ====================

    async def run(self) -> None:
        """Main monitoring loop.

        Runs until stop() is called. Coordinates:
        - BLE reading reception (via callback)
        - AVAPS power polling
        - State evaluation
        - Heartbeat pings
        """
        self._running = True
        self._shutdown_event.clear()
        logger.info("State machine starting")

        # Set up BLE callback
        self.ble_reader.callback = self._on_reading

        # Log start event
        await self.database.log_event(
            "system_start",
            "O2 Monitor starting",
            {"mock_mode": self.config.mock_mode}
        )

        # Send heartbeat start signal
        await self.alert_manager.send_heartbeat("starting")

        try:
            while self._running:
                try:
                    await self._evaluation_cycle()
                except Exception as e:
                    logger.error(f"Error in evaluation cycle: {e}")
                    await self.database.log_event(
                        "error",
                        f"Evaluation error: {e}",
                    )

                await asyncio.sleep(self.EVALUATION_INTERVAL)

        finally:
            # Clean up
            await self._cleanup()

    async def _evaluation_cycle(self) -> None:
        """Single evaluation cycle."""
        now = datetime.now()

        # Poll AVAPS if needed
        if (now - self._last_avaps_poll).total_seconds() >= self.AVAPS_POLL_INTERVAL:
            await self._poll_avaps()

        # Store current reading if it's new
        if (self._current_reading and
                self._current_reading is not self._last_stored_reading):
            await self._store_reading(self._current_reading)
            self._last_stored_reading = self._current_reading

        # Evaluate alerts using new therapy-aware system
        await self._evaluate_alerts()

        # Evaluate state
        new_state = await self._evaluate_state()

        # Handle state change
        if new_state != self._current_state:
            await self._handle_state_transition(self._current_state, new_state)
            self._previous_state = self._current_state
            self._current_state = new_state
            self._state_changed_at = now

        # Send heartbeat if needed
        if (now - self._last_heartbeat).total_seconds() >= self.HEARTBEAT_INTERVAL:
            await self._send_heartbeat()

        # Run daily database cleanup if needed
        if (now - self._last_cleanup).total_seconds() >= self.CLEANUP_INTERVAL:
            await self._run_cleanup()

    def stop(self) -> None:
        """Signal shutdown."""
        logger.info("State machine stopping")
        self._running = False
        self._shutdown_event.set()

    async def _cleanup(self) -> None:
        """Clean up on shutdown."""
        # Resolve any active alerts
        await self.alert_manager.resolve_all()

        # Log shutdown
        await self.database.log_event(
            "system_stop",
            "O2 Monitor stopping",
            {"uptime_seconds": int(self.uptime.total_seconds())}
        )

        # Send final heartbeat
        await self.alert_manager.send_heartbeat("shutdown")

        logger.info("State machine cleanup complete")

    # ==================== Alert Evaluation ====================

    async def _evaluate_alerts(self) -> None:
        """Evaluate all alert conditions using therapy-aware thresholds.

        Uses the AlertEvaluator to check:
        - SpO2 critical/warning (therapy-aware thresholds)
        - HR high/low (therapy-aware)
        - Disconnect (escalating severity)
        - No therapy at night (sleep hours check)
        - Battery warnings
        """
        # Get alerts from evaluator
        alerts = self.alert_evaluator.evaluate(
            reading=self._current_reading,
            avaps_state=self._avaps_state,
            ble_connected=self.ble_reader.is_connected,
        )

        # Process each alert
        for alert in alerts:
            # Set AVAPS state on alert
            alert.avaps_state = self._avaps_state

            # Store in database
            await self.database.insert_alert(alert)

            # Trigger alert through manager
            # Critical alerts always trigger full alarm
            # Others depend on severity
            if alert.severity == AlertSeverity.CRITICAL:
                await self.alert_manager.trigger_alarm(alert)
            elif alert.severity == AlertSeverity.HIGH:
                await self.alert_manager.trigger_alarm(alert)
            elif alert.severity == AlertSeverity.WARNING:
                # Warning: trigger but maybe not full alarm
                await self.alert_manager.trigger_alarm(alert)
            else:
                # Info: log only, no alarm
                logger.info(f"Alert (info): {alert.message}")

    # ==================== State Evaluation ====================

    # Threshold for considering readings stale (seconds)
    STALE_READING_THRESHOLD = 30

    async def _evaluate_state(self) -> MonitorState:
        """Evaluate current conditions and determine state.

        Returns:
            Appropriate MonitorState based on current conditions
        """
        # Check BLE connection first
        if not self.ble_reader.is_connected:
            return await self._evaluate_disconnected()

        # Check for stale readings - if no new data, treat as disconnected
        # This handles cases where BLE is connected but sensor is off/inactive
        if self._current_reading:
            reading_age = (datetime.now() - self._current_reading.timestamp).total_seconds()
            if reading_age > self.STALE_READING_THRESHOLD:
                return await self._evaluate_disconnected()

        # Must have a valid reading to be in any "normal" operating state
        if not self._current_reading or not self._current_reading.is_valid:
            # Connected but no data yet - stay in initializing
            return MonitorState.INITIALIZING

        # Check AVAPS state
        if self._avaps_state == AVAPSState.ON:
            return MonitorState.THERAPY_ACTIVE

        # Check for silenced state
        if self.alert_manager.is_silenced:
            return MonitorState.SILENCED

        # Check SpO2 levels
        spo2 = self._current_reading.spo2
        threshold = self.config.thresholds.spo2.alarm_level

        if spo2 < threshold:
            return await self._evaluate_low_spo2()

        # Clear low SpO2 tracking if we're back to normal
        self._low_spo2_start = None

        return MonitorState.NORMAL

    async def _evaluate_disconnected(self) -> MonitorState:
        """Evaluate disconnected state and handle alerting."""
        now = datetime.now()

        # Track disconnect start
        if self._disconnect_start is None:
            self._disconnect_start = now
            logger.warning("BLE disconnected")

        # Check if we should alert
        disconnect_duration = (now - self._disconnect_start).total_seconds()
        if (disconnect_duration >= self.DISCONNECT_ALERT_DELAY and
                not self._disconnect_alert_sent):
            await self._trigger_disconnect_alert()
            self._disconnect_alert_sent = True

        return MonitorState.DISCONNECTED

    async def _evaluate_low_spo2(self) -> MonitorState:
        """Evaluate low SpO2 condition."""
        now = datetime.now()
        alarm_duration = self.config.thresholds.spo2.alarm_duration_seconds

        # Start tracking if this is new
        if self._low_spo2_start is None:
            self._low_spo2_start = now
            logger.warning(
                f"Low SpO2 detected: {self._current_reading.spo2}% "
                f"(threshold: {self.config.thresholds.spo2.alarm_level}%)"
            )
            return MonitorState.LOW_SPO2_WARNING

        # Check if alarm duration exceeded
        elapsed = (now - self._low_spo2_start).total_seconds()
        if elapsed >= alarm_duration:
            # Trigger alarm if not already triggered
            if self._alarm_alert_id is None:
                await self._trigger_spo2_alarm()
            return MonitorState.ALARM

        return MonitorState.LOW_SPO2_WARNING

    # ==================== State Transitions ====================

    async def _handle_state_transition(
        self,
        old_state: MonitorState,
        new_state: MonitorState
    ) -> None:
        """Handle side effects of state transitions.

        Args:
            old_state: Previous state
            new_state: New state
        """
        logger.info(f"State transition: {old_state.value} -> {new_state.value}")

        # Log to database
        await self.database.log_event(
            "state_change",
            f"State: {old_state.value} -> {new_state.value}",
            {
                "old_state": old_state.value,
                "new_state": new_state.value,
                "spo2": self._current_reading.spo2 if self._current_reading else None,
                "avaps_state": self._avaps_state.value,
            }
        )

        # Handle specific transitions
        if old_state == MonitorState.DISCONNECTED and new_state != MonitorState.DISCONNECTED:
            # Reconnected
            self._disconnect_start = None
            self._disconnect_alert_sent = False
            logger.info("BLE reconnected")

        if old_state == MonitorState.ALARM and new_state != MonitorState.ALARM:
            # Alarm resolved
            if self._alarm_alert_id:
                await self.alert_manager.resolve_alert(self._alarm_alert_id)
                self._alarm_alert_id = None
            logger.info("SpO2 alarm resolved")

        if new_state == MonitorState.THERAPY_ACTIVE:
            # AVAPS turned on - clear any low SpO2 tracking
            self._low_spo2_start = None
            if self._alarm_alert_id:
                await self.alert_manager.resolve_alert(self._alarm_alert_id)
                self._alarm_alert_id = None

    # ==================== Alerting ====================

    async def _trigger_spo2_alarm(self) -> None:
        """Trigger SpO2 alarm."""
        reading = self._current_reading
        duration = self.low_spo2_duration

        message = self.config.messages.spo2_alarm
        if reading:
            message = f"{message} SpO2: {reading.spo2}%"

        alert = Alert(
            id=f"spo2-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            alert_type=AlertType.SPO2_CRITICAL,
            severity=AlertSeverity.CRITICAL,
            message=message,
            spo2=reading.spo2 if reading else None,
            heart_rate=reading.heart_rate if reading else None,
            avaps_state=self._avaps_state,
        )

        self._alarm_alert_id = alert.id

        # Store in database
        await self.database.insert_alert(alert)

        # Trigger alarm
        await self.alert_manager.trigger_alarm(alert)

        logger.critical(
            f"SPO2 ALARM: {reading.spo2 if reading else '?'}% "
            f"for {duration.total_seconds() if duration else 0:.0f}s"
        )

    async def _trigger_disconnect_alert(self) -> None:
        """Trigger BLE disconnect alert."""
        alert = Alert(
            id=f"ble-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            alert_type=AlertType.DISCONNECT,
            severity=AlertSeverity.WARNING,
            message=self.config.messages.ble_disconnect,
        )

        await self.database.insert_alert(alert)
        await self.alert_manager.trigger_alarm(alert)

        logger.warning("BLE disconnect alert triggered")

    # ==================== Component Integration ====================

    def _on_reading(self, reading: OxiReading) -> None:
        """Callback for new BLE readings.

        Args:
            reading: New OxiReading from BLE reader
        """
        self._current_reading = reading

        # Clear disconnect tracking on valid reading
        if reading.is_valid and self._disconnect_start:
            self._disconnect_start = None
            self._disconnect_alert_sent = False

        # Queue reading for storage (handled in main loop)
        # Note: Callback may be called from a different thread,
        # so we just store the reading and let the main loop handle DB writes

        # Log warning-level readings
        if reading.is_valid:
            warning_level = self.config.thresholds.spo2.warning_level
            if reading.spo2 < warning_level:
                logger.warning(f"Low SpO2 reading: {reading.spo2}%")

    async def _store_reading(self, reading: OxiReading) -> None:
        """Store reading in database.

        Args:
            reading: OxiReading to store
        """
        try:
            await self.database.insert_reading(reading, self._avaps_state)
        except Exception as e:
            logger.error(f"Failed to store reading: {e}")

    async def _poll_avaps(self) -> None:
        """Poll AVAPS power state."""
        self._last_avaps_poll = datetime.now()

        try:
            self._avaps_state = await self.avaps_monitor.get_state()
        except Exception as e:
            logger.warning(f"AVAPS poll failed: {e}")
            self._avaps_state = AVAPSState.UNKNOWN

    async def _send_heartbeat(self) -> None:
        """Send heartbeat ping."""
        self._last_heartbeat = datetime.now()

        status = "ok"
        if self._current_state == MonitorState.ALARM:
            status = "alarm"
        elif self._current_state == MonitorState.DISCONNECTED:
            status = "disconnected"

        await self.alert_manager.send_heartbeat(status)

    async def _run_cleanup(self) -> None:
        """Run daily database cleanup and config backup."""
        self._last_cleanup = datetime.now()
        logger.info("Running daily maintenance")

        # Database cleanup
        try:
            deleted = await self.database.cleanup_old_data(
                readings_days=30,
                alerts_days=365,
                events_days=90
            )
            logger.info(f"Database cleanup complete: {deleted}")
            await self.database.log_event(
                "cleanup",
                "Daily database cleanup completed",
                deleted
            )
        except Exception as e:
            logger.error(f"Database cleanup failed: {e}")

        # Config backup
        try:
            import subprocess
            result = subprocess.run(
                ["./backup-config.sh"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                logger.info("Config backup completed")
            else:
                logger.warning(f"Config backup failed: {result.stderr}")
        except Exception as e:
            logger.error(f"Config backup failed: {e}")


# Command-line interface for testing
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    parser = argparse.ArgumentParser(description="Test state machine")
    parser.add_argument("--config", default="config.yaml",
                        help="Config file path")
    parser.add_argument("--duration", type=int, default=60,
                        help="Test duration in seconds")
    args = parser.parse_args()

    async def main():
        from src.config import load_config
        from src.mocks import MockBLEReader, MockAVAPSMonitor
        from src.alerting import AlertManager
        from src.database import Database

        print("=" * 50)
        print("State Machine Test (Mock Mode)")
        print("=" * 50)

        config = load_config(args.config)

        # Create mock components
        ble_reader = MockBLEReader()
        ble_reader.connect()

        avaps_monitor = MockAVAPSMonitor()

        alert_manager = AlertManager(config)
        await alert_manager.initialize()

        database = Database("data/test_sm.db")
        await database.initialize()

        # Create state machine
        sm = O2MonitorStateMachine(
            config, ble_reader, avaps_monitor, alert_manager, database
        )

        print(f"Running for {args.duration} seconds...")
        print("Press Ctrl+C to stop\n")

        # Run with timeout
        async def run_with_updates():
            ble_reader.start()

            # Schedule state machine stop
            async def stop_after_delay():
                await asyncio.sleep(args.duration)
                sm.stop()

            asyncio.create_task(stop_after_delay())

            # Print status periodically
            async def print_status():
                while sm._running:
                    status = sm.get_status()
                    reading = status.current_reading
                    spo2 = reading.spo2 if reading else '--'
                    hr = reading.heart_rate if reading else '--'
                    print(
                        f"State: {status.state.value:15} | "
                        f"SpO2: {spo2:>3}% | "
                        f"HR: {hr:>3} | "
                        f"AVAPS: {status.avaps_state.value:7}"
                    )
                    await asyncio.sleep(5)

            asyncio.create_task(print_status())

            await sm.run()

        try:
            await run_with_updates()
        except KeyboardInterrupt:
            sm.stop()

        # Cleanup
        ble_reader.stop()
        await alert_manager.close()
        await database.close()

        # Remove test database
        if os.path.exists("data/test_sm.db"):
            os.remove("data/test_sm.db")

        print("\n" + "=" * 50)
        print("Test complete")
        print("=" * 50)

    asyncio.run(main())
