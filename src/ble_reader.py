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
"""

import logging
import multiprocessing as mp
import subprocess
import time
from datetime import datetime
from typing import Callable, List, Optional

from src.models import OxiReading

logger = logging.getLogger(__name__)

# Viatom/Wellue BLE characteristics
RX_UUID = "0734594a-a8e7-4b1a-a6b1-cd5243059a57"  # Receive notifications
TX_UUID = "8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3"  # Send commands


def _ble_worker(mac_address: str, read_interval: int, queue: mp.Queue, stop_event: mp.Event):
    """
    BLE worker function that runs in a separate process.

    This function contains all GLib/BLE logic and runs in a pristine
    process environment, avoiding any state pollution from asyncio.
    """
    import signal
    import subprocess

    # Ignore SIGINT in worker - parent handles shutdown
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    # Connection timeout handler
    class ConnectionTimeout(Exception):
        pass

    def timeout_handler(signum, frame):
        raise ConnectionTimeout("BLE connection timed out")

    signal.signal(signal.SIGALRM, timeout_handler)

    # --- HELPER: Force Scan on Demand ---
    def force_device_discovery(mac):
        """
        Force BlueZ to find the device by scanning briefly.
        This repopulates the BlueZ internal cache if the adapter was reset.
        """
        queue.put({"type": "status", "message": "scanning", "mac": mac})
        try:
            # Run scan for 5 seconds then kill it
            # Using 'timeout' command to ensure it doesn't hang
            subprocess.run(
                "timeout 5s bash -c 'echo -e \"scan on\" | bluetoothctl'",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Small settling time for BlueZ to process advertisements
            time.sleep(1)
        except Exception as e:
            queue.put({"type": "error", "message": f"Scan failed: {e}"})

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

    # Set 45-second timeout for connection (allows for scan time)
    signal.alarm(45)

    try:
        # Create BLE connection
        ble = BLE_GATT.Central(mac_address)

        # Connect with Retry Logic
        try:
            # Attempt 1: Direct Connect (Optimistic)
            ble.connect()
        except Exception:
            # Attempt 2: Scan first, then Connect
            # This fixes the "Device Not Found" error if cache was wiped
            queue.put({"type": "status", "message": "retrying_with_scan"})
            
            # Reset alarm temporarily so we don't timeout during scan
            signal.alarm(0)
            force_device_discovery(mac_address)
            signal.alarm(45)  # Re-arm alarm
            
            ble.connect()

        queue.put({"type": "status", "message": "connected", "attempts": 1})

    except ConnectionTimeout:
        queue.put({"type": "error", "message": "Connection timed out after 45s"})
        return
    except Exception as e:
        queue.put({"type": "error", "message": str(e)})
        return
    finally:
        # Cancel the alarm
        signal.alarm(0)

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
    """

    def __init__(
        self,
        mac_address: str,
        callback: Optional[Callable[[OxiReading], None]] = None,
        error_callback: Optional[Callable[[str], None]] = None,
        read_interval: int = 10,
        respawn_delay_seconds: int = 15,
    ):
        self.mac_address = mac_address
        self.callback = callback
        self.error_callback = error_callback
        self.read_interval = read_interval
        self.respawn_delay_seconds = respawn_delay_seconds

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

        # Connection health tracking
        self._consecutive_failures: int = 0
        self._disconnect_start_time: Optional[float] = None
        self._last_successful_reading_time: Optional[float] = None

        # Use 'spawn' context for clean process state
        self._mp_context = mp.get_context('spawn')

        logger.info(f"CheckmeO2Reader initialized (MAC: {mac_address}, multiprocessing mode)")

    def _get_backoff_delay(self) -> int:
        """Calculate exponential backoff delay based on consecutive failures.

        Returns delay in seconds:
        - Attempt 1: 5s
        - Attempt 2: 15s
        - Attempt 3: 30s
        - Attempt 4: 60s
        - Attempt 5+: 60s (max)

        This prevents overwhelming flaky BLE peripherals that need time to recover.
        """
        backoff_schedule = [5, 15, 30, 60]
        index = min(self._consecutive_failures - 1, len(backoff_schedule) - 1)
        index = max(0, index)  # Ensure non-negative
        return backoff_schedule[index]

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_reading(self) -> Optional[OxiReading]:
        return self._last_reading

    @property
    def battery_level(self) -> Optional[int]:
        return self._battery_level if self._connected else None

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
        logger.info(f"BLE worker process started (PID: {self._process.pid})")

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
        self._consecutive_failures = 0
        self._disconnect_start_time = None

        # Start worker
        self._start_worker()

        # Process messages from worker
        try:
            while self._running:
                # Check if process died
                if self._process and not self._process.is_alive():
                    self._consecutive_failures += 1

                    # Track when disconnect started
                    if self._disconnect_start_time is None:
                        self._disconnect_start_time = time.time()

                    # Calculate disconnect duration
                    disconnect_duration = time.time() - self._disconnect_start_time
                    disconnect_mins = int(disconnect_duration / 60)
                    disconnect_secs = int(disconnect_duration % 60)

                    # Calculate exponential backoff delay
                    backoff_delay = self._get_backoff_delay()

                    # Log with escalating severity based on consecutive failures
                    if self._consecutive_failures == 1:
                        logger.warning(f"BLE worker process died, waiting {backoff_delay}s before restarting...")
                    elif self._consecutive_failures == 5:
                        logger.warning(f"BLE connection issues: 5 consecutive failures over {disconnect_mins}m {disconnect_secs}s, backing off to {backoff_delay}s")
                    elif self._consecutive_failures == 10:
                        logger.error(f"BLE connection issues: 10 consecutive failures over {disconnect_mins}m {disconnect_secs}s - adapter may need reset")
                    elif self._consecutive_failures == 20:
                        logger.error(f"BLE connection issues: 20 consecutive failures over {disconnect_mins}m {disconnect_secs}s - check device and adapter")
                    elif self._consecutive_failures % 20 == 0:
                        logger.error(f"BLE connection issues: {self._consecutive_failures} consecutive failures over {disconnect_mins}m {disconnect_secs}s")
                    else:
                        logger.warning(f"BLE worker died (failure #{self._consecutive_failures}, outage: {disconnect_mins}m {disconnect_secs}s), waiting {backoff_delay}s...")

                    time.sleep(backoff_delay)
                    self._start_worker()

                try:
                    # Non-blocking check with timeout
                    msg = self._queue.get(timeout=1.0)
                    self._handle_worker_message(msg)

                    # Check if we have enough readings
                    if num_readings > 0 and len(self._readings) >= num_readings:
                        break

                except Exception:
                    # Queue timeout - nothing to do
                    pass

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
                # Log extra detail if recovering from failures
                if self._consecutive_failures > 0:
                    logger.info(f"Connected after {msg.get('attempts')} attempts (recovering from {self._consecutive_failures} failures)")
                else:
                    logger.info(f"Connected after {msg.get('attempts')} attempts")
            elif status == "retrying_with_scan":
                logger.debug(f"Direct connection failed, forcing scan to repopulate cache...")
            elif status == "scanning":
                logger.debug("Scanning for device...")
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

            # Log recovery summary if we had failures
            if self._consecutive_failures > 0:
                outage_duration = 0
                if self._disconnect_start_time:
                    outage_duration = time.time() - self._disconnect_start_time
                outage_mins = int(outage_duration / 60)
                outage_secs = int(outage_duration % 60)
                logger.info(f"CONNECTION RECOVERED: {self._consecutive_failures} failures over {outage_mins}m {outage_secs}s outage")

                # Reset tracking
                self._consecutive_failures = 0
                self._disconnect_start_time = None

            # Track last successful reading time
            self._last_successful_reading_time = time.time()

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
        # Get timing config
        read_interval = config.bluetooth.read_interval_seconds if hasattr(config, 'bluetooth') else config.devices.oximeter.read_interval_seconds
        respawn_delay = config.bluetooth.respawn_delay_seconds if hasattr(config, 'bluetooth') else 15

        logger.info("Using CheckmeO2Reader (multiprocessing mode)")
        return CheckmeO2Reader(
            mac_address=config.devices.oximeter.mac_address,
            callback=callback,
            error_callback=error_callback,
            read_interval=read_interval,
            respawn_delay_seconds=respawn_delay,
        )
