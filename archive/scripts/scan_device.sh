#!/bin/bash
# Scan for O2 device to populate BlueZ cache
MAC="${1:-D4:30:77:4B:0F:C7}"
TIMEOUT="${2:-10}"

echo "Scanning for $MAC..."

# Tune BLE connection parameters for better stability with weak signals
# supervision_timeout: time before kernel gives up on connection (unit: 10ms, 600 = 6s)
# conn_max_interval: max connection interval (unit: 1.25ms)
if [ -d /sys/kernel/debug/bluetooth/hci0 ]; then
    echo 600 > /sys/kernel/debug/bluetooth/hci0/supervision_timeout 2>/dev/null
    echo 600 > /sys/kernel/debug/bluetooth/hci0/conn_max_interval 2>/dev/null
    echo "BLE connection parameters tuned"
fi

# Scan to populate BlueZ cache (don't remove - keep existing cache warm)
(
    sleep 1
    echo "scan on"
    sleep $TIMEOUT
    echo "scan off"
    echo "quit"
) | bluetoothctl 2>&1 | grep -q "$MAC"

if [ $? -eq 0 ]; then
    echo "Device found"
    exit 0
else
    echo "Device not found (will retry in app)"
    exit 0  # Don't fail - app has retry logic
fi
