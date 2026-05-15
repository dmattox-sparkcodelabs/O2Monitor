#!/bin/bash
# =============================================================================
# BT Watchdog - Auto-reset Bluetooth stack when BLE is wedged
# =============================================================================
# Runs via systemd timer every 2 minutes. Resets the BT stack if no readings
# have been received for 15 minutes.
#
# First reset after 15 minutes of no readings, then retries every 30 minutes.
# Resets backoff counter when readings resume.
#
# Install:
#   sudo cp scripts/bt_watchdog.service /etc/systemd/system/
#   sudo cp scripts/bt_watchdog.timer /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now bt_watchdog.timer
# =============================================================================

BASE_COOLDOWN=${1:-15}  # Minutes of no readings before first reset
RETRY_COOLDOWN=${2:-30} # Minutes between subsequent retries
LOG_TAG="bt_watchdog"
STATE_DIR="/var/lib/bt_watchdog"
STAMP_FILE="${STATE_DIR}/last_reset"
FAIL_COUNT_FILE="${STATE_DIR}/fail_count"

log() {
    logger -t "$LOG_TAG" "$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1"
}

# Ensure state directory exists
mkdir -p "$STATE_DIR" 2>/dev/null

# Only act if o2monitor is running
if ! systemctl is-active --quiet o2monitor; then
    exit 0
fi

# --- Read failure count ---
FAIL_COUNT=0
if [ -f "$FAIL_COUNT_FILE" ]; then
    FAIL_COUNT=$(cat "$FAIL_COUNT_FILE")
fi

# --- Determine cooldown ---
if [ "$FAIL_COUNT" -eq 0 ]; then
    COOLDOWN_MINUTES=$BASE_COOLDOWN
else
    COOLDOWN_MINUTES=$RETRY_COOLDOWN
fi

RECENT_READINGS=$(journalctl -u o2monitor --since "${BASE_COOLDOWN} minutes ago" --no-pager 2>/dev/null \
    | grep -c "Reading: SpO2=")

if [ "$RECENT_READINGS" -gt 0 ]; then
    # Readings are flowing — reset backoff state
    if [ "$FAIL_COUNT" -gt 0 ]; then
        log "Readings resumed - resetting backoff counter (was at ${FAIL_COUNT})"
        echo 0 > "$FAIL_COUNT_FILE"
        rm -f "$STAMP_FILE"
    fi
    exit 0
fi

# --- Cooldown check ---
if [ -f "$STAMP_FILE" ]; then
    LAST_RESET=$(cat "$STAMP_FILE")
    NOW=$(date +%s)
    ELAPSED=$(( (NOW - LAST_RESET) / 60 ))
    if [ "$ELAPSED" -lt "$COOLDOWN_MINUTES" ]; then
        exit 0
    fi
fi

# --- No readings and cooldown expired — but is the service old enough? ---
UPTIME_STAMP=$(systemctl show o2monitor --property=ActiveEnterTimestamp --value 2>/dev/null)
if [ -n "$UPTIME_STAMP" ]; then
    BOOT_EPOCH=$(date -d "$UPTIME_STAMP" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    RUNNING_MINS=$(( (NOW_EPOCH - BOOT_EPOCH) / 60 ))
    if [ "$RUNNING_MINS" -lt "$BASE_COOLDOWN" ]; then
        exit 0
    fi
fi

# --- Reset ---
ATTEMPT=$(( FAIL_COUNT + 1 ))
log "No readings for ${COOLDOWN_MINUTES}m - reset attempt #${ATTEMPT} (next retry in ${RETRY_COOLDOWN}m if still failing)"

# Update state
date +%s > "$STAMP_FILE"
echo "$ATTEMPT" > "$FAIL_COUNT_FILE"

# Stop o2monitor first
systemctl stop o2monitor
log "Stopped o2monitor"

# Restart bluetooth service
systemctl restart bluetooth
sleep 2
log "Restarted bluetooth service"

# Reset HCI adapter
hciconfig hci0 reset
sleep 2
log "Reset hci0 adapter"

# Restart o2monitor
systemctl start o2monitor
log "Started o2monitor - BT stack reset complete"
