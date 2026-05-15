#!/bin/bash
# Install O2Monitor as a systemd service

set -e

SERVICE_FILE="o2monitor.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_FILE"

echo "Installing O2Monitor service..."

# Copy service file
sudo cp "$SERVICE_FILE" "$SERVICE_PATH"
echo "  Copied service file to $SERVICE_PATH"

# Reload systemd
sudo systemctl daemon-reload
echo "  Reloaded systemd"

# Enable service (start on boot)
sudo systemctl enable o2monitor
echo "  Enabled service for boot start"

echo ""
echo "Service installed! Commands:"
echo "  sudo systemctl start o2monitor    # Start now"
echo "  sudo systemctl stop o2monitor     # Stop"
echo "  sudo systemctl restart o2monitor  # Restart"
echo "  sudo systemctl status o2monitor   # Check status"
echo "  journalctl -u o2monitor -f        # View logs"
