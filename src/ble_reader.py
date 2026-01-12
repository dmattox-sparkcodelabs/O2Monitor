"""BLE Reader for Checkme O2 Max pulse oximeter.

This module handles Bluetooth Low Energy communication with the
Wellue/Viatom Checkme O2 Max pulse oximeter device.

Uses multiprocessing to run BLE/GLib in a completely separate process,
avoiding state pollution from asyncio/D-Bus interactions.
"""

import logging
import multiprocessing as mp
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
    """

    def __init__(
        self,
        mac_address: str,
        callback: Optional[Callable[[OxiReading], None]] = None,
        error_callback: Optional[Callable[[str], None]] = None,
        read_interval: int = 10,
    ):
        self.mac_address = mac_address
        self.callback = callback
        self.error_callback = error_callback
        self.read_interval = read_interval

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

        # Use 'spawn' context for clean process state
        self._mp_context = mp.get_context('spawn')

        logger.info(f"CheckmeO2Reader initialized (MAC: {mac_address}, multiprocessing mode)")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_reading(self) -> Optional[OxiReading]:
        return self._last_reading

    @property
    def battery_level(self) -> Optional[int]:
        return self._battery_level if self._connected else None

    def run(self, num_readings: int = -1) -> List[OxiReading]:
        """Start BLE reader in subprocess and process readings."""
        self._running = True
        self._connected = False
        self._readings = []

        # Create IPC primitives
        self._queue = self._mp_context.Queue()
        self._stop_event = self._mp_context.Event()

        # Spawn worker process
        self._process = self._mp_context.Process(
            target=_ble_worker,
            args=(self.mac_address, self.read_interval, self._queue, self._stop_event),
            daemon=True,
        )
        self._process.start()
        logger.info(f"BLE worker process started (PID: {self._process.pid})")

        # Process messages from worker
        try:
            while self._running and self._process.is_alive():
                try:
                    # Non-blocking check with timeout
                    msg = self._queue.get(timeout=1.0)
                    self._handle_worker_message(msg)

                    # Check if we have enough readings
                    if num_readings > 0 and len(self._readings) >= num_readings:
                        break

                except Exception:
                    # Queue timeout - just continue
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
        self._connected = False

        if self._stop_event:
            try:
                self._stop_event.set()
            except Exception:
                pass

        process = self._process  # Local reference to avoid race conditions
        if process is not None:
            try:
                if process.is_alive():
                    # Give it a moment to clean up
                    process.join(timeout=5)
                    if process.is_alive():
                        logger.warning("Worker didn't stop gracefully, terminating...")
                        process.terminate()
                        process.join(timeout=2)
            except Exception as e:
                logger.debug(f"Error during process cleanup: {e}")

        self._process = None
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
        logger.info("Using CheckmeO2Reader (multiprocessing mode)")
        return CheckmeO2Reader(
            mac_address=config.devices.oximeter.mac_address,
            callback=callback,
            error_callback=error_callback,
            read_interval=config.devices.oximeter.read_interval_seconds,
        )
