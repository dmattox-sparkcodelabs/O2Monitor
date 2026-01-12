"""Main routes for O2 Monitor web dashboard.

Handles page rendering for:
- Dashboard (real-time display)
- History (historical charts)
- Alerts (alert log)
- Settings (configuration)
"""

import logging
from datetime import datetime, timedelta

from flask import Blueprint, g, redirect, render_template, url_for

from src.web.auth import login_required

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Root route - redirect to dashboard or login."""
    return redirect(url_for('main.dashboard'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main real-time dashboard page."""
    # Get current status from state machine
    status = None
    if g.state_machine:
        status = g.state_machine.get_status()

    return render_template('dashboard.html', status=status)


@main_bp.route('/history')
@login_required
def history():
    """Historical data charts page."""
    return render_template('history.html')


@main_bp.route('/alerts')
@login_required
def alerts():
    """Alert log page."""
    return render_template('alerts.html')


@main_bp.route('/settings')
@login_required
def settings():
    """Settings/configuration page."""
    config = g.config
    return render_template('settings.html', config=config)
