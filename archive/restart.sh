#!/bin/bash
cd "$(dirname "$0")"

# Check if systemd service is installed
if systemctl list-unit-files o2monitor.service &>/dev/null && \
   [ -f /etc/systemd/system/o2monitor.service ]; then
    echo "Using systemd service..."
    sudo systemctl restart o2monitor
    sleep 1
    sudo systemctl status o2monitor --no-pager
    echo ""
    echo "Logs: journalctl -u o2monitor -f"
else
    # Manual mode
    ./stop.sh
    sleep 2
    ./start.sh
fi
