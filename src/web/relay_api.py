# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Relay API endpoints for O2 Monitor.

Provides JSON API for Android app to relay oximeter readings when the user
is out of range of the Pi's Bluetooth adapters.

Endpoints:
    GET  /api/relay/status      - Check if Pi needs relay help
    POST /api/relay/reading     - Submit a single reading
    POST /api/relay/batch       - Submit batch of readings
    GET  /api/relay/app-version - Get Android app version info

All endpoints require authentication.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

from flask import Blueprint, g, jsonify, request, session

from src.models import AVAPSState, OxiReading
from src.web.auth import api_login_required

logger = logging.getLogger(__name__)

relay_bp = Blueprint('relay', __name__)


def run_async(coro):
    """Run async coroutine from sync Flask context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    task = loop.create_task(coro)
    return loop.run_until_complete(task)


# ==================== Relay Status ====================

@relay_bp.route('/status')
@api_login_required
def get_relay_status():
    """Check if the Pi needs relay help from the Android app.

    Returns:
        JSON with fields matching Android app expectations:
        - timestamp: str - Current Pi time (ISO format)
        - last_reading_age_seconds: int|null - Seconds since last valid reading
        - source: str - Current data source ('BLE' or 'Mobile')
        - needs_relay: bool - True if Pi wants the phone to relay readings
        - pi_ble_connected: bool - Current BLE connection state
        - relay_active: bool - True if Pi is currently receiving relay data
        - current_vitals: object|null - Latest vitals for display
        - therapy_active: bool - True if AVAPS therapy is on
        - power_watts: float|null - Current AVAPS power draw

    The phone should start relaying when needs_relay is True and stop
    when it becomes False.
    """
    if not g.state_machine:
        return jsonify({'error': 'State machine not available'}), 503

    status = g.state_machine.get_status()

    # Calculate seconds since last reading
    last_reading_age_seconds = None
    if status.ble_status.last_reading_time:
        last_reading_age_seconds = int(
            (datetime.now() - status.ble_status.last_reading_time).total_seconds()
        )

    # Determine if Pi needs relay help
    # Pi wants relay if:
    # 1. BLE is not connected, OR
    # 2. Last reading is older than late_reading_seconds threshold
    late_threshold = g.config.bluetooth.late_reading_seconds if g.config else 30
    needs_relay = (
        not status.ble_status.connected or
        (last_reading_age_seconds is not None and last_reading_age_seconds > late_threshold)
    )

    # Check if relay is currently active (receiving data from phone)
    relay_active = getattr(g.state_machine, '_relay_active', False)
    last_relay_time = getattr(g.state_machine, '_last_relay_reading_time', None)

    # Relay is considered active if we received data in the last 30 seconds
    if last_relay_time:
        relay_age = (datetime.now() - last_relay_time).total_seconds()
        relay_active = relay_age < 30

    # Determine current data source
    if relay_active:
        source = 'Mobile'
    elif status.ble_status.connected:
        source = 'BLE'
    else:
        source = 'None'

    # Build current vitals for display on the phone
    current_vitals = None
    reading = status.current_reading
    if reading:
        current_vitals = {
            'spo2': reading.spo2,
            'heart_rate': reading.heart_rate,
            'battery_level': reading.battery_level,
            'is_valid': reading.is_valid,
            'timestamp': reading.timestamp.isoformat() if reading.timestamp else None,
            'source': source,
        }

    # Get therapy (AVAPS) status and power
    therapy_active = status.avaps_state == AVAPSState.ON
    power_watts = status.avaps_power_watts

    return jsonify({
        # Fields expected by Android app
        'timestamp': datetime.now().isoformat(),
        'last_reading_age_seconds': last_reading_age_seconds,
        'source': source,
        'needs_relay': needs_relay,
        'pi_ble_connected': status.ble_status.connected,
        # Additional fields
        'relay_active': relay_active,
        'current_vitals': current_vitals,
        'therapy_active': therapy_active,
        'power_watts': power_watts,
    })


# ==================== Submit Reading ====================

@relay_bp.route('/reading', methods=['POST'])
@api_login_required
def post_relay_reading():
    """Submit a single oximeter reading from the Android app.

    Request body (JSON):
        {
            "timestamp": "2024-01-15T10:30:00",  // ISO format
            "spo2": 97,                          // 0-100
            "heart_rate": 72,                    // BPM
            "battery_level": 85,                 // 0-100 (optional)
            "is_valid": true                     // (optional, default true)
        }

    Returns:
        JSON with:
        - success: bool
        - message: str
        - reading_id: int (database row ID)
    """
    if not g.state_machine or not g.database:
        return jsonify({'error': 'System not available'}), 503

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    # Validate required fields
    if 'spo2' not in data or 'heart_rate' not in data:
        return jsonify({'error': 'spo2 and heart_rate are required'}), 400

    try:
        spo2 = int(data['spo2'])
        heart_rate = int(data['heart_rate'])

        if not (0 <= spo2 <= 100):
            return jsonify({'error': 'spo2 must be 0-100'}), 400
        if not (0 <= heart_rate <= 300):
            return jsonify({'error': 'heart_rate must be 0-300'}), 400

    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid value: {e}'}), 400

    # Parse timestamp or use current time
    if 'timestamp' in data:
        try:
            timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            # Convert to local time if needed
            if timestamp.tzinfo:
                timestamp = timestamp.replace(tzinfo=None)
        except ValueError:
            return jsonify({'error': 'Invalid timestamp format'}), 400
    else:
        timestamp = datetime.now()

    # Create OxiReading
    reading = OxiReading(
        timestamp=timestamp,
        spo2=spo2,
        heart_rate=heart_rate,
        battery_level=int(data.get('battery_level', 0)),
        movement=int(data.get('movement', 0)),
        is_valid=data.get('is_valid', True),
    )

    # Get current AVAPS state
    avaps_state = g.state_machine.avaps_state

    # Store in database with source='relay'
    try:
        reading_id = run_async(
            g.database.insert_reading(
                reading=reading,
                avaps_state=avaps_state,
                source='relay'
            )
        )
    except TypeError:
        # If insert_reading doesn't support source param yet, fall back
        reading_id = run_async(
            g.database.insert_reading(
                reading=reading,
                avaps_state=avaps_state,
            )
        )

    # Update state machine with relay reading
    _update_state_machine_with_relay(g.state_machine, reading)

    # Log relay activity
    logger.info(
        f"Relay reading received: SpO2={spo2}%, HR={heart_rate}bpm "
        f"(source: Android app)"
    )

    return jsonify({
        'success': True,
        'message': 'Reading accepted',
        'reading_id': reading_id,
    })


# ==================== Submit Batch ====================

@relay_bp.route('/batch', methods=['POST'])
@api_login_required
def post_relay_batch():
    """Submit a batch of oximeter readings from the Android app.

    Used when the phone has queued readings while offline and needs
    to flush them to the Pi.

    Request body (JSON):
        {
            "readings": [
                {
                    "timestamp": "2024-01-15T10:30:00",
                    "spo2": 97,
                    "heart_rate": 72,
                    "battery_level": 85,
                    "is_valid": true
                },
                ...
            ]
        }

    Returns:
        JSON with:
        - success: bool
        - accepted: int (number of readings accepted)
        - rejected: int (number of readings rejected)
        - errors: list of error messages (if any)
    """
    if not g.state_machine or not g.database:
        return jsonify({'error': 'System not available'}), 503

    data = request.get_json()
    if not data or 'readings' not in data:
        return jsonify({'error': 'JSON body with readings array required'}), 400

    readings_data = data['readings']
    if not isinstance(readings_data, list):
        return jsonify({'error': 'readings must be an array'}), 400

    if len(readings_data) > 1000:
        return jsonify({'error': 'Maximum 1000 readings per batch'}), 400

    accepted = 0
    rejected = 0
    errors = []
    avaps_state = g.state_machine.avaps_state
    latest_reading = None

    for i, item in enumerate(readings_data):
        try:
            # Validate fields
            if 'spo2' not in item or 'heart_rate' not in item:
                errors.append(f"Reading {i}: missing spo2 or heart_rate")
                rejected += 1
                continue

            spo2 = int(item['spo2'])
            heart_rate = int(item['heart_rate'])

            if not (0 <= spo2 <= 100) or not (0 <= heart_rate <= 300):
                errors.append(f"Reading {i}: values out of range")
                rejected += 1
                continue

            # Parse timestamp
            if 'timestamp' in item:
                timestamp = datetime.fromisoformat(
                    item['timestamp'].replace('Z', '+00:00')
                )
                if timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=None)
            else:
                timestamp = datetime.now()

            # Create reading
            reading = OxiReading(
                timestamp=timestamp,
                spo2=spo2,
                heart_rate=heart_rate,
                battery_level=int(item.get('battery_level', 0)),
                movement=int(item.get('movement', 0)),
                is_valid=item.get('is_valid', True),
            )

            # Store in database
            try:
                run_async(
                    g.database.insert_reading(
                        reading=reading,
                        avaps_state=avaps_state,
                        source='relay'
                    )
                )
            except TypeError:
                run_async(
                    g.database.insert_reading(
                        reading=reading,
                        avaps_state=avaps_state,
                    )
                )

            accepted += 1

            # Track latest reading for state machine update
            if latest_reading is None or timestamp > latest_reading.timestamp:
                latest_reading = reading

        except Exception as e:
            errors.append(f"Reading {i}: {str(e)}")
            rejected += 1

    # Update state machine with the most recent reading
    if latest_reading:
        _update_state_machine_with_relay(g.state_machine, latest_reading)

    logger.info(
        f"Relay batch received: {accepted} accepted, {rejected} rejected "
        f"(source: Android app)"
    )

    return jsonify({
        'success': rejected == 0,
        'accepted': accepted,
        'rejected': rejected,
        'errors': errors[:10] if errors else [],  # Limit error messages
    })


# ==================== App Version ====================

@relay_bp.route('/app-version')
@api_login_required
def get_app_version():
    """Get Android app version information for auto-update checks.

    Returns:
        JSON with:
        - latest_version: str (e.g., "1.0.0")
        - latest_version_code: int (e.g., 1)
        - min_supported_version: str
        - min_supported_version_code: int
        - download_url: str (URL to download APK)
        - release_notes: str
    """
    # Try to load version info from version.json file
    version_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'android',
        'version.json'
    )

    default_version = {
        'latest_version': '1.0.0',
        'latest_version_code': 1,
        'min_supported_version': '1.0.0',
        'min_supported_version_code': 1,
        'download_url': '',
        'release_notes': 'Initial release',
    }

    if os.path.exists(version_file):
        try:
            with open(version_file, 'r') as f:
                version_info = json.load(f)
                # Merge with defaults
                return jsonify({**default_version, **version_info})
        except Exception as e:
            logger.warning(f"Failed to load version.json: {e}")

    return jsonify(default_version)


# ==================== Helper Functions ====================

def _update_state_machine_with_relay(state_machine, reading: OxiReading) -> None:
    """Update the state machine with a relay reading.

    This allows the state machine to use relay readings for alerting
    and state transitions when BLE is disconnected.

    Args:
        state_machine: O2MonitorStateMachine instance
        reading: OxiReading from relay
    """
    # Store the reading in state machine
    state_machine._current_reading = reading

    # Mark relay as active
    state_machine._relay_active = True
    state_machine._last_relay_reading_time = datetime.now()

    # Clear disconnect tracking since we're getting data via relay
    if hasattr(state_machine, '_disconnect_start'):
        state_machine._disconnect_start = None

    logger.debug(
        f"State machine updated with relay reading: "
        f"SpO2={reading.spo2}%, HR={reading.heart_rate}bpm"
    )
