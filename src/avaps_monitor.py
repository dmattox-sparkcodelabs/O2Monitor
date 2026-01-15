# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""AVAPS Monitor - Monitors BiPAP therapy device power state.

This module monitors the power consumption of an AVAPS (BiPAP) therapy device
via a TP-Link Kasa KP115 smart plug with energy monitoring.

The power reading is used to determine if the patient is receiving therapy:
- High power (>3W): AVAPS is running, therapy active
- Low power (<2W): AVAPS is off/standby

This information is used by the state machine to decide whether to
trigger SpO2 alarms (alarms are suppressed when therapy is active).

Usage:
    from src.avaps_monitor import AVAPSMonitor, get_monitor
    from src.models import AVAPSState

    # Direct usage
    monitor = AVAPSMonitor(plug_ip="192.168.1.100")
    power = await monitor.get_power_watts()
    state = await monitor.get_state()

    # Or use factory function with config
    monitor = get_monitor(config)
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

# Add project root to path when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kasa import Discover, KasaException

from src.models import AVAPSState

logger = logging.getLogger(__name__)


class AVAPSMonitor:
    """Monitors AVAPS therapy device power state via Kasa smart plug.

    Uses a TP-Link Kasa KP115 (or similar energy-monitoring plug) to
    read power consumption and determine if the AVAPS is running.

    Attributes:
        plug_ip: IP address of the Kasa smart plug
        on_threshold_watts: Power level above which AVAPS is considered ON
        off_threshold_watts: Power level below which AVAPS is considered OFF
        current_state: Current AVAPS state based on last reading
    """

    # Default thresholds (can be overridden in config)
    DEFAULT_ON_THRESHOLD = 3.0   # Watts - AVAPS running
    DEFAULT_OFF_THRESHOLD = 2.0  # Watts - AVAPS off/standby

    # Cache duration to avoid hammering the plug
    CACHE_DURATION_SECONDS = 2.0

    def __init__(
        self,
        plug_ip: str,
        on_threshold_watts: float = DEFAULT_ON_THRESHOLD,
        off_threshold_watts: float = DEFAULT_OFF_THRESHOLD,
    ):
        """Initialize AVAPS monitor.

        Args:
            plug_ip: IP address of the Kasa KP115 smart plug
            on_threshold_watts: Power threshold for ON state (default 3.0W)
            off_threshold_watts: Power threshold for OFF state (default 2.0W)
        """
        self.plug_ip = plug_ip
        self.on_threshold_watts = on_threshold_watts
        self.off_threshold_watts = off_threshold_watts

        # Kasa device
        self._plug: Optional[SmartPlug] = None
        self._initialized = False

        # State tracking
        self._current_state = AVAPSState.UNKNOWN
        self._last_power: Optional[float] = None
        self._last_read_time: float = 0
        self._last_error: Optional[str] = None
        self._consecutive_errors: int = 0

        logger.info(
            f"AVAPSMonitor initialized (IP: {plug_ip}, "
            f"on>{on_threshold_watts}W, off<{off_threshold_watts}W)"
        )

    @property
    def current_state(self) -> AVAPSState:
        """Current AVAPS state based on last reading."""
        return self._current_state

    @property
    def last_power(self) -> Optional[float]:
        """Last power reading in watts, or None if never read."""
        return self._last_power

    @property
    def last_error(self) -> Optional[str]:
        """Last error message, if any."""
        return self._last_error

    async def _ensure_initialized(self) -> bool:
        """Ensure plug is initialized and updated.

        Returns:
            True if plug is ready, False on error
        """
        try:
            if self._plug is None:
                # Use Discover.discover_single for modern python-kasa API
                self._plug = await Discover.discover_single(self.plug_ip)

            # Update device state
            await self._plug.update()
            self._initialized = True
            self._consecutive_errors = 0
            return True

        except KasaException as e:
            self._last_error = f"Device error: {e}"
            self._consecutive_errors += 1
            logger.warning(f"Kasa device error: {e}")
            return False

        except Exception as e:
            self._last_error = f"Connection error: {e}"
            self._consecutive_errors += 1
            logger.warning(f"Kasa connection error: {e}")
            return False

    async def get_power_watts(self) -> float:
        """Get current power consumption in watts.

        Returns:
            Power in watts

        Raises:
            ConnectionError: If unable to connect to plug
        """
        # Check cache
        now = time.time()
        if (self._last_power is not None and
                now - self._last_read_time < self.CACHE_DURATION_SECONDS):
            return self._last_power

        # Get fresh reading
        if not await self._ensure_initialized():
            raise ConnectionError(self._last_error or "Failed to connect to Kasa plug")

        try:
            # Get emeter (energy meter) realtime data
            # Modern python-kasa uses modules for energy monitoring
            if hasattr(self._plug, 'modules') and 'Energy' in self._plug.modules:
                energy = self._plug.modules['Energy']
                power = energy.current_consumption or 0.0
            elif hasattr(self._plug, 'emeter_realtime'):
                # Fallback to older API
                emeter = self._plug.emeter_realtime
                power = emeter.get("power", 0.0) if isinstance(emeter, dict) else 0.0
            else:
                power = 0.0
                logger.warning("Device does not have energy monitoring capability")

            self._last_power = power
            self._last_read_time = now
            self._last_error = None

            logger.debug(f"Power reading: {power:.2f}W")
            return power

        except KasaException as e:
            self._last_error = str(e)
            self._consecutive_errors += 1
            logger.error(f"Error reading power: {e}")
            raise ConnectionError(f"Failed to read power: {e}")

    async def is_avaps_on(self) -> bool:
        """Check if AVAPS is currently on (therapy active).

        Returns:
            True if power is above on_threshold

        Raises:
            ConnectionError: If unable to read power
        """
        power = await self.get_power_watts()
        return power > self.on_threshold_watts

    async def get_state(self) -> AVAPSState:
        """Get current AVAPS state.

        Uses hysteresis to prevent oscillation at threshold boundaries:
        - ON: power > on_threshold (3W default)
        - OFF: power < off_threshold (2W default)
        - UNKNOWN: power in between, or on error

        Returns:
            AVAPSState enum value
        """
        try:
            power = await self.get_power_watts()

            if power > self.on_threshold_watts:
                self._current_state = AVAPSState.ON
            elif power <= self.off_threshold_watts:
                self._current_state = AVAPSState.OFF
            # else: keep current state (hysteresis)

            return self._current_state

        except ConnectionError:
            self._current_state = AVAPSState.UNKNOWN
            return AVAPSState.UNKNOWN

    async def get_plug_info(self) -> dict:
        """Get information about the smart plug.

        Returns:
            Dict with plug info (alias, model, features, etc.)
        """
        if not await self._ensure_initialized():
            return {"error": self._last_error}

        # Check for energy monitoring capability
        has_emeter = (
            hasattr(self._plug, 'modules') and 'Energy' in self._plug.modules
        ) or getattr(self._plug, 'has_emeter', False)

        return {
            "alias": self._plug.alias,
            "model": self._plug.model,
            "host": self._plug.host,
            "is_on": self._plug.is_on,
            "has_emeter": has_emeter,
        }

    async def close(self) -> None:
        """Close connection to plug."""
        # python-kasa doesn't require explicit close,
        # but we reset state for cleanliness
        self._plug = None
        self._initialized = False
        logger.debug("AVAPSMonitor closed")


