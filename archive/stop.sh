#!/bin/bash
cd "$(dirname "$0")"

# Check if systemd service is installed
if systemctl list-unit-files o2monitor.service &>/dev/null && \
   [ -f /etc/systemd/system/o2monitor.service ]; then
    echo "Using systemd service..."
    sudo systemctl stop o2monitor
    echo "O2Monitor stopped"
else
    # Manual mode - kill processes
    pkill -9 -f "src.main"
    pkill -9 -f "python.*main"
    pkill -9 -f "multiprocessing"
    sleep 1
    killall -9 python 2>/dev/null
    echo "O2Monitor stopped"
fi
