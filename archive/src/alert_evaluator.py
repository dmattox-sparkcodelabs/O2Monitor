# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Alert evaluation logic for O2 Monitor.

This module implements therapy-aware alert evaluation, checking readings
against configurable thresholds. Each alert can be configured to bypass
when AVAPS therapy is active.

Alert types evaluated:
- SpO2 critical/warning: Oxygen saturation below thresholds
- HR high/low: Heart rate outside normal range
- Disconnect: Oximeter disconnected
- No therapy at night: AVAPS off during sleep hours
- Battery: Low/critical battery levels
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from src.config import AlertsConfig, AlertItemConfig
from src.models import Alert, AlertSeverity, AlertType, AVAPSState, OxiReading

logger = logging.getLogger(__name__)


# Map severity strings to AlertSeverity enum
SEVERITY_MAP = {
    'critical': AlertSeverity.CRITICAL,
    'high': AlertSeverity.HIGH,
    'warning': AlertSeverity.WARNING,
    'info': AlertSeverity.INFO,
}


@dataclass
class AlertConditionTracker:
    """Tracks the start time of various alert conditions.

    Used to determine how long a condition has been active
    before triggering an alert.
    """
    condition_starts: Dict[str, datetime] = field(default_factory=dict)
    fired_alerts: Dict[str, datetime] = field(default_factory=dict)

    def reset(self, condition: str) -> None:
        """Reset a condition's start time."""
        self.condition_starts.pop(condition, None)

    def start(self, condition: str) -> None:
        """Start tracking a condition if not already started."""
        if condition not in self.condition_starts:
            self.condition_starts[condition] = datetime.now()

    def duration_seconds(self, condition: str) -> float:
        """Get how long a condition has been active."""
        start = self.condition_starts.get(condition)
        if start is None:
            return 0
        return (datetime.now() - start).total_seconds()

    def mark_fired(self, alert_type: str, severity: str) -> None:
        """Mark an alert as fired to prevent duplicates."""
        key = f"{alert_type}_{severity}"
        self.fired_alerts[key] = datetime.now()

    def was_fired_recently(self, alert_type: str, severity: str,
                           cooldown_seconds: float = 300) -> bool:
        """Check if alert was fired recently (within cooldown period)."""
        key = f"{alert_type}_{severity}"
        if key not in self.fired_alerts:
            return False
        elapsed = (datetime.now() - self.fired_alerts[key]).total_seconds()
        return elapsed < cooldown_seconds

    def clear_fired(self, alert_type: str) -> None:
        """Clear fired status for an alert type (all severities)."""
        keys_to_remove = [k for k in self.fired_alerts if k.startswith(alert_type)]
        for key in keys_to_remove:
            del self.fired_alerts[key]


