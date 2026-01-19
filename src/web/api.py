# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""REST API endpoints for O2 Monitor.

Provides JSON API for:
- Real-time status
- Historical readings
- Alert management
- Configuration

All endpoints require authentication except /api/health.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

from flask import Blueprint, g, jsonify, request, session

from src.models import Alert, AlertSeverity, AlertType
from src.web.auth import api_login_required

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


def run_async(coro):
    """Run async coroutine from sync Flask context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    # Wrap in task for aiohttp 3.x compatibility
    task = loop.create_task(coro)
    return loop.run_until_complete(task)


# ==================== Health Check ====================

@api_bp.route('/health')
def health():
    """Health check endpoint (no auth required)."""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
    })


# ==================== Status ====================

@api_bp.route('/status')
@api_login_required
def get_status():
    """Get current system status."""
    if not g.state_machine:
        return jsonify({'error': 'State machine not available'}), 503

    status = g.state_machine.get_status()

    # Convert to JSON-serializable dict
    reading = status.current_reading
    return jsonify({
        'timestamp': status.timestamp.isoformat(),
        'state': status.state.value,
        'vitals': {
            'spo2': reading.spo2 if reading else None,
            'heart_rate': reading.heart_rate if reading else None,
            'is_valid': reading.is_valid if reading else False,
        } if reading else None,
        'ble': {
            'connected': status.ble_status.connected,
            'battery_level': status.ble_status.battery_level,
            'last_reading_time': (
                status.ble_status.last_reading_time.isoformat()
                if status.ble_status.last_reading_time else None
            ),
        },
        'avaps': {
            'state': status.avaps_state.value,
            'power_watts': status.avaps_power_watts,
        },
        'system': {
            'uptime_seconds': status.uptime_seconds,
            'alerts_silenced': status.alerts_silenced,
            'silence_remaining_seconds': status.silence_remaining_seconds,
            'active_alert_count': status.active_alert_count,
        },
        'low_spo2': {
            'start_time': (
                status.low_spo2_start_time.isoformat()
                if status.low_spo2_start_time else None
            ),
            'duration_seconds': status.low_spo2_duration_seconds,
        } if status.low_spo2_start_time else None,
    })


# ==================== Readings ====================

@api_bp.route('/readings')
@api_login_required
def get_readings():
    """Get recent readings with pagination."""
    if not g.database:
        return jsonify({'error': 'Database not available'}), 503

    # Parse query parameters
    limit = min(int(request.args.get('limit', 100)), 200000)

    # Time range - support both 'hours' and 'start'/'end' parameters
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    if start_str and end_str:
        try:
            # Handle ISO format with Z suffix (UTC) - convert to local time
            # Remove Z suffix and parse, then treat as UTC and convert to local
            start_clean = start_str.replace('Z', '').replace('+00:00', '')
            end_clean = end_str.replace('Z', '').replace('+00:00', '')

            # Parse as naive datetime (these are UTC times from JS)
            start_utc = datetime.fromisoformat(start_clean)
            end_utc = datetime.fromisoformat(end_clean)

            # Convert UTC to local time (database stores local time)
            # Use time.localtime() to get current UTC offset (correctly handles DST)
            import time
            import calendar
            # Get current local time's UTC offset by comparing localtime and gmtime
            now = time.time()
            local_time = time.localtime(now)
            # tm_gmtoff gives seconds east of UTC (negative for west)
            # If not available, calculate from the difference
            if hasattr(local_time, 'tm_gmtoff'):
                utc_offset = timedelta(seconds=local_time.tm_gmtoff)
            else:
                # Fallback: calculate offset from local vs UTC
                utc_offset = timedelta(seconds=calendar.timegm(local_time) - int(now))
            start_time = start_utc + utc_offset
            end_time = end_utc + utc_offset
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    else:
        hours = int(request.args.get('hours', 1))
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

    # Fetch readings
    readings = run_async(g.database.get_readings(
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    ))

    # Get stats
    stats = run_async(g.database.get_reading_stats(start_time, end_time))

    return jsonify({
        'readings': readings,
        'count': len(readings),
        'stats': stats,
        'start_time': start_time.isoformat(),
        'end_time': end_time.isoformat(),
    })


@api_bp.route('/readings/export')
@api_login_required
def export_readings_csv():
    """Export readings as CSV file."""
    import csv
    import io
    from flask import Response

    if not g.database:
        return jsonify({'error': 'Database not available'}), 503

    # Parse query parameters (same as get_readings)
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    if start_str and end_str:
        try:
            start_clean = start_str.replace('Z', '').replace('+00:00', '')
            end_clean = end_str.replace('Z', '').replace('+00:00', '')
            start_utc = datetime.fromisoformat(start_clean)
            end_utc = datetime.fromisoformat(end_clean)

            import time
            import calendar
            now = time.time()
            local_time = time.localtime(now)
            if hasattr(local_time, 'tm_gmtoff'):
                utc_offset = timedelta(seconds=local_time.tm_gmtoff)
            else:
                utc_offset = timedelta(seconds=calendar.timegm(local_time) - int(now))
            start_time = start_utc + utc_offset
            end_time = end_utc + utc_offset
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    else:
        hours = int(request.args.get('hours', 24))
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

    # Fetch all readings (no limit for export)
    readings = run_async(g.database.get_readings(
        start_time=start_time,
        end_time=end_time,
        limit=500000,
    ))

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow(['Timestamp', 'SpO2 (%)', 'Heart Rate (BPM)', 'AVAPS State', 'Power (Watts)', 'Battery (%)', 'Valid'])

    # Data rows
    for r in readings:
        writer.writerow([
            r.get('timestamp', ''),
            r.get('spo2', ''),
            r.get('heart_rate', ''),
            r.get('avaps_state', ''),
            r.get('power_watts', '') if r.get('power_watts') is not None else '',
            r.get('battery_level', '') if r.get('battery_level') is not None else '',
            'Yes' if r.get('is_valid') else 'No',
        ])

    # Create response with CSV content
    csv_content = output.getvalue()
    output.close()

    # Generate filename with date range
    filename = f"o2monitor_{start_time.strftime('%Y%m%d')}_{end_time.strftime('%Y%m%d')}.csv"

    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@api_bp.route('/readings/range')
@api_login_required
def get_readings_range():
    """Get readings for a specific date range."""
    if not g.database:
        return jsonify({'error': 'Database not available'}), 503

    # Parse date range
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    if not start_str or not end_str:
        return jsonify({'error': 'start and end parameters required'}), 400

    try:
        start_time = datetime.fromisoformat(start_str)
        end_time = datetime.fromisoformat(end_str)
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use ISO format.'}), 400

    limit = min(int(request.args.get('limit', 1000)), 5000)

    readings = run_async(g.database.get_readings(
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    ))

    # Get stats
    stats = run_async(g.database.get_reading_stats(start_time, end_time))

    return jsonify({
        'readings': readings,
        'count': len(readings),
        'stats': stats,
        'start_time': start_time.isoformat(),
        'end_time': end_time.isoformat(),
    })


# ==================== Alerts ====================

@api_bp.route('/alerts')
@api_login_required
def get_alerts():
    """Get alert history."""
    if not g.database:
        return jsonify({'error': 'Database not available'}), 503

    # Parse query parameters
    limit = min(int(request.args.get('limit', 50)), 200)
    hours = int(request.args.get('hours', 24))

    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)

    alerts = run_async(g.database.get_alerts(
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    ))

    return jsonify({
        'alerts': alerts,
        'count': len(alerts),
    })


@api_bp.route('/alerts/active')
@api_login_required
def get_active_alerts():
    """Get currently active (unacknowledged) alerts."""
    if not g.database:
        return jsonify({'error': 'Database not available'}), 503

    alerts = run_async(g.database.get_active_alerts())

    return jsonify({
        'alerts': alerts,
        'count': len(alerts),
    })


@api_bp.route('/alerts/test', methods=['POST'])
@api_login_required
def trigger_test_alert():
    """Trigger a test alert for a specific alert type."""
    if not g.alert_manager:
        return jsonify({'error': 'Alert manager not available'}), 503

    data = request.get_json() or {}
    alert_type_str = data.get('alert_type', 'test')

    # Map alert type string to AlertType enum and get configured severity
    alert_type_map = {
        'spo2_critical_off_therapy': (AlertType.SPO2_CRITICAL, 'spo2_critical_off_therapy'),
        'spo2_critical_on_therapy': (AlertType.SPO2_CRITICAL, 'spo2_critical_on_therapy'),
        'spo2_warning': (AlertType.SPO2_WARNING, 'spo2_warning'),
        'hr_high': (AlertType.HR_HIGH, 'hr_high'),
        'hr_low': (AlertType.HR_LOW, 'hr_low'),
        'disconnect': (AlertType.DISCONNECT, 'disconnect'),
        'no_therapy_at_night_info': (AlertType.NO_THERAPY_AT_NIGHT, 'no_therapy_at_night_info'),
        'no_therapy_at_night_high': (AlertType.NO_THERAPY_AT_NIGHT, 'no_therapy_at_night_high'),
        'battery_warning': (AlertType.BATTERY_WARNING, 'battery_warning'),
        'battery_critical': (AlertType.BATTERY_CRITICAL, 'battery_critical'),
        'test': (AlertType.TEST, None),
    }

    if alert_type_str not in alert_type_map:
        return jsonify({'error': f'Unknown alert type: {alert_type_str}'}), 400

    alert_type, config_key = alert_type_map[alert_type_str]

    # Get severity from config if available
    severity = AlertSeverity.INFO
    if config_key and g.config and hasattr(g.config, 'alerts'):
        alert_config = getattr(g.config.alerts, config_key, None)
        if alert_config and hasattr(alert_config, 'severity'):
            severity_str = alert_config.severity.upper()
            try:
                severity = AlertSeverity[severity_str]
            except KeyError:
                severity = AlertSeverity.INFO

    # Build descriptive message
    alert_messages = {
        'spo2_critical_off_therapy': 'TEST: SpO2 Critical (Off Therapy) - Oxygen level dangerously low',
        'spo2_critical_on_therapy': 'TEST: SpO2 Critical (On Therapy) - Oxygen level dangerously low during AVAPS',
        'spo2_warning': 'TEST: SpO2 Warning - Oxygen level entering warning zone',
        'hr_high': 'TEST: Heart Rate High - Heart rate above threshold',
        'hr_low': 'TEST: Heart Rate Low - Heart rate below threshold',
        'disconnect': 'TEST: Disconnect - Oximeter connection lost',
        'no_therapy_at_night_info': 'TEST: No Therapy at Night (Info) - AVAPS not in use during sleep hours',
        'no_therapy_at_night_high': 'TEST: No Therapy at Night (Urgent) - AVAPS still not in use during sleep hours',
        'battery_warning': 'TEST: Battery Warning - Oximeter battery low',
        'battery_critical': 'TEST: Battery Critical - Oximeter battery very low',
        'test': 'Test alert triggered from web dashboard',
    }

    alert = Alert(
        id=f"test-{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now(),
        alert_type=alert_type,
        severity=severity,
        message=alert_messages.get(alert_type_str, 'Test alert'),
    )

    # Trigger full alert (including PagerDuty) and capture dedup_key
    pagerduty_dedup_key = run_async(g.alert_manager.trigger_alarm(alert))

    # Store in database with dedup_key for two-way sync
    if g.database:
        run_async(g.database.insert_alert(alert, pagerduty_dedup_key=pagerduty_dedup_key))

    logger.info(f"Test alert ({alert_type_str}, {severity.value}) triggered by {session.get('user')}")

    return jsonify({
        'success': True,
        'alert_id': alert.id,
        'alert_type': alert_type_str,
        'severity': severity.value,
        'message': f'Test {alert_type_str} alert triggered ({severity.value})',
    })


@api_bp.route('/alerts/<alert_id>/acknowledge', methods=['POST'])
@api_login_required
def acknowledge_alert(alert_id: str):
    """Acknowledge an alert and resolve it in PagerDuty."""
    if not g.database:
        return jsonify({'error': 'Database not available'}), 503

    user = session.get('user', 'unknown')

    # Acknowledge in database
    success = run_async(g.database.acknowledge_alert(alert_id, user))

    if success:
        logger.info(f"Alert {alert_id} acknowledged by {user}")

        # Also resolve in AlertManager (stops audio, resolves PagerDuty)
        if g.alert_manager:
            run_async(g.alert_manager.resolve_alert(alert_id))

        # Mark as resolved in database too
        run_async(g.database.resolve_alert(alert_id))

        return jsonify({'success': True, 'pagerduty_resolved': bool(g.alert_manager)})
    else:
        return jsonify({'error': 'Alert not found'}), 404


@api_bp.route('/alerts/silence', methods=['POST'])
@api_login_required
def silence_alerts():
    """Silence alerts for a duration."""
    if not g.alert_manager:
        return jsonify({'error': 'Alert manager not available'}), 503

    data = request.get_json() or {}
    duration = int(data.get('duration_minutes', 30))
    duration = max(1, min(duration, 120))  # 1-120 minutes

    g.alert_manager.silence(duration)

    logger.info(f"Alerts silenced for {duration} minutes by {session.get('user')}")

    return jsonify({
        'success': True,
        'duration_minutes': duration,
        'message': f'Alerts silenced for {duration} minutes',
    })


@api_bp.route('/alerts/unsilence', methods=['POST'])
@api_login_required
def unsilence_alerts():
    """Cancel alert silencing."""
    if not g.alert_manager:
        return jsonify({'error': 'Alert manager not available'}), 503

    g.alert_manager.unsilence()

    logger.info(f"Alerts unsilenced by {session.get('user')}")

    return jsonify({
        'success': True,
        'message': 'Alerts unsilenced',
    })


# ==================== Configuration ====================

@api_bp.route('/config')
@api_login_required
def get_config():
    """Get current configuration (thresholds only, not secrets)."""
    config = g.config
    if not config:
        return jsonify({'error': 'Config not available'}), 503

    # Helper to serialize alert item
    def _alert_to_dict(alert):
        return {
            'enabled': alert.enabled,
            'threshold': alert.threshold,
            'duration_seconds': alert.duration_seconds,
            'severity': alert.severity,
            'bypass_on_therapy': alert.bypass_on_therapy,
            'resend_interval_seconds': alert.resend_interval_seconds,
        }

    return jsonify({
        'alerts': {
            'spo2_critical_off_therapy': _alert_to_dict(config.alerts.spo2_critical_off_therapy),
            'spo2_critical_on_therapy': _alert_to_dict(config.alerts.spo2_critical_on_therapy),
            'spo2_warning': _alert_to_dict(config.alerts.spo2_warning),
            'hr_high': _alert_to_dict(config.alerts.hr_high),
            'hr_low': _alert_to_dict(config.alerts.hr_low),
            'disconnect': _alert_to_dict(config.alerts.disconnect),
            'no_therapy_at_night_info': _alert_to_dict(config.alerts.no_therapy_at_night_info),
            'no_therapy_at_night_high': _alert_to_dict(config.alerts.no_therapy_at_night_high),
            'battery_warning': _alert_to_dict(config.alerts.battery_warning),
            'battery_critical': _alert_to_dict(config.alerts.battery_critical),
            'sleep_hours': {
                'start': config.alerts.sleep_hours.start,
                'end': config.alerts.sleep_hours.end,
            },
        },
        'thresholds': {
            'avaps': {
                'on_watts': config.thresholds.avaps.on_watts,
                'window_minutes': config.thresholds.avaps.window_minutes,
            },
        },
        'alerting': {
            'local_audio': {
                'enabled': config.alerting.local_audio.enabled,
                'volume': config.alerting.local_audio.volume,
            },
            'pagerduty': {
                'configured': bool(config.alerting.pagerduty.routing_key),
                'routing_key': config.alerting.pagerduty.routing_key or '',
                'api_token': config.alerting.pagerduty.api_token or '',
                'service_name': config.alerting.pagerduty.service_name,
            },
            'healthchecks': {
                'configured': bool(config.alerting.healthchecks.ping_url),
                'ping_url': config.alerting.healthchecks.ping_url or '',
            },
        },
        'devices': {
            'oximeter': {
                'mac_address': config.devices.oximeter.mac_address,
                'name': config.devices.oximeter.name,
            },
            'smart_plug': {
                'ip_address': config.devices.smart_plug.ip_address,
                'name': config.devices.smart_plug.name,
            },
        },
        'bluetooth': {
            'read_interval_seconds': config.bluetooth.read_interval_seconds,
            'late_reading_seconds': config.bluetooth.late_reading_seconds,
            'respawn_delay_seconds': config.bluetooth.respawn_delay_seconds,
            'bt_restart_threshold_minutes': config.bluetooth.bt_restart_threshold_minutes,
        },
    })


@api_bp.route('/config', methods=['PUT'])
@api_login_required
def update_config():
    """Update configuration settings and persist to config.yaml."""
    config = g.config
    if not config:
        return jsonify({'error': 'Config not available'}), 503

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    updated = []

    # Update alerts configuration (unified format)
    if 'alerts' in data:
        alerts = data['alerts']

        # Helper to update alert item from dict
        def _update_alert(alert_config, alert_data, alert_name):
            fields_updated = []
            if 'enabled' in alert_data:
                alert_config.enabled = bool(alert_data['enabled'])
                fields_updated.append(f'{alert_name}.enabled')
            if 'threshold' in alert_data:
                alert_config.threshold = int(alert_data['threshold'])
                fields_updated.append(f'{alert_name}.threshold')
            if 'duration_seconds' in alert_data:
                alert_config.duration_seconds = int(alert_data['duration_seconds'])
                fields_updated.append(f'{alert_name}.duration_seconds')
            if 'severity' in alert_data:
                alert_config.severity = alert_data['severity']
                fields_updated.append(f'{alert_name}.severity')
            if 'bypass_on_therapy' in alert_data:
                alert_config.bypass_on_therapy = bool(alert_data['bypass_on_therapy'])
                fields_updated.append(f'{alert_name}.bypass_on_therapy')
            if 'resend_interval_seconds' in alert_data:
                alert_config.resend_interval_seconds = int(alert_data['resend_interval_seconds'])
                fields_updated.append(f'{alert_name}.resend_interval_seconds')
            return fields_updated

        # Update each alert type
        alert_types = ['spo2_critical_off_therapy', 'spo2_critical_on_therapy', 'spo2_warning',
                       'hr_high', 'hr_low', 'disconnect',
                       'no_therapy_at_night_info', 'no_therapy_at_night_high',
                       'battery_warning', 'battery_critical']
        for alert_name in alert_types:
            if alert_name in alerts:
                alert_config = getattr(config.alerts, alert_name)
                updated.extend(_update_alert(alert_config, alerts[alert_name], alert_name))

        # Update sleep hours
        if 'sleep_hours' in alerts:
            if 'start' in alerts['sleep_hours']:
                config.alerts.sleep_hours.start = alerts['sleep_hours']['start']
                updated.append('alerts.sleep_hours.start')
            if 'end' in alerts['sleep_hours']:
                config.alerts.sleep_hours.end = alerts['sleep_hours']['end']
                updated.append('alerts.sleep_hours.end')

    # Update thresholds
    if 'thresholds' in data:
        t = data['thresholds']
        if 'avaps' in t:
            if 'on_watts' in t['avaps']:
                config.thresholds.avaps.on_watts = float(t['avaps']['on_watts'])
                updated.append('avaps.on_watts')
            if 'window_minutes' in t['avaps']:
                config.thresholds.avaps.window_minutes = int(t['avaps']['window_minutes'])
                updated.append('avaps.window_minutes')

    # Update alerting
    if 'alerting' in data:
        a = data['alerting']
        if 'local_audio' in a:
            if 'enabled' in a['local_audio']:
                config.alerting.local_audio.enabled = bool(a['local_audio']['enabled'])
                updated.append('alerting.local_audio.enabled')
            if 'volume' in a['local_audio']:
                config.alerting.local_audio.volume = int(a['local_audio']['volume'])
                updated.append('alerting.local_audio.volume')

        if 'pagerduty' in a:
            if 'routing_key' in a['pagerduty']:
                config.alerting.pagerduty.routing_key = a['pagerduty']['routing_key']
                updated.append('alerting.pagerduty.routing_key')
            if 'api_token' in a['pagerduty']:
                config.alerting.pagerduty.api_token = a['pagerduty']['api_token']
                updated.append('alerting.pagerduty.api_token')

        if 'healthchecks' in a:
            if 'ping_url' in a['healthchecks']:
                config.alerting.healthchecks.ping_url = a['healthchecks']['ping_url']
                updated.append('alerting.healthchecks.ping_url')

    # Update devices
    if 'devices' in data:
        d = data['devices']
        if 'smart_plug' in d:
            if 'ip_address' in d['smart_plug']:
                config.devices.smart_plug.ip_address = d['smart_plug']['ip_address']
                updated.append('devices.smart_plug.ip_address')

    # Update bluetooth
    if 'bluetooth' in data:
        bt = data['bluetooth']
        if 'read_interval_seconds' in bt:
            config.bluetooth.read_interval_seconds = int(bt['read_interval_seconds'])
            updated.append('bluetooth.read_interval_seconds')
        if 'late_reading_seconds' in bt:
            config.bluetooth.late_reading_seconds = int(bt['late_reading_seconds'])
            updated.append('bluetooth.late_reading_seconds')
        if 'respawn_delay_seconds' in bt:
            config.bluetooth.respawn_delay_seconds = int(bt['respawn_delay_seconds'])
            updated.append('bluetooth.respawn_delay_seconds')
        if 'bt_restart_threshold_minutes' in bt:
            config.bluetooth.bt_restart_threshold_minutes = int(bt['bt_restart_threshold_minutes'])
            updated.append('bluetooth.bt_restart_threshold_minutes')

    # Persist to config.yaml
    from src.config import save_config
    try:
        save_config(config, "config.yaml")
        logger.info(f"Config updated and saved by {session.get('user')}: {updated}")
        return jsonify({
            'success': True,
            'updated': updated,
            'message': f'Updated {len(updated)} settings and saved to config.yaml',
        })
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return jsonify({
            'success': True,
            'updated': updated,
            'message': f'Updated {len(updated)} settings (save to file failed: {e})',
        })


# ==================== Audio Test ====================

@api_bp.route('/audio/test', methods=['POST'])
@api_login_required
def test_audio():
    """Play a test sound through local audio."""
    import subprocess
    import math

    data = request.get_json() or {}
    volume = min(100, max(0, int(data.get('volume', 50))))

    # ALSA uses logarithmic scale, so we compensate to make slider feel linear
    # If we send X%, ALSA displays roughly (X^2/100)%, so we send sqrt(volume)*10
    amixer_volume = int(math.sqrt(volume) * 10)

    try:
        # Set volume using amixer on headphone card (card 0, PCM control)
        subprocess.run(
            ['amixer', '-c', '0', 'set', 'PCM', f'{amixer_volume}%'],
            capture_output=True,
            timeout=5
        )

        # Play test sound using espeak at fixed amplitude, amixer controls actual volume
        result = subprocess.run(
            ['espeak', '-a', '200', 'Audio test'],
            capture_output=True,
            timeout=10
        )

        if result.returncode != 0:
            # Fallback to aplay with system beep if available
            subprocess.run(
                ['aplay', '/usr/share/sounds/alsa/Front_Center.wav'],
                capture_output=True,
                timeout=10
            )

        logger.info(f"Audio test played at {volume}% by {session.get('user')}")
        return jsonify({'success': True, 'volume': volume})

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Audio playback timed out'}), 500
    except FileNotFoundError as e:
        return jsonify({'error': f'Audio tool not found: {e}'}), 500
    except Exception as e:
        logger.error(f"Audio test failed: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== System Events ====================

@api_bp.route('/events')
@api_login_required
def get_events():
    """Get system events."""
    if not g.database:
        return jsonify({'error': 'Database not available'}), 503

    limit = min(int(request.args.get('limit', 50)), 200)
    event_type = request.args.get('type')

    events = run_async(g.database.get_events(
        event_type=event_type,
        limit=limit,
    ))

    return jsonify({
        'events': events,
        'count': len(events),
    })


# ==================== Device Discovery ====================

@api_bp.route('/devices/discover', methods=['POST'])
@api_login_required
def discover_devices():
    """Discover Kasa smart plugs on the network."""
    try:
        from kasa import Discover

        devices = run_async(_discover_plugs())

        return jsonify({
            'success': True,
            'devices': devices,
            'count': len(devices),
        })
    except ImportError:
        return jsonify({'error': 'python-kasa not installed'}), 500
    except Exception as e:
        logger.error(f"Device discovery failed: {e}")
        return jsonify({'error': str(e)}), 500


async def _discover_plugs():
    """Async function to discover Kasa devices."""
    from kasa import Discover

    devices = []
    discovered = await Discover.discover(timeout=10)

    for ip, device in discovered.items():
        await device.update()
        devices.append({
            'ip': ip,
            'alias': device.alias,
            'model': device.model if hasattr(device, 'model') else 'Unknown',
            'has_emeter': device.has_emeter if hasattr(device, 'has_emeter') else False,
        })

    return devices
