#!/bin/bash
cd "$(dirname "$0")"

# Check if systemd service is installed
if systemctl list-unit-files o2monitor.service &>/dev/null && \
   [ -f /etc/systemd/system/o2monitor.service ]; then
    echo "Using systemd service..."
    sudo systemctl start o2monitor
    sleep 1
    sudo systemctl status o2monitor --no-pager
    echo ""
    echo "Logs: journalctl -u o2monitor -f"
else
    # Manual mode
    source venv/bin/activate
    nohup python -m src.main --config config.yaml > /tmp/o2monitor.log 2>&1 &
    echo "O2Monitor started (PID: $!)"
    echo "Logs: /tmp/o2monitor.log"
fi
