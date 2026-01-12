"""Authentication module for O2 Monitor web dashboard.

Handles user authentication with:
- Login/logout routes
- Session management
- Rate limiting
- Password verification with bcrypt

Usage:
    from src.web.auth import auth_bp, login_required

    @app.route('/protected')
    @login_required
    def protected_route():
        return "Secret content"
"""

import functools
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import bcrypt
from flask import (
    Blueprint, current_app, flash, g, redirect,
    render_template, request, session, url_for
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# Rate limiting storage (in-memory, resets on restart)
_login_attempts: Dict[str, list] = {}  # IP -> list of attempt timestamps


def login_required(f):
    """Decorator to require authentication for a route."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin role for a route."""
    @functools.wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def check_rate_limit(ip: str, max_attempts: int = 5, window_minutes: int = 15) -> Tuple[bool, int]:
    """Check if IP is rate limited.

    Args:
        ip: Client IP address
        max_attempts: Maximum attempts allowed
        window_minutes: Time window in minutes

    Returns:
        Tuple of (is_allowed, remaining_attempts)
    """
    now = time.time()
    window_start = now - (window_minutes * 60)

    # Clean old attempts
    if ip in _login_attempts:
        _login_attempts[ip] = [t for t in _login_attempts[ip] if t > window_start]
    else:
        _login_attempts[ip] = []

    attempts = len(_login_attempts[ip])
    remaining = max(0, max_attempts - attempts)

    return attempts < max_attempts, remaining


def record_login_attempt(ip: str):
    """Record a failed login attempt.

    Args:
        ip: Client IP address
    """
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    _login_attempts[ip].append(time.time())


def clear_login_attempts(ip: str):
    """Clear login attempts for IP after successful login.

    Args:
        ip: Client IP address
    """
    if ip in _login_attempts:
        del _login_attempts[ip]


def verify_password(stored_hash: str, password: str) -> bool:
    """Verify password against stored bcrypt hash.

    Args:
        stored_hash: Stored bcrypt hash
        password: Password to verify

    Returns:
        True if password matches
    """
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            stored_hash.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        bcrypt hash string
    """
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt(rounds=12)
    ).decode('utf-8')


def get_user_by_username(username: str) -> Optional[dict]:
    """Look up user in config.

    Args:
        username: Username to find

    Returns:
        User dict with username, password_hash, role or None
    """
    config = g.config
    if not config or not hasattr(config, 'auth'):
        return None

    for user in config.auth.users:
        if user.username == username:
            return {
                'username': user.username,
                'password_hash': user.password_hash,
                'role': getattr(user, 'role', 'user'),
            }
    return None


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle login page and form submission."""
    # Already logged in?
    if 'user' in session:
        return redirect(url_for('main.dashboard'))

    error = None
    client_ip = request.remote_addr

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Check rate limiting
        config = g.config
        max_attempts = config.auth.max_login_attempts if config else 5
        lockout_minutes = config.auth.lockout_minutes if config else 15

        is_allowed, remaining = check_rate_limit(client_ip, max_attempts, lockout_minutes)

        if not is_allowed:
            error = f'Too many login attempts. Please try again in {lockout_minutes} minutes.'
            logger.warning(f"Rate limited login attempt from {client_ip}")
        else:
            # Verify credentials
            user = get_user_by_username(username)

            if user and verify_password(user['password_hash'], password):
                # Success - create session
                session.permanent = True
                session['user'] = username
                session['role'] = user.get('role', 'user')
                session['login_time'] = datetime.now().isoformat()

                clear_login_attempts(client_ip)
                logger.info(f"User '{username}' logged in from {client_ip}")

                # Redirect to requested page or dashboard
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):
                    return redirect(next_page)
                return redirect(url_for('main.dashboard'))
            else:
                record_login_attempt(client_ip)
                error = f'Invalid username or password. {remaining - 1} attempts remaining.'
                logger.warning(f"Failed login for '{username}' from {client_ip}")

    return render_template('login.html', error=error)


@auth_bp.route('/logout')
def logout():
    """Handle logout."""
    username = session.get('user', 'unknown')
    session.clear()
    logger.info(f"User '{username}' logged out")
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# Utility script for generating password hashes
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.web.auth <password>")
        print("Generates a bcrypt hash for the given password.")
        sys.exit(1)

    password = sys.argv[1]
    hashed = hash_password(password)
    print(f"\nPassword hash (copy to config.yaml):\n{hashed}\n")
