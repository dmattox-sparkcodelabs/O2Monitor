# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""BLE Reader for Checkme O2 Max pulse oximeter.

This module handles Bluetooth Low Energy communication with the
Wellue/Viatom Checkme O2 Max pulse oximeter device.

Uses multiprocessing to run BLE/GLib in a completely separate process,
avoiding state pollution from asyncio/D-Bus interactions.

Supports multiple Bluetooth adapters with automatic failover.
"""

import logging
import multiprocessing as mp
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional

from src.models import OxiReading

logger = logging.getLogger(__name__)

# Viatom/Wellue BLE characteristics
RX_UUID = "0734594a-a8e7-4b1a-a6b1-cd5243059a57"  # Receive notifications
TX_UUID = "8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3"  # Send commands


@dataclass
class AdapterInfo:
    """Information about a Bluetooth adapter."""
    name: str
    mac_address: str
    hci: Optional[str] = None  # e.g., "hci0"
    is_up: bool = False


class AdapterManager:
    """Manages multiple Bluetooth adapters with failover support.

    Handles:
    - Discovering available adapters
    - Selecting which adapter to use
    - Switching between adapters on failure
    - Bringing adapters up/down via hciconfig
    """

    def __init__(self, adapters_config: List[Dict[str, str]]):
        """Initialize with adapter configuration.

        Args:
            adapters_config: List of dicts with 'name' and 'mac_address' keys
        """
        self.configured_adapters = [
            AdapterInfo(name=a.get('name', 'Unknown'), mac_address=a.get('mac_address', '').upper())
            for a in adapters_config
        ]
        self.current_adapter_index = 0
        self.is_switching_mode = False
        self.switch_mode_start_time: Optional[float] = None

        logger.info(f"AdapterManager initialized with {len(self.configured_adapters)} adapters: "
                    f"{[a.name for a in self.configured_adapters]}")

    def discover_adapters(self) -> List[AdapterInfo]:
        """Discover available Bluetooth adapters and match with config."""
        try:
            result = subprocess.run(
                ['hciconfig', '-a'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                logger.error("Failed to run hciconfig")
                return []

            # Parse hciconfig output
            import re
            current_hci = None
            current_mac = None
            current_up = False

            for line in result.stdout.split('\n'):
                hci_match = re.match(r'^(hci\d+):', line)
                if hci_match:
                    # Save previous adapter if any
                    if current_hci and current_mac:
                        self._update_adapter_info(current_hci, current_mac, current_up)

                    current_hci = hci_match.group(1)
                    current_mac = None
                    current_up = 'UP' in line and 'RUNNING' in line
                else:
                    bd_match = re.search(r'BD Address:\s*([0-9A-Fa-f:]+)', line)
                    if bd_match:
                        current_mac = bd_match.group(1).upper()
                    if 'UP RUNNING' in line:
                        current_up = True

            # Don't forget the last adapter
            if current_hci and current_mac:
                self._update_adapter_info(current_hci, current_mac, current_up)

            return self.configured_adapters

        except Exception as e:
            logger.error(f"Error discovering adapters: {e}")
            return []

    def _update_adapter_info(self, hci: str, mac: str, is_up: bool):
        """Update adapter info based on discovered data."""
        for adapter in self.configured_adapters:
            if adapter.mac_address == mac:
                adapter.hci = hci
                adapter.is_up = is_up
                logger.debug(f"Found adapter {adapter.name} ({mac}) as {hci}, up={is_up}")
                break

    def get_current_adapter(self) -> Optional[AdapterInfo]:
        """Get the currently selected adapter."""
        if not self.configured_adapters:
            return None
        if self.current_adapter_index >= len(self.configured_adapters):
            self.current_adapter_index = 0
        return self.configured_adapters[self.current_adapter_index]

    def switch_to_next_adapter(self) -> Optional[AdapterInfo]:
        """Switch to the next available adapter.

        Returns:
            The new adapter, or None if no adapters available
        """
        if len(self.configured_adapters) < 2:
            logger.warning("Cannot switch - only one adapter configured")
            return self.get_current_adapter()

        # Refresh adapter status before switching
        self.discover_adapters()

        old_adapter = self.get_current_adapter()

        # Find next available adapter (one that has an hci device)
        attempts = 0
        while attempts < len(self.configured_adapters):
            self.current_adapter_index = (self.current_adapter_index + 1) % len(self.configured_adapters)
            new_adapter = self.get_current_adapter()

            if new_adapter and new_adapter.hci:
                # Found an available adapter
                break
            else:
                logger.warning(f"Adapter {new_adapter.name if new_adapter else 'Unknown'} not detected, skipping...")
                attempts += 1

        if attempts >= len(self.configured_adapters):
            logger.error("No adapters available!")
            return None

        new_adapter = self.get_current_adapter()
        logger.info(f"Switching adapter: {old_adapter.name if old_adapter else 'None'} -> {new_adapter.name if new_adapter else 'None'}")

        # Bring down old adapter, bring up new one
        if old_adapter and old_adapter.hci:
            self._set_adapter_state(old_adapter.hci, up=False)

        if new_adapter and new_adapter.hci:
            self._set_adapter_state(new_adapter.hci, up=True)

        return new_adapter

    def activate_adapter(self, adapter: AdapterInfo) -> bool:
        """Activate a specific adapter and deactivate others.

        Returns:
            True if successful
        """
        # Refresh adapter status
        self.discover_adapters()

        # Check if target adapter is available
        if not adapter.hci:
            logger.error(f"Adapter {adapter.name} not detected - cannot activate")
            return False

        # Bring down all other adapters
        for a in self.configured_adapters:
            if a != adapter and a.hci:
                self._set_adapter_state(a.hci, up=False)

        # Bring up the target adapter
        return self._set_adapter_state(adapter.hci, up=True)

    def _set_adapter_state(self, hci: str, up: bool) -> bool:
        """Set adapter state via hciconfig."""
        try:
            cmd = ['sudo', 'hciconfig', hci, 'up' if up else 'down']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                logger.info(f"Adapter {hci} {'up' if up else 'down'}")
                return True
            else:
                logger.error(f"Failed to set {hci} {'up' if up else 'down'}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error setting adapter state: {e}")
            return False

    def enter_switching_mode(self):
        """Enter switching mode - bouncing between adapters."""
        if not self.is_switching_mode:
            self.is_switching_mode = True
            self.switch_mode_start_time = time.time()
            logger.warning("Entering adapter switching mode")

    def exit_switching_mode(self):
        """Exit switching mode - readings resumed."""
        if self.is_switching_mode:
            self.is_switching_mode = False
            duration = time.time() - self.switch_mode_start_time if self.switch_mode_start_time else 0
            logger.info(f"Exiting adapter switching mode (was in mode for {duration:.1f}s)")
            self.switch_mode_start_time = None

    def check_adapter_health(self) -> Dict[str, bool]:
        """Check which adapters are currently available.

        Returns:
            Dict mapping adapter name to availability (True = detected)
        """
        self.discover_adapters()
        return {a.name: (a.hci is not None) for a in self.configured_adapters}

    def get_available_adapter_count(self) -> int:
        """Get count of currently available adapters."""
        return sum(1 for a in self.configured_adapters if a.hci is not None)


def _ble_worker(mac_address: str, read_interval: int, queue: mp.Queue, stop_event: mp.Event):
    """
    BLE worker function that runs in a separate process.

    This function contains all GLib/BLE logic and runs in a pristine
    process environment, avoiding any state pollution from asyncio.
    """
    import signal

    # Ignore SIGINT in worker - parent handles shutdown
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    try:
        import BLE_GATT
    except ImportError as e:
        queue.put({"type": "error", "message": f"BLE_GATT not available: {e}"})
        return

    # State
    rx_buffer = bytearray()
    last_reading_time = 0
    wait_for = -1  # Infinite

    def calc_crc(data):
        """Calculate CRC for command packet."""
        crc = 0x00
        for b in data:
            chk = (crc ^ b) & 0xFF
            crc = 0x00
            if chk & 0x01: crc ^= 0x07
            if chk & 0x02: crc ^= 0x0e
            if chk & 0x04: crc ^= 0x1c
            if chk & 0x08: crc ^= 0x38
            if chk & 0x10: crc ^= 0x70
            if chk & 0x20: crc ^= 0xe0
            if chk & 0x40: crc ^= 0xc7
            if chk & 0x80: crc ^= 0x89
        return crc

    def build_command(cmd):
        """Build command packet with header and CRC."""
        pkt = bytearray([
            0xAA,
            cmd,
            0xFF ^ cmd,
            0x00, 0x00,
            0x00, 0x00,
        ])
        pkt.append(calc_crc(pkt))
        return pkt

    def request_reading():
        """Send command 0x17 to request sensor values."""
        cmd = build_command(0x17)
        ble.char_write(TX_UUID, cmd)

    def handle_notification(value):
        """Handle incoming BLE notification."""
        nonlocal rx_buffer, last_reading_time, wait_for

        rx_buffer.extend(bytearray(value))

        # Look for complete packet (starts with 0x55)
        while len(rx_buffer) > 0 and rx_buffer[0] != 0x55:
            rx_buffer = rx_buffer[1:]

        if len(rx_buffer) < 8:
            return

        # Check payload length
        pay_len = rx_buffer[5] | (rx_buffer[6] << 8)
        total_len = pay_len + 8

        if len(rx_buffer) < total_len:
            return

        # Extract packet
        packet = rx_buffer[:total_len]
        rx_buffer = rx_buffer[total_len:]

        # Parse payload (skip 7-byte header)
        if pay_len == 0x0d:  # Sensor reading
            payload = packet[7:7+pay_len]
            process_reading(payload)

    def process_reading(payload: bytes):
        """Process sensor reading payload and send to parent."""
        nonlocal last_reading_time, wait_for

        if len(payload) < 10:
            return

        spo2 = payload[0]
        hr = payload[1]
        flag = payload[2]
        battery = payload[7]
        movement = payload[9]

        # Skip invalid readings
        if flag == 0xFF:
            return  # Sensor off
        elif flag == 0x00 and spo2 == 0 and hr == 0:
            return  # Sensor idle

        # Rate limit (one reading per second max)
        now = time.time()
        if now - last_reading_time < 1:
            return
        last_reading_time = now

        # Send reading to parent process
        reading_data = {
            "type": "reading",
            "timestamp": datetime.now().isoformat(),
            "spo2": spo2,
            "heart_rate": hr,
            "battery_level": battery,
            "movement": movement,
        }
        queue.put(reading_data)

    def periodic_request():
        """Periodically request readings (recurring timer)."""
        if stop_event.is_set():
            return False  # Stop the timer
        request_reading()
        return True  # Keep the timer running

    def check_stop():
        """Periodically check if parent wants us to stop."""
        if stop_event.is_set():
            ble.cleanup()
            return False  # Stop checking
        return True  # Keep checking

    # --- Main worker logic ---
    queue.put({"type": "status", "message": "connecting", "mac": mac_address})

    # Create BLE connection
    ble = BLE_GATT.Central(mac_address)

    # Connect with retry
    attempts = 0
    while not stop_event.is_set():
        try:
            attempts += 1
            ble.connect()
            queue.put({"type": "status", "message": "connected", "attempts": attempts})
            break
        except Exception as e:
            if attempts % 10 == 0:
                queue.put({"type": "status", "message": "retrying", "attempts": attempts})
            time.sleep(2)

    if stop_event.is_set():
        return

    # Subscribe to notifications
    ble.on_value_change(RX_UUID, handle_notification)

    # Set up GLib timers
    from gi.repository import GLib

    # Request first reading
    request_reading()

    # Set up recurring timer to request readings every read_interval seconds
    GLib.timeout_add_seconds(read_interval, periodic_request)

    # Set up periodic stop check (every 5 seconds)
    GLib.timeout_add_seconds(5, check_stop)

    queue.put({"type": "status", "message": "monitoring"})

    # Run GLib main loop (blocks until cleanup() is called)
    try:
        ble.wait_for_notifications()
    except Exception as e:
        queue.put({"type": "error", "message": str(e)})

    queue.put({"type": "status", "message": "stopped"})


class CheckmeO2Reader:
    """BLE reader that runs in a separate process.

    This class manages a worker subprocess that handles all BLE/GLib
    communication, keeping the main process free of GLib state pollution.

    Supports multiple Bluetooth adapters with automatic failover.
    """

    def __init__(
        self,
        mac_address: str,
        callback: Optional[Callable[[OxiReading], None]] = None,
        error_callback: Optional[Callable[[str], None]] = None,
        read_interval: int = 10,
        adapters_config: Optional[List[Dict[str, str]]] = None,
        switch_timeout_minutes: int = 5,
        bounce_interval_minutes: int = 1,
    ):
        self.mac_address = mac_address
        self.callback = callback
        self.error_callback = error_callback
        self.read_interval = read_interval
        self.switch_timeout_seconds = switch_timeout_minutes * 60
        self.bounce_interval_seconds = bounce_interval_minutes * 60

        # Process management
        self._process: Optional[mp.Process] = None
        self._queue: Optional[mp.Queue] = None
        self._stop_event: Optional[mp.Event] = None

        # State (updated from worker messages)
        self._connected = False
        self._running = False
        self._last_reading: Optional[OxiReading] = None
        self._last_reading_time: float = 0
        self._battery_level: int = 0
        self._readings: List[OxiReading] = []

        # Adapter management
        self._adapter_manager: Optional[AdapterManager] = None
        if adapters_config:
            self._adapter_manager = AdapterManager(adapters_config)
            self._adapter_manager.discover_adapters()

        self._last_switch_time: float = 0
        self._last_health_check: float = 0
        self._health_check_interval: int = 60  # Check adapter health every 60 seconds
        self._current_adapter_name: str = "default"

        # Use 'spawn' context for clean process state
        self._mp_context = mp.get_context('spawn')

        logger.info(f"CheckmeO2Reader initialized (MAC: {mac_address}, multiprocessing mode, "
                    f"adapters: {len(adapters_config) if adapters_config else 0})")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_reading(self) -> Optional[OxiReading]:
        return self._last_reading

    @property
    def battery_level(self) -> Optional[int]:
        return self._battery_level if self._connected else None

    @property
    def current_adapter_name(self) -> str:
        """Get the name of the currently active adapter."""
        return self._current_adapter_name

    def _select_and_activate_adapter(self):
        """Select and activate the current adapter."""
        if self._adapter_manager:
            # Refresh adapter status
            self._adapter_manager.discover_adapters()

            adapter = self._adapter_manager.get_current_adapter()

            # If current adapter not available, try to find one that is
            if adapter and not adapter.hci:
                logger.warning(f"Adapter {adapter.name} not detected, looking for available adapter...")
                for i, a in enumerate(self._adapter_manager.configured_adapters):
                    if a.hci:
                        self._adapter_manager.current_adapter_index = i
                        adapter = a
                        break

            if adapter and adapter.hci:
                if self._adapter_manager.activate_adapter(adapter):
                    self._current_adapter_name = adapter.name
                    logger.info(f"Using adapter: {adapter.name} ({adapter.mac_address})")
                else:
                    logger.error(f"Failed to activate adapter {adapter.name}")
                    self._current_adapter_name = "default"
            else:
                logger.warning("No adapters available, using system default")
                self._current_adapter_name = "default"
        else:
            self._current_adapter_name = "default"

    def _check_adapter_health(self):
        """Periodically check adapter availability."""
        if not self._adapter_manager:
            return

        now = time.time()
        if now - self._last_health_check < self._health_check_interval:
            return

        self._last_health_check = now
        health = self._adapter_manager.check_adapter_health()
        available_count = self._adapter_manager.get_available_adapter_count()

        # Log any changes in adapter availability
        for name, available in health.items():
            if not available:
                logger.warning(f"Adapter {name} not detected")

        if available_count == 0:
            logger.error("No Bluetooth adapters available!")
        elif available_count < len(self._adapter_manager.configured_adapters):
            logger.warning(f"Only {available_count}/{len(self._adapter_manager.configured_adapters)} adapters available")

    def _check_adapter_switch_needed(self) -> bool:
        """Check if we should switch adapters due to timeout.

        Returns:
            True if adapter was switched
        """
        if not self._adapter_manager or len(self._adapter_manager.configured_adapters) < 2:
            return False

        now = time.time()
        time_since_last_reading = now - self._last_reading_time

        # Determine the timeout to use
        if self._adapter_manager.is_switching_mode:
            timeout = self.bounce_interval_seconds
        else:
            timeout = self.switch_timeout_seconds

        # Check if we've exceeded the timeout
        if time_since_last_reading > timeout and (now - self._last_switch_time) > timeout:
            if not self._adapter_manager.is_switching_mode:
                self._adapter_manager.enter_switching_mode()

            logger.warning(f"No readings for {time_since_last_reading:.0f}s, switching adapter...")
            self._switch_adapter()
            return True

        return False

    def _switch_adapter(self):
        """Switch to the next adapter and restart the worker."""
        if not self._adapter_manager:
            return

        # Stop current worker
        self._stop_worker()

        # Switch to next adapter
        new_adapter = self._adapter_manager.switch_to_next_adapter()
        if new_adapter:
            self._current_adapter_name = new_adapter.name

        self._last_switch_time = time.time()

        # Start new worker
        self._start_worker()

    def _start_worker(self):
        """Start the BLE worker process."""
        self._queue = self._mp_context.Queue()
        self._stop_event = self._mp_context.Event()

        self._process = self._mp_context.Process(
            target=_ble_worker,
            args=(self.mac_address, self.read_interval, self._queue, self._stop_event),
            daemon=True,
        )
        self._process.start()
        logger.info(f"BLE worker process started (PID: {self._process.pid}, adapter: {self._current_adapter_name})")

    def _stop_worker(self):
        """Stop the BLE worker process."""
        if self._stop_event:
            try:
                self._stop_event.set()
            except Exception:
                pass

        process = self._process
        if process is not None:
            try:
                if process.is_alive():
                    process.join(timeout=3)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=2)
            except Exception as e:
                logger.debug(f"Error during worker stop: {e}")

        self._process = None
        self._connected = False

    def run(self, num_readings: int = -1) -> List[OxiReading]:
        """Start BLE reader in subprocess and process readings."""
        self._running = True
        self._connected = False
        self._readings = []
        self._last_reading_time = time.time()  # Initialize to now
        self._last_switch_time = 0

        # Select and activate initial adapter
        self._select_and_activate_adapter()

        # Start worker
        self._start_worker()

        # Process messages from worker
        try:
            while self._running:
                # Check if process died
                if self._process and not self._process.is_alive():
                    logger.warning("BLE worker process died, restarting...")
                    self._start_worker()

                try:
                    # Non-blocking check with timeout
                    msg = self._queue.get(timeout=1.0)
                    self._handle_worker_message(msg)

                    # Check if we have enough readings
                    if num_readings > 0 and len(self._readings) >= num_readings:
                        break

                except Exception:
                    # Queue timeout - check adapter health and switch if needed
                    self._check_adapter_health()
                    self._check_adapter_switch_needed()

        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            self.stop()

        return self._readings

    def _handle_worker_message(self, msg: dict):
        """Handle a message from the worker process."""
        msg_type = msg.get("type")

        if msg_type == "status":
            status = msg.get("message")
            if status == "connecting":
                logger.info(f"Connecting to {msg.get('mac')}...")
            elif status == "connected":
                self._connected = True
                self._last_reading_time = time.time()
                logger.info(f"Connected after {msg.get('attempts')} attempts")
            elif status == "retrying":
                logger.debug(f"Connection attempt {msg.get('attempts')}...")
            elif status == "monitoring":
                logger.info("Monitoring (readings: infinite)...")
            elif status == "stopped":
                self._connected = False
                logger.info("BLE worker stopped")

        elif msg_type == "reading":
            reading = OxiReading(
                timestamp=datetime.fromisoformat(msg["timestamp"]),
                spo2=msg["spo2"],
                heart_rate=msg["heart_rate"],
                battery_level=msg["battery_level"],
                movement=msg.get("movement", 0),
                is_valid=True,
            )

            self._last_reading = reading
            self._last_reading_time = time.time()
            self._battery_level = reading.battery_level
            self._readings.append(reading)

            # Exit switching mode if we were in it - we got a reading!
            if self._adapter_manager and self._adapter_manager.is_switching_mode:
                self._adapter_manager.exit_switching_mode()
                logger.info(f"Readings resumed on adapter: {self._current_adapter_name}")

            logger.info(f"Reading: SpO2={reading.spo2}%, HR={reading.heart_rate}bpm, Battery={reading.battery_level}%")

            # Call user callback
            if self.callback:
                try:
                    self.callback(reading)
                except Exception as e:
                    logger.error(f"Error in callback: {e}")

        elif msg_type == "error":
            error_msg = msg.get("message", "Unknown error")
            logger.error(f"BLE worker error: {error_msg}")
            if self.error_callback:
                self.error_callback(error_msg)

    def stop(self):
        """Stop the BLE reader subprocess."""
        logger.info("Stopping BLE reader...")
        self._running = False

        self._stop_worker()

        self._queue = None
        self._stop_event = None
        logger.info("BLE reader stopped")

    def disconnect(self):
        """Alias for stop()."""
        self.stop()


def get_reader(config, callback=None, error_callback=None):
    """Factory function to get appropriate reader based on config."""
    if config.mock_mode:
        from src.mocks import MockBLEReader
        logger.info("Using MockBLEReader (mock_mode=True)")
        return MockBLEReader(
            mac_address=config.devices.oximeter.mac_address,
            callback=callback,
            read_interval=config.devices.oximeter.read_interval_seconds,
        )
    else:
        # Build adapters config from bluetooth section
        adapters_config = None
        if hasattr(config, 'bluetooth') and config.bluetooth.adapters:
            adapters_config = [
                {'name': a.name, 'mac_address': a.mac_address}
                for a in config.bluetooth.adapters
            ]

        # Get timing config
        read_interval = config.bluetooth.read_interval_seconds if hasattr(config, 'bluetooth') else config.devices.oximeter.read_interval_seconds
        switch_timeout = config.bluetooth.switch_timeout_minutes if hasattr(config, 'bluetooth') else 5
        bounce_interval = config.bluetooth.bounce_interval_minutes if hasattr(config, 'bluetooth') else 1

        logger.info(f"Using CheckmeO2Reader (multiprocessing mode, {len(adapters_config) if adapters_config else 0} adapters)")
        return CheckmeO2Reader(
            mac_address=config.devices.oximeter.mac_address,
            callback=callback,
            error_callback=error_callback,
            read_interval=read_interval,
            adapters_config=adapters_config,
            switch_timeout_minutes=switch_timeout,
            bounce_interval_minutes=bounce_interval,
        )