async def discover_plugs() -> list:
    """Discover Kasa devices on the local network.

    Returns:
        List of discovered devices with their info
    """
    logger.info("Discovering Kasa devices...")
    devices = await Discover.discover()

    results = []
    for ip, device in devices.items():
        await device.update()
        # Check for energy monitoring capability
        has_emeter = (
            hasattr(device, 'modules') and 'Energy' in device.modules
        ) or getattr(device, 'has_emeter', False)
        # Check if it's a plug
        is_plug = getattr(device, 'is_plug', False) or 'Plug' in type(device).__name__

        results.append({
            "ip": ip,
            "alias": device.alias,
            "model": device.model,
            "has_emeter": has_emeter,
            "is_plug": is_plug,
        })
        logger.info(f"Found: {device.alias} ({device.model}) at {ip}")

    return results


def get_monitor(config, use_mock: Optional[bool] = None):
    """Factory function to get appropriate monitor based on config.

    Args:
        config: Config object with mock_mode and device settings
        use_mock: Override config.mock_mode if specified

    Returns:
        AVAPSMonitor or MockAVAPSMonitor depending on config
    """
    mock_mode = use_mock if use_mock is not None else config.mock_mode

    if mock_mode:
        from src.mocks import MockAVAPSMonitor
        logger.info("Using MockAVAPSMonitor (mock_mode=True)")
        return MockAVAPSMonitor(
            plug_ip=config.devices.smart_plug.ip_address,
            on_threshold_watts=config.thresholds.avaps.on_watts,
            off_threshold_watts=config.thresholds.avaps.off_watts,
        )
    else:
        logger.info("Using AVAPSMonitor (real hardware)")
        return AVAPSMonitor(
            plug_ip=config.devices.smart_plug.ip_address,
            on_threshold_watts=config.thresholds.avaps.on_watts,
            off_threshold_watts=config.thresholds.avaps.off_watts,
        )


# Command-line interface for testing
if __name__ == "__main__":
    import argparse
    import sys
    import os

    # Add project root to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    parser = argparse.ArgumentParser(description="Test AVAPS monitor")
    parser.add_argument("--ip", help="Plug IP address")
    parser.add_argument("--discover", action="store_true",
                        help="Discover Kasa devices on network")
    parser.add_argument("-n", "--num", type=int, default=5,
                        help="Number of readings (default: 5)")
    parser.add_argument("-i", "--interval", type=float, default=2.0,
                        help="Seconds between readings (default: 2)")
    args = parser.parse_args()

    async def main():
        if args.discover:
            print("=" * 50)
            print("Discovering Kasa devices...")
            print("=" * 50)
            devices = await discover_plugs()
            if devices:
                print(f"\nFound {len(devices)} device(s):")
                for d in devices:
                    emeter = "Yes" if d["has_emeter"] else "No"
                    print(f"  {d['alias']} ({d['model']}) - {d['ip']} - Energy Monitor: {emeter}")
            else:
                print("No devices found")
            return

        if not args.ip:
            print("Error: --ip required (or use --discover to find devices)")
            sys.exit(1)

        print("=" * 50)
        print("AVAPS Monitor Test")
        print("=" * 50)
        print(f"Plug IP: {args.ip}")
        print(f"Readings: {args.num}")
        print(f"Interval: {args.interval} seconds")
        print()

        monitor = AVAPSMonitor(plug_ip=args.ip)

        # Get plug info
        info = await monitor.get_plug_info()
        if "error" not in info:
            print(f"Plug: {info['alias']} ({info['model']})")
            print(f"Energy Monitor: {'Yes' if info['has_emeter'] else 'No'}")
            print()

        # Take readings
        for i in range(args.num):
            try:
                power = await monitor.get_power_watts()
                state = await monitor.get_state()
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"{ts} Power: {power:6.2f}W - AVAPS: {state.value.upper()}")
            except ConnectionError as e:
                print(f"Error: {e}")

            if i < args.num - 1:
                await asyncio.sleep(args.interval)

        print()
        print("=" * 50)
        print("Complete.")
        print("=" * 50)

    asyncio.run(main())
