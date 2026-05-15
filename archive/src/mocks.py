# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Mock hardware implementations for testing without physical devices.

This module provides simulated versions of the BLE oximeter reader and
AVAPS power monitor that generate realistic data for testing the
monitoring system without requiring actual hardware.

Enable mock mode by:
- Setting MOCK_HARDWARE=true environment variable, OR
- Setting mock_mode: true in config.yaml
"""

import asyncio
import logging
import random
import threading
import time
from datetime import datetime
from typing import Callable, List, Optional

from src.models import AVAPSState, OxiReading

logger = logging.getLogger(__name__)


class MockBLEReader:
    """Simulated BLE oximeter reader for testing.

    Generates realistic SpO2 and heart rate data with configurable
    patterns for testing normal operation and alarm scenarios.

    The mock can be controlled to:
    - Generate normal readings (SpO2 92-99%, HR 60-90 bpm)
    - Simulate low SpO2 events (dips below 90%)
    - Simulate disconnection/reconnection
    - Simulate sensor-off conditions

    Attributes:
        mac_address: Simulated device MAC address
        read_interval: Seconds between readings
        is_connected: Whether mock is "connected"
        callback: Function called with each reading
    """

    def __init__(
        self,
        mac_address: str = "00:00:00:00:00:00",
        callback: Optional[Callable[[OxiReading], None]] = None,
        read_interval: int = 10,
    ):
        """Initialize mock BLE reader.

        Args:
            mac_address: MAC address (for logging, not used)
            callback: Function to call with each reading
            read_interval: Seconds between readings
        """
        self.mac_address = mac_address
        self.callback = callback
        self.read_interval = read_interval

        # Connection state
        self._connected = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Reading state
        self._readings: List[OxiReading] = []
        self._last_reading: Optional[OxiReading] = None
        self._battery_level = 85

        # Simulation controls
        self._simulate_disconnect = False
        self._simulate_low_spo2 = False
        self._simulate_sensor_off = False
        self._low_spo2_value = 85  # Value to use when simulating low SpO2

        # Base values for normal readings (will vary around these)
        self._base_spo2 = 96
        self._base_hr = 72

        logger.info(f"MockBLEReader initialized (MAC: {mac_address})")

    @property
    def is_connected(self) -> bool:
        """Whether the mock is currently connected."""
        return self._connected and not self._simulate_disconnect

    @property
    def last_reading(self) -> Optional[OxiReading]:
        """Most recent reading."""
        return self._last_reading

    @property
    def battery_level(self) -> Optional[int]:
        """Simulated battery level."""
        return self._battery_level if self._connected else None

    def connect(self) -> bool:
        """Simulate connection to device.

        Returns:
            True after brief simulated connection delay
        """
        logger.info("MockBLEReader: Simulating connection...")
        time.sleep(0.5)  # Brief delay to simulate connection
        self._connected = True
        logger.info("MockBLEReader: Connected (simulated)")
        return True

    def disconnect(self) -> None:
        """Disconnect and stop reading loop."""
        logger.info("MockBLEReader: Disconnecting...")
        self._running = False
        self._connected = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def start(self) -> None:
        """Start generating readings in a background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._reading_loop, daemon=True)
        self._thread.start()
        logger.info("MockBLEReader: Started reading loop")

    def stop(self) -> None:
        """Stop generating readings."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("MockBLEReader: Stopped")

    def run(self, num_readings: int = -1) -> List[OxiReading]:
        """Run and collect readings (blocking).

        Args:
            num_readings: Number of readings to collect (-1 for infinite)

        Returns:
            List of collected readings
        """
        self.connect()
        self._readings = []
        count = 0

        while self._running or num_readings != -1:
            if not self.is_connected:
                time.sleep(1)
                continue

            reading = self._generate_reading()
            if reading:
                self._readings.append(reading)
                if self.callback:
                    self.callback(reading)
                count += 1

                if num_readings > 0 and count >= num_readings:
                    break

            time.sleep(self.read_interval)

        return self._readings

    def _reading_loop(self) -> None:
        """Background thread reading loop."""
        while self._running:
            if self.is_connected:
                reading = self._generate_reading()
                if reading and self.callback:
                    self.callback(reading)

            time.sleep(self.read_interval)

    def _generate_reading(self) -> Optional[OxiReading]:
        """Generate a simulated reading.

        Returns:
            OxiReading with simulated values, or None if sensor off
        """
        if self._simulate_sensor_off:
            logger.debug("MockBLEReader: Sensor off (simulated)")
            return OxiReading(
                timestamp=datetime.now(),
                spo2=0,
                heart_rate=0,
                battery_level=self._battery_level,
                movement=0,
                is_valid=False,
            )

        # Generate SpO2 value
        if self._simulate_low_spo2:
            # Low SpO2 scenario - use configured low value with small variation
            spo2 = self._low_spo2_value + random.randint(-2, 2)
            spo2 = max(70, min(89, spo2))  # Keep in "low" range
        else:
            # Normal variation around base value
            spo2 = self._base_spo2 + random.randint(-3, 3)
            spo2 = max(92, min(100, spo2))  # Normal range

            # Occasional natural dip (5% chance)
            if random.random() < 0.05:
                spo2 = random.randint(88, 91)

        # Generate heart rate with variation
        hr = self._base_hr + random.randint(-8, 8)
        hr = max(50, min(110, hr))

        # Small movement variation
        movement = random.randint(0, 3)

        # Slowly drain battery (very slowly for simulation)
        if random.random() < 0.01:
            self._battery_level = max(10, self._battery_level - 1)

        reading = OxiReading(
            timestamp=datetime.now(),
            spo2=spo2,
            heart_rate=hr,
            battery_level=self._battery_level,
            movement=movement,
            is_valid=True,
        )

        self._last_reading = reading
        logger.debug(f"MockBLEReader: Generated reading SpO2={spo2}% HR={hr}bpm")

        return reading

    # Simulation control methods

    def simulate_disconnect(self, disconnected: bool = True) -> None:
        """Simulate connection loss.

        Args:
            disconnected: True to simulate disconnect, False to reconnect
        """
        self._simulate_disconnect = disconnected
        logger.info(f"MockBLEReader: Simulating disconnect={disconnected}")

    def simulate_low_spo2(self, low: bool = True, value: int = 85) -> None:
        """Simulate low SpO2 readings.

        Args:
            low: True to enable low SpO2 simulation
            value: SpO2 value to simulate (default 85%)
        """
        self._simulate_low_spo2 = low
        self._low_spo2_value = value
        logger.info(f"MockBLEReader: Simulating low SpO2={low} (value={value}%)")

    def simulate_sensor_off(self, off: bool = True) -> None:
        """Simulate sensor removed from finger.

        Args:
            off: True to simulate sensor off
        """
        self._simulate_sensor_off = off
        logger.info(f"MockBLEReader: Simulating sensor off={off}")

    def set_base_values(self, spo2: int = 96, hr: int = 72) -> None:
        """Set base values for normal readings.

        Args:
            spo2: Base SpO2 percentage (readings vary around this)
            hr: Base heart rate (readings vary around this)
        """
        self._base_spo2 = spo2
        self._base_hr = hr
        logger.info(f"MockBLEReader: Set base values SpO2={spo2}% HR={hr}bpm")


class MockAVAPSMonitor:
    """Simulated AVAPS power monitor for testing.

    Simulates reading power consumption from a smart plug to determine
    if the AVAPS therapy device is running.

    The mock can be toggled between on/off states for testing.

    Attributes:
        plug_ip: Simulated plug IP (not used)
        on_threshold_watts: Power threshold for "on" state (in 5-min window)
    """

    # Simulated power readings
    POWER_OFF = 15.0   # Watts when AVAPS is off/standby
    POWER_ON = 40.0    # Watts when AVAPS is running

    def __init__(
        self,
        plug_ip: str = "0.0.0.0",
        on_threshold_watts: float = 30.0,
    ):
        """Initialize mock AVAPS monitor.

        Args:
            plug_ip: IP address (for logging, not used)
            on_threshold_watts: Power level indicating AVAPS on
        """
        self.plug_ip = plug_ip
        self.on_threshold_watts = on_threshold_watts

        # Simulation state
        self._is_on = False
        self._simulate_error = False
        self._custom_power: Optional[float] = None

        logger.info(f"MockAVAPSMonitor initialized (IP: {plug_ip})")

    @property
    def current_state(self) -> AVAPSState:
        """Current AVAPS state based on simulated power."""
        if self._simulate_error:
            return AVAPSState.UNKNOWN

        power = self._get_power()
        if power > self.on_threshold_watts:
            return AVAPSState.ON
        else:
            return AVAPSState.OFF

    async def get_power_watts(self) -> float:
        """Get simulated power reading.

        Returns:
            Power in watts (0.8 when off, 15.0 when on, or custom value)

        Raises:
            ConnectionError: If simulating network error
        """
        if self._simulate_error:
            raise ConnectionError("MockAVAPSMonitor: Simulated network error")

        # Small delay to simulate network request
        await asyncio.sleep(0.1)

        return self._get_power()

    async def is_avaps_on(self) -> bool:
        """Check if AVAPS is on.

        Returns:
            True if power is above on_threshold
        """
        power = await self.get_power_watts()
        return power > self.on_threshold_watts

    async def get_state(self) -> AVAPSState:
        """Get current AVAPS state.

        Returns:
            AVAPSState enum value
        """
        try:
            power = await self.get_power_watts()
            if power > self.on_threshold_watts:
                return AVAPSState.ON
            else:
                return AVAPSState.OFF
        except ConnectionError:
            return AVAPSState.UNKNOWN

    def _get_power(self) -> float:
        """Get current power value with small variation."""
        if self._custom_power is not None:
            return self._custom_power

        base = self.POWER_ON if self._is_on else self.POWER_OFF
        # Add small random variation
        variation = random.uniform(-0.2, 0.2)
        return max(0, base + variation)

    # Simulation control methods

    def set_on(self, on: bool = True) -> None:
        """Set AVAPS on/off state.

        Args:
            on: True for on (high power), False for off (low power)
        """
        self._is_on = on
        self._custom_power = None
        logger.info(f"MockAVAPSMonitor: Set AVAPS on={on}")

    def set_power(self, watts: float) -> None:
        """Set custom power value.

        Args:
            watts: Power value in watts
        """
        self._custom_power = watts
        logger.info(f"MockAVAPSMonitor: Set custom power={watts}W")

    def simulate_error(self, error: bool = True) -> None:
        """Simulate network error.

        Args:
            error: True to simulate error, False to clear
        """
        self._simulate_error = error
        logger.info(f"MockAVAPSMonitor: Simulating error={error}")

    def toggle(self) -> bool:
        """Toggle AVAPS on/off state.

        Returns:
            New state (True = on)
        """
        self._is_on = not self._is_on
        self._custom_power = None
        logger.info(f"MockAVAPSMonitor: Toggled to on={self._is_on}")
        return self._is_on


class MockScenarioRunner:
    """Helper class to run test scenarios with mocks.

    Provides pre-built scenarios for testing alarm conditions.
    """

    def __init__(
        self,
        ble_reader: MockBLEReader,
        avaps_monitor: MockAVAPSMonitor,
    ):
        """Initialize scenario runner.

        Args:
            ble_reader: Mock BLE reader instance
            avaps_monitor: Mock AVAPS monitor instance
        """
        self.ble = ble_reader
        self.avaps = avaps_monitor

    def scenario_normal_operation(self) -> None:
        """Set up normal operation scenario.

        - SpO2: 92-99%
        - HR: 60-90 bpm
        - AVAPS: Off
        - All connections working
        """
        self.ble.simulate_disconnect(False)
        self.ble.simulate_low_spo2(False)
        self.ble.simulate_sensor_off(False)
        self.ble.set_base_values(spo2=96, hr=72)
        self.avaps.set_on(False)
        self.avaps.simulate_error(False)
        logger.info("Scenario: Normal operation")

    def scenario_therapy_active(self) -> None:
        """Set up therapy active scenario.

        - SpO2: Normal (doesn't matter when therapy on)
        - AVAPS: On
        """
        self.scenario_normal_operation()
        self.avaps.set_on(True)
        logger.info("Scenario: Therapy active")

    def scenario_low_spo2_alarm(self, spo2_value: int = 85) -> None:
        """Set up low SpO2 alarm scenario.

        - SpO2: Below 90% (configurable)
        - AVAPS: Off
        """
        self.scenario_normal_operation()
        self.ble.simulate_low_spo2(True, value=spo2_value)
        logger.info(f"Scenario: Low SpO2 alarm (SpO2={spo2_value}%)")

    def scenario_ble_disconnect(self) -> None:
        """Set up BLE disconnect scenario.

        - BLE: Disconnected
        - AVAPS: Off
        """
        self.scenario_normal_operation()
        self.ble.simulate_disconnect(True)
        logger.info("Scenario: BLE disconnect")

    def scenario_sensor_off(self) -> None:
        """Set up sensor off scenario.

        - Sensor: Not on finger
        - AVAPS: Off
        """
        self.scenario_normal_operation()
        self.ble.simulate_sensor_off(True)
        logger.info("Scenario: Sensor off finger")

    def scenario_network_error(self) -> None:
        """Set up network error scenario.

        - AVAPS monitor: Network error
        - BLE: Connected
        """
        self.scenario_normal_operation()
        self.avaps.simulate_error(True)
        logger.info("Scenario: Network error")
