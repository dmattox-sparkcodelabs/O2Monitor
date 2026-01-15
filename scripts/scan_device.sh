#!/bin/bash
# Scan for O2 device to populate BlueZ cache
MAC="${1:-C8:F1:6B:56:7B:F1}"
TIMEOUT="${2:-10}"

echo "Scanning for $MAC..."

# Use bluetoothctl with the correct adapter
(
    sleep 1
    echo "select 10:A5:62:EC:E8:A5"
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
