# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Flask application factory for O2 Monitor web dashboard.

This module creates and configures the Flask application with:
- Session management
- CSRF protection
- Static file serving
- Template rendering
- Logging integration

Usage:
    from src.web.app import create_app

    app = create_app(config)
    app.run()
"""

import logging
import os
from datetime import timedelta
from typing import Optional

from flask import Flask, g

logger = logging.getLogger(__name__)


def create_app(config, state_machine=None, database=None, alert_manager=None):
    """Create and configure Flask application.

    Args:
        config: Application configuration object
        state_machine: O2MonitorStateMachine instance (for live data)
        database: Database instance (for historical data)
        alert_manager: AlertManager instance (for alert control)

    Returns:
        Configured Flask application
    """
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='templates',
    )

    # Basic configuration
    app.config['SECRET_KEY'] = config.web.secret_key or os.urandom(32)
    app.config['SESSION_COOKIE_SECURE'] = False  # Set True in production with HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
        minutes=config.auth.session_timeout_minutes
    )

    # Store references to core components
    app.config['STATE_MACHINE'] = state_machine
    app.config['DATABASE'] = database
    app.config['ALERT_MANAGER'] = alert_manager
    app.config['APP_CONFIG'] = config

    # Register blueprints
    from src.web.routes import main_bp
    from src.web.api import api_bp
    from src.web.auth import auth_bp
    from src.web.relay_api import relay_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(relay_bp, url_prefix='/api/relay')

    # Context processor for templates
    @app.context_processor
    def inject_globals():
        """Inject global variables into templates."""
        return {
            'app_name': 'O2 Monitor',
            'version': '1.0.0',
        }

    # Before request - make components available
    @app.before_request
    def before_request():
        """Set up request context."""
        g.state_machine = app.config.get('STATE_MACHINE')
        g.database = app.config.get('DATABASE')
        g.alert_manager = app.config.get('ALERT_MANAGER')
        g.config = app.config.get('APP_CONFIG')

    logger.info("Flask application created")
    return app


def run_app(app, host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
    """Run the Flask application.

    Args:
        app: Flask application instance
        host: Host to bind to
        port: Port to listen on
        debug: Enable debug mode
    """
    logger.info(f"Starting web server on {host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)
