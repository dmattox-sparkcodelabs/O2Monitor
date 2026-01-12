#!/home/dmattox/projects/O2Monitor/venv/bin/python3
"""
Working BLE test for Checkme O2 Max.

NOTE: Run with: ./test_working.py  OR  source venv/bin/activate && python test_working.py

This script successfully connects and reads SpO2/HR data.
Based on the ble_spo2 project approach using BLE_GATT library.

Usage:
    python test_working.py [MAC_ADDRESS] [NUM_READINGS] [INTERVAL_SECONDS]

Example:
    python test_working.py C8:F1:6B:56:7B:F1 10 10
"""

import BLE_GATT
import sys
import time
import signal

# Default device MAC - update for your device
DEFAULT_MAC = "C8:F1:6B:56:7B:F1"

# Viatom/Wellue BLE characteristics
RX_UUID = "0734594a-a8e7-4b1a-a6b1-cd5243059a57"  # Receive notifications
TX_UUID = "8b00ace7-eb0b-49b0-bbe9-9aee0a26e1a3"  # Send commands


class CheckmeO2Reader:
    def __init__(self, mac_address, read_interval=10):
        self.mac = mac_address
        self.ble = BLE_GATT.Central(mac_address)
        self.rx_buffer = bytearray()
        self.readings = []
        self.wait_for = 0
        self.read_interval = read_interval  # Seconds between readings
        self.last_reading_time = 0  # Prevent duplicate readings

    def connect(self):
        """Connect with retry logic."""
        print(f"Connecting to {self.mac}...")
        while True:
            try:
                self.ble.connect()
                print("Connected!")
                return True
            except Exception as e:
                print("Wait")
                time.sleep(2)

    def calc_crc(self, data):
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

    def build_command(self, cmd):
        """Build command packet with header and CRC."""
        pkt = bytearray([
            0xAA,           # Start byte
            cmd,            # Command
            0xFF ^ cmd,     # Command complement
            0x00, 0x00,     # Block ID
            0x00, 0x00,     # Payload length (0 for simple commands)
        ])
        pkt.append(self.calc_crc(pkt))
        return pkt

    def request_reading(self):
        """Send command 0x17 to request sensor values."""
        cmd = self.build_command(0x17)
        self.ble.char_write(TX_UUID, cmd)

    def parse_reading(self, payload):
        """Parse sensor reading from payload."""
        if len(payload) < 10:
            return None

        spo2 = payload[0]
        hr = payload[1]
        flag = payload[2]  # 0xFF = sensor off
        batt = payload[7]
        moves = payload[9]

        if flag == 0xFF:
            return {"status": "sensor_off"}
        elif flag == 0x00 and spo2 == 0 and hr == 0:
            return {"status": "idle"}
        else:
            return {
                "status": "ok",
                "spo2": spo2,
                "hr": hr,
                "battery": batt,
                "moves": moves,
            }

    def handle_notification(self, value):
        """Handle incoming BLE notification."""
        self.rx_buffer.extend(bytearray(value))

        # Look for complete packet (starts with 0x55)
        while len(self.rx_buffer) > 0 and self.rx_buffer[0] != 0x55:
            self.rx_buffer = self.rx_buffer[1:]

        if len(self.rx_buffer) < 8:
            return

        # Check payload length
        pay_len = self.rx_buffer[5] | (self.rx_buffer[6] << 8)
        total_len = pay_len + 8

        if len(self.rx_buffer) < total_len:
            return

        # Extract packet
        packet = self.rx_buffer[:total_len]
        self.rx_buffer = self.rx_buffer[total_len:]

        # Parse payload (skip 7-byte header)
        if pay_len == 0x0d:  # Sensor reading
            payload = packet[7:7+pay_len]
            reading = self.parse_reading(payload)

            if reading and reading.get("status") == "ok":
                # Only record one reading per interval (ignore duplicates)
                now = time.time()
                if now - self.last_reading_time >= 1:  # At least 1 sec since last
                    self.last_reading_time = now
                    ts = time.strftime('%H:%M:%S')
                    print(f"{ts} SpO2: {reading['spo2']}%, HR: {reading['hr']} bpm, "
                          f"Battery: {reading['battery']}%")
                    self.readings.append(reading)

                    # Decrement counter
                    if self.wait_for > 0:
                        self.wait_for -= 1
                        if self.wait_for == 0:
                            self.ble.cleanup()
                            return

                    # Request next reading after delay
                    if self.wait_for != 0:
                        from gi.repository import GLib
                        GLib.timeout_add_seconds(self.read_interval, self._delayed_request)

    def _delayed_request(self):
        """Request reading after delay (called by GLib timer)."""
        if self.wait_for != 0:
            self.request_reading()
        return False  # Don't repeat timer

    def run(self, num_readings=-1):
        """Main monitoring loop."""
        self.connect()

        # Subscribe to notifications
        self.ble.on_value_change(RX_UUID, self.handle_notification)

        # Set up counter (-1 = infinite)
        self.wait_for = num_readings

        # Request first reading
        self.request_reading()

        # Handle Ctrl+C
        def signal_handler(sig, frame):
            print("\nStopping...")
            self.ble.cleanup()
            sys.exit(0)
        signal.signal(signal.SIGINT, signal_handler)

        # Run event loop
        print(f"Monitoring (readings: {'infinite' if num_readings < 0 else num_readings})...")
        self.ble.wait_for_notifications()

        return self.readings


if __name__ == "__main__":
    mac = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MAC
    num = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    interval = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    print("=" * 50)
    print("Checkme O2 Max BLE Test")
    print("=" * 50)
    print(f"Device: {mac}")
    print(f"Readings: {num}")
    print(f"Interval: {interval} seconds")
    print("")

    reader = CheckmeO2Reader(mac, read_interval=interval)
    readings = reader.run(num)

    print("")
    print("=" * 50)
    print(f"Complete. Got {len(readings)} readings.")
    print("=" * 50)
