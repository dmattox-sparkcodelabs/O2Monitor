#!/bin/bash
# =============================================================================
# O2Monitor Installation Script
# Sets up O2Monitor on a fresh Raspberry Pi
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "  O2Monitor Installation Script"
echo "=============================================="
echo ""

# Check if running as root (we don't want that)
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Please run as regular user, not root${NC}"
    exit 1
fi

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${YELLOW}Step 1: Checking prerequisites...${NC}"

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 not found. Install with: sudo apt install python3${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "  ✓ $PYTHON_VERSION"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}pip3 not found. Install with: sudo apt install python3-pip${NC}"
    exit 1
fi
echo "  ✓ pip3 installed"

# Check BlueZ
if ! command -v bluetoothctl &> /dev/null; then
    echo -e "${RED}BlueZ not found. Install with: sudo apt install bluez${NC}"
    exit 1
fi
echo "  ✓ BlueZ installed"

# Check for required system packages
echo ""
echo -e "${YELLOW}Step 2: Checking system packages...${NC}"

PACKAGES_NEEDED=""

# Check for GLib/PyGObject (needed for BLE)
if ! python3 -c "import gi" 2>/dev/null; then
    PACKAGES_NEEDED="$PACKAGES_NEEDED python3-gi"
fi

# Check for SDL2 mixer (needed for audio)
if ! dpkg -l libsdl2-mixer-2.0-0 &>/dev/null; then
    PACKAGES_NEEDED="$PACKAGES_NEEDED libsdl2-mixer-2.0-0"
fi

# Check for espeak (needed for TTS)
if ! command -v espeak &> /dev/null; then
    PACKAGES_NEEDED="$PACKAGES_NEEDED espeak"
fi

if [ -n "$PACKAGES_NEEDED" ]; then
    echo "  Installing missing packages:$PACKAGES_NEEDED"
    sudo apt update
    sudo apt install -y $PACKAGES_NEEDED
else
    echo "  ✓ All system packages installed"
fi

# Create virtual environment
echo ""
echo -e "${YELLOW}Step 3: Setting up Python virtual environment...${NC}"

if [ ! -d "venv" ]; then
    echo "  Creating venv with system-site-packages (needed for GLib)..."
    python3 -m venv --system-site-packages venv
    echo "  ✓ Virtual environment created"
else
    echo "  ✓ Virtual environment already exists"
fi

# Activate and install dependencies
echo ""
echo -e "${YELLOW}Step 4: Installing Python dependencies...${NC}"

source venv/bin/activate
pip install --upgrade pip > /dev/null

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "  ✓ Dependencies installed"
else
    echo -e "${RED}requirements.txt not found${NC}"
    exit 1
fi

# Create data directory
echo ""
echo -e "${YELLOW}Step 5: Creating data directories...${NC}"

mkdir -p data logs
echo "  ✓ Created data/ and logs/"

# Check for config file
echo ""
echo -e "${YELLOW}Step 6: Checking configuration...${NC}"

if [ ! -f "config.yaml" ]; then
    if [ -f "config.example.yaml" ]; then
        cp config.example.yaml config.yaml
        echo "  ✓ Created config.yaml from example"
        echo -e "${YELLOW}  ⚠ Edit config.yaml to set your device MAC, passwords, etc.${NC}"
    else
        echo -e "${RED}  No config.yaml or config.example.yaml found${NC}"
        echo "  You'll need to create config.yaml manually"
    fi
else
    echo "  ✓ config.yaml exists"
fi

# Check for acknowledgment file
echo ""
echo -e "${YELLOW}Step 7: Checking acknowledgment file...${NC}"

ACKNOWLEDGMENT_FILE="ACKNOWLEDGED_NOT_FOR_MEDICAL_USE.txt"
if [ ! -f "$ACKNOWLEDGMENT_FILE" ]; then
    echo -e "${YELLOW}  ⚠ You must create $ACKNOWLEDGMENT_FILE before running${NC}"
    echo "  Contents must include: 'I understand this is not a medical device'"
else
    echo "  ✓ Acknowledgment file exists"
fi

# Trust BLE device
echo ""
echo -e "${YELLOW}Step 8: Bluetooth setup...${NC}"

# Check if MAC address is configured
if [ -f "config.yaml" ]; then
    MAC=$(grep -oP 'mac_address:\s*"\K[^"]+' config.yaml 2>/dev/null || echo "")
    if [ -n "$MAC" ] && [ "$MAC" != "XX:XX:XX:XX:XX:XX" ]; then
        echo "  Oximeter MAC: $MAC"
        echo "  To trust the device, run:"
        echo "    bluetoothctl trust $MAC"
    else
        echo "  ⚠ Configure oximeter MAC address in config.yaml"
    fi
else
    echo "  ⚠ Configure config.yaml first"
fi

# Install systemd service
echo ""
echo -e "${YELLOW}Step 9: Installing systemd service...${NC}"

if [ -f "o2monitor.service" ]; then
    read -p "  Install systemd service for auto-start? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ./install-service.sh
    else
        echo "  Skipped. Run ./install-service.sh later if needed."
    fi
else
    echo "  ⚠ o2monitor.service not found"
fi

# Done!
echo ""
echo "=============================================="
echo -e "${GREEN}  Installation Complete!${NC}"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Edit config.yaml with your settings:"
echo "     - Oximeter MAC address"
echo "     - Kasa smart plug IP"
echo "     - Web dashboard password"
echo "     - PagerDuty/Healthchecks keys"
echo ""
echo "  2. Create acknowledgment file:"
echo "     echo 'I understand this is not a medical device' > $ACKNOWLEDGMENT_FILE"
echo ""
echo "  3. Trust your oximeter in Bluetooth:"
echo "     bluetoothctl trust <MAC_ADDRESS>"
echo ""
echo "  4. Start the monitor:"
echo "     ./start.sh"
echo ""
echo "  5. Access dashboard at:"
echo "     http://$(hostname -I | awk '{print $1}'):5000"
echo ""