class AlertEvaluator:
    """Evaluates readings against configurable alert thresholds.

    Each alert can be configured to bypass when AVAPS therapy is active.
    """

    def __init__(self, config: AlertsConfig):
        """Initialize the alert evaluator.

        Args:
            config: AlertsConfig with all threshold settings
        """
        self.config = config
        self.tracker = AlertConditionTracker()
        self._last_battery_level: Optional[int] = None

    def _get_severity(self, cfg: AlertItemConfig) -> AlertSeverity:
        """Get AlertSeverity enum from config string."""
        return SEVERITY_MAP.get(cfg.severity, AlertSeverity.WARNING)

    def _should_bypass(self, cfg: AlertItemConfig, therapy_on: bool) -> bool:
        """Check if alert should be bypassed based on therapy state."""
        return therapy_on and cfg.bypass_on_therapy

    def evaluate(
        self,
        reading: Optional[OxiReading],
        avaps_state: AVAPSState,
        ble_connected: bool,
    ) -> List[Alert]:
        """Evaluate all alert conditions and return triggered alerts.

        Args:
            reading: Current oximeter reading (None if disconnected)
            avaps_state: Current AVAPS therapy state
            ble_connected: Whether oximeter is connected

        Returns:
            List of Alert objects for conditions that should trigger
        """
        alerts = []
        therapy_on = avaps_state == AVAPSState.ON

        # Evaluate disconnect first (affects other evaluations)
        disconnect_alerts = self._evaluate_disconnect(ble_connected, therapy_on)
        alerts.extend(disconnect_alerts)

        # If connected and have a valid reading, evaluate vitals
        if ble_connected and reading and reading.is_valid:
            alerts.extend(self._evaluate_spo2(reading, therapy_on))
            alerts.extend(self._evaluate_hr(reading, therapy_on))
            alerts.extend(self._evaluate_battery(reading, therapy_on))

        # Evaluate no-therapy-at-night (independent of connection)
        alerts.extend(self._evaluate_no_therapy_at_night(avaps_state))

        return alerts

    def _evaluate_spo2(self, reading: OxiReading, therapy_on: bool) -> List[Alert]:
        """Evaluate SpO2 against critical and warning thresholds."""
        alerts = []
        spo2 = reading.spo2

        # Evaluate critical SpO2 - use different config based on therapy state
        if therapy_on:
            cfg = self.config.spo2_critical_on_therapy
            tracker_key = "spo2_critical_on"
        else:
            cfg = self.config.spo2_critical_off_therapy
            tracker_key = "spo2_critical_off"

        therapy_str = "on therapy" if therapy_on else "off therapy"

        if spo2 < cfg.threshold:
            self.tracker.start(tracker_key)
            duration = self.tracker.duration_seconds(tracker_key)

            if duration >= cfg.duration_seconds:
                severity = self._get_severity(cfg)
                cooldown = cfg.resend_interval_seconds
                if not self.tracker.was_fired_recently(tracker_key, severity.value, cooldown):
                    if cfg.enabled:
                        alert = Alert(
                            alert_type=AlertType.SPO2_CRITICAL,
                            severity=severity,
                            message=f"SpO2 critically low at {spo2}% for {int(duration)}s ({therapy_str})",
                            spo2=spo2,
                            heart_rate=reading.heart_rate,
                        )
                        alerts.append(alert)
                        self.tracker.mark_fired(tracker_key, severity.value)
                        logger.critical(f"SpO2 CRITICAL: {spo2}% for {duration:.0f}s ({therapy_str})")
                    else:
                        logger.info(f"SpO2 CRITICAL would fire (DISABLED): {spo2}% for {duration:.0f}s ({therapy_str})")
                        self.tracker.mark_fired(tracker_key, severity.value)
        else:
            self.tracker.reset(tracker_key)
            self.tracker.clear_fired(tracker_key)

        # Evaluate warning SpO2 (only if not already critical)
        cfg = self.config.spo2_warning
        if not alerts and not self._should_bypass(cfg, therapy_on):
            if spo2 < cfg.threshold:
                self.tracker.start("spo2_warning")
                duration = self.tracker.duration_seconds("spo2_warning")

                if duration >= cfg.duration_seconds:
                    severity = self._get_severity(cfg)
                    cooldown = cfg.resend_interval_seconds
                    if not self.tracker.was_fired_recently("spo2_warning", severity.value, cooldown):
                        if cfg.enabled:
                            alert = Alert(
                                alert_type=AlertType.SPO2_WARNING,
                                severity=severity,
                                message=f"SpO2 warning at {spo2}% for {int(duration)}s",
                                spo2=spo2,
                                heart_rate=reading.heart_rate,
                            )
                            alerts.append(alert)
                            self.tracker.mark_fired("spo2_warning", severity.value)
                            logger.warning(f"SpO2 WARNING: {spo2}% for {duration:.0f}s")
                        else:
                            logger.info(f"SpO2 WARNING would fire (DISABLED): {spo2}% for {duration:.0f}s")
                            self.tracker.mark_fired("spo2_warning", severity.value)
            else:
                self.tracker.reset("spo2_warning")
                self.tracker.clear_fired("spo2_warning")

        return alerts

    def _evaluate_hr(self, reading: OxiReading, therapy_on: bool) -> List[Alert]:
        """Evaluate heart rate against high and low thresholds."""
        alerts = []
        hr = reading.heart_rate

        # Evaluate HR high
        cfg = self.config.hr_high
        if not self._should_bypass(cfg, therapy_on):
            if hr > cfg.threshold:
                self.tracker.start("hr_high")
                duration = self.tracker.duration_seconds("hr_high")

                if duration >= cfg.duration_seconds:
                    severity = self._get_severity(cfg)
                    cooldown = cfg.resend_interval_seconds
                    if not self.tracker.was_fired_recently("hr_high", severity.value, cooldown):
                        if cfg.enabled:
                            alert = Alert(
                                alert_type=AlertType.HR_HIGH,
                                severity=severity,
                                message=f"Heart rate high at {hr} BPM for {int(duration)}s",
                                spo2=reading.spo2,
                                heart_rate=hr,
                            )
                            alerts.append(alert)
                            self.tracker.mark_fired("hr_high", severity.value)
                            logger.warning(f"HR HIGH: {hr} BPM for {duration:.0f}s")
                        else:
                            logger.info(f"HR HIGH would fire (DISABLED): {hr} BPM for {duration:.0f}s")
                            self.tracker.mark_fired("hr_high", severity.value)
            else:
                self.tracker.reset("hr_high")
                self.tracker.clear_fired("hr_high")

        # Evaluate HR low
        cfg = self.config.hr_low
        if not self._should_bypass(cfg, therapy_on):
            if hr < cfg.threshold:
                self.tracker.start("hr_low")
                duration = self.tracker.duration_seconds("hr_low")

                if duration >= cfg.duration_seconds:
                    severity = self._get_severity(cfg)
                    cooldown = cfg.resend_interval_seconds
                    if not self.tracker.was_fired_recently("hr_low", severity.value, cooldown):
                        if cfg.enabled:
                            alert = Alert(
                                alert_type=AlertType.HR_LOW,
                                severity=severity,
                                message=f"Heart rate low at {hr} BPM for {int(duration)}s",
                                spo2=reading.spo2,
                                heart_rate=hr,
                            )
                            alerts.append(alert)
                            self.tracker.mark_fired("hr_low", severity.value)
                            logger.warning(f"HR LOW: {hr} BPM for {duration:.0f}s")
                        else:
                            logger.info(f"HR LOW would fire (DISABLED): {hr} BPM for {duration:.0f}s")
                            self.tracker.mark_fired("hr_low", severity.value)
            else:
                self.tracker.reset("hr_low")
                self.tracker.clear_fired("hr_low")

        return alerts

    def _evaluate_disconnect(self, ble_connected: bool, therapy_on: bool) -> List[Alert]:
        """Evaluate disconnect condition."""
        alerts = []
        cfg = self.config.disconnect

        # Check bypass on therapy
        if self._should_bypass(cfg, therapy_on):
            self.tracker.reset("disconnect")
            self.tracker.clear_fired("disconnect")
            return alerts

        if not ble_connected:
            self.tracker.start("disconnect")
            duration_minutes = self.tracker.duration_seconds("disconnect") / 60

            # Threshold is in minutes for disconnect
            if duration_minutes >= cfg.threshold:
                severity = self._get_severity(cfg)
                cooldown = cfg.resend_interval_seconds
                if not self.tracker.was_fired_recently("disconnect", severity.value, cooldown):
                    if cfg.enabled:
                        alert = Alert(
                            alert_type=AlertType.DISCONNECT,
                            severity=severity,
                            message=f"Oximeter disconnected for {int(duration_minutes)} minutes",
                        )
                        alerts.append(alert)
                        self.tracker.mark_fired("disconnect", severity.value)
                        logger.warning(f"DISCONNECT: {duration_minutes:.0f} minutes")
                    else:
                        logger.info(f"DISCONNECT would fire (DISABLED): {duration_minutes:.0f} minutes")
                        self.tracker.mark_fired("disconnect", severity.value)
        else:
            # Connected - reset disconnect tracking
            if "disconnect" in self.tracker.condition_starts:
                logger.info("Oximeter reconnected")
            self.tracker.reset("disconnect")
            self.tracker.clear_fired("disconnect")

        return alerts

    def _evaluate_no_therapy_at_night(self, avaps_state: AVAPSState) -> List[Alert]:
        """Evaluate no-therapy-at-night condition with two escalation levels."""
        alerts = []

        # Check if we're in sleep hours
        now = datetime.now()
        in_sleep_hours = self.config.sleep_hours.is_sleep_hours(now.hour, now.minute)

        if not in_sleep_hours:
            self.tracker.reset("no_therapy")
            self.tracker.clear_fired("no_therapy_info")
            self.tracker.clear_fired("no_therapy_high")
            return alerts

        # In sleep hours - check if therapy is off
        if avaps_state == AVAPSState.OFF:
            self.tracker.start("no_therapy")
            duration_minutes = self.tracker.duration_seconds("no_therapy") / 60

            # Check high-level alert first (longer threshold)
            cfg_high = self.config.no_therapy_at_night_high
            if duration_minutes >= cfg_high.threshold:
                severity = self._get_severity(cfg_high)
                cooldown = cfg_high.resend_interval_seconds
                if not self.tracker.was_fired_recently("no_therapy_high", severity.value, cooldown):
                    if cfg_high.enabled:
                        alert = Alert(
                            alert_type=AlertType.NO_THERAPY_AT_NIGHT,
                            severity=severity,
                            message=f"URGENT: AVAPS therapy not in use for {int(duration_minutes)} minutes during sleep hours",
                        )
                        alerts.append(alert)
                        self.tracker.mark_fired("no_therapy_high", severity.value)
                        logger.warning(f"NO THERAPY (HIGH): {duration_minutes:.0f} minutes")
                    else:
                        logger.info(f"NO THERAPY (HIGH) would fire (DISABLED): {duration_minutes:.0f} minutes")
                        self.tracker.mark_fired("no_therapy_high", severity.value)

            # Check info-level alert (shorter threshold) - only if high didn't fire
            cfg_info = self.config.no_therapy_at_night_info
            if not alerts and duration_minutes >= cfg_info.threshold:
                severity = self._get_severity(cfg_info)
                cooldown = cfg_info.resend_interval_seconds
                if not self.tracker.was_fired_recently("no_therapy_info", severity.value, cooldown):
                    if cfg_info.enabled:
                        alert = Alert(
                            alert_type=AlertType.NO_THERAPY_AT_NIGHT,
                            severity=severity,
                            message=f"AVAPS therapy not in use for {int(duration_minutes)} minutes during sleep hours",
                        )
                        alerts.append(alert)
                        self.tracker.mark_fired("no_therapy_info", severity.value)
                        logger.info(f"NO THERAPY (INFO): {duration_minutes:.0f} minutes")
                    else:
                        logger.info(f"NO THERAPY (INFO) would fire (DISABLED): {duration_minutes:.0f} minutes")
                        self.tracker.mark_fired("no_therapy_info", severity.value)
        else:
            # Therapy is on - reset tracking
            self.tracker.reset("no_therapy")
            self.tracker.clear_fired("no_therapy_info")
            self.tracker.clear_fired("no_therapy_high")

        return alerts

    def _evaluate_battery(self, reading: OxiReading, therapy_on: bool) -> List[Alert]:
        """Evaluate battery level against warning and critical thresholds."""
        alerts = []
        battery = reading.battery_level

        # Only alert on battery changes or first reading
        if self._last_battery_level == battery:
            return alerts
        self._last_battery_level = battery

        # Check critical battery
        cfg = self.config.battery_critical
        if not self._should_bypass(cfg, therapy_on):
            if battery <= cfg.threshold:
                severity = self._get_severity(cfg)
                cooldown = cfg.resend_interval_seconds
                if not self.tracker.was_fired_recently("battery_critical", severity.value, cooldown):
                    if cfg.enabled:
                        alert = Alert(
                            alert_type=AlertType.BATTERY_CRITICAL,
                            severity=severity,
                            message=f"Oximeter battery critically low at {battery}%",
                            spo2=reading.spo2,
                            heart_rate=reading.heart_rate,
                        )
                        alerts.append(alert)
                        self.tracker.mark_fired("battery_critical", severity.value)
                        logger.error(f"BATTERY CRITICAL: {battery}%")
                    else:
                        logger.info(f"BATTERY CRITICAL would fire (DISABLED): {battery}%")
                        self.tracker.mark_fired("battery_critical", severity.value)
                return alerts  # Don't also fire warning

        # Check warning battery
        cfg = self.config.battery_warning
        if not self._should_bypass(cfg, therapy_on):
            if battery <= cfg.threshold:
                severity = self._get_severity(cfg)
                cooldown = cfg.resend_interval_seconds
                if not self.tracker.was_fired_recently("battery_warning", severity.value, cooldown):
                    if cfg.enabled:
                        alert = Alert(
                            alert_type=AlertType.BATTERY_WARNING,
                            severity=severity,
                            message=f"Oximeter battery low at {battery}%",
                            spo2=reading.spo2,
                            heart_rate=reading.heart_rate,
                        )
                        alerts.append(alert)
                        self.tracker.mark_fired("battery_warning", severity.value)
                        logger.warning(f"BATTERY WARNING: {battery}%")
                    else:
                        logger.info(f"BATTERY WARNING would fire (DISABLED): {battery}%")
                        self.tracker.mark_fired("battery_warning", severity.value)

        return alerts

    def reset_all(self) -> None:
        """Reset all tracking state."""
        self.tracker = AlertConditionTracker()
        self._last_battery_level = None
