# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Database layer for O2 Monitor.

This module handles SQLite database operations for persisting:
- SpO2/HR readings
- Alerts
- System events
- User accounts and sessions

Uses aiosqlite for async database operations.

Usage:
    from src.database import Database

    db = Database("data/history.db")
    await db.initialize()
    await db.insert_reading(reading, avaps_state)
    await db.close()
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Add project root to path when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite

from src.models import Alert, AlertSeverity, AlertType, AVAPSState, OxiReading

logger = logging.getLogger(__name__)


class Database:
    """Async SQLite database manager for O2 Monitor.

    Handles all database operations including:
    - Schema initialization
    - Reading/Alert/Event persistence
    - User authentication data
    - Data retention and cleanup

    Attributes:
        db_path: Path to SQLite database file
    """

    def __init__(self, db_path: str):
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
        logger.info(f"Database initialized (path: {db_path})")

    async def initialize(self) -> None:
        """Initialize database connection and create tables.

        Creates the database file and all tables if they don't exist.
        """
        # Ensure directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"Created database directory: {db_dir}")

        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

        await self._create_tables()
        logger.info("Database initialized and tables created")

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    async def _create_tables(self) -> None:
        """Create all database tables if they don't exist."""
        async with self._connection.cursor() as cursor:
            # Readings table - SpO2/HR data
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    spo2 INTEGER,
                    heart_rate INTEGER,
                    battery_level INTEGER,
                    movement INTEGER,
                    is_valid BOOLEAN,
                    avaps_state TEXT,
                    power_watts REAL,
                    source TEXT DEFAULT 'ble'
                )
            """)

            # Create index on timestamp for readings
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_readings_timestamp
                ON readings(timestamp)
            """)

            # Migration: Add power_watts column if it doesn't exist
            await cursor.execute("PRAGMA table_info(readings)")
            columns = [row[1] for row in await cursor.fetchall()]
            if 'power_watts' not in columns:
                await cursor.execute("ALTER TABLE readings ADD COLUMN power_watts REAL")
                logger.info("Added power_watts column to readings table")

            # Migration: Add source column if it doesn't exist
            if 'source' not in columns:
                await cursor.execute("ALTER TABLE readings ADD COLUMN source TEXT DEFAULT 'ble'")
                logger.info("Added source column to readings table")

            # Alerts table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    timestamp DATETIME NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT,
                    spo2 INTEGER,
                    heart_rate INTEGER,
                    avaps_state TEXT,
                    acknowledged BOOLEAN DEFAULT FALSE,
                    acknowledged_at DATETIME,
                    acknowledged_by TEXT,
                    resolved BOOLEAN DEFAULT FALSE,
                    resolved_at DATETIME
                )
            """)

            # Create index on timestamp for alerts
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
                ON alerts(timestamp)
            """)

            # System events table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT,
                    metadata TEXT
                )
            """)

            # Create index on timestamp for events
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_timestamp
                ON system_events(timestamp)
            """)

            # Users table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    last_login DATETIME
                )
            """)

            # Sessions table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    last_activity DATETIME NOT NULL,
                    expires_at DATETIME NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # API tokens table (for mobile/API authentication)
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_tokens (
                    token TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    expires_at DATETIME NOT NULL,
                    last_used_at DATETIME,
                    device_name TEXT
                )
            """)

            # Create index on api_tokens expiration for cleanup
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_tokens_expires
                ON api_tokens(expires_at)
            """)

            await self._connection.commit()

            # Migrations - add columns to existing tables
            await self._run_migrations(cursor)
            await self._connection.commit()

    async def _run_migrations(self, cursor) -> None:
        """Run database migrations for schema updates."""
        # Add pagerduty_dedup_key column to alerts table if it doesn't exist
        try:
            await cursor.execute("SELECT pagerduty_dedup_key FROM alerts LIMIT 1")
        except Exception:
            logger.info("Adding pagerduty_dedup_key column to alerts table")
            await cursor.execute("""
                ALTER TABLE alerts ADD COLUMN pagerduty_dedup_key TEXT
            """)

    # ==================== Reading Operations ====================

    async def insert_reading(
        self,
        reading: Optional[OxiReading] = None,
        avaps_state: AVAPSState = AVAPSState.UNKNOWN,
        power_watts: Optional[float] = None,
        timestamp: Optional[datetime] = None,
        source: str = 'ble'
    ) -> int:
        """Insert a new reading (with or without O2 data).

        Args:
            reading: OxiReading object with vitals data (None for power-only readings)
            avaps_state: Current AVAPS state
            power_watts: Current AVAPS power consumption in watts
            timestamp: Timestamp for power-only readings (ignored if reading provided)
            source: Source of reading - 'ble' (default) or 'relay' (from Android app)

        Returns:
            ID of the inserted row
        """
        if reading is not None:
            # Full reading with O2 data
            ts = reading.timestamp.isoformat()
            spo2 = reading.spo2
            heart_rate = reading.heart_rate
            battery_level = reading.battery_level
            movement = reading.movement
            is_valid = reading.is_valid
        else:
            # Power-only reading (O2 disconnected)
            ts = (timestamp or datetime.now()).isoformat()
            spo2 = None
            heart_rate = None
            battery_level = None
            movement = None
            is_valid = False

        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                INSERT INTO readings
                (timestamp, spo2, heart_rate, battery_level, movement, is_valid, avaps_state, power_watts, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts,
                spo2,
                heart_rate,
                battery_level,
                movement,
                is_valid,
                avaps_state.value,
                power_watts,
                source,
            ))
            await self._connection.commit()
            return cursor.lastrowid

    async def get_readings(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get readings within a time range.

        Args:
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            limit: Maximum number of readings to return

        Returns:
            List of reading dictionaries
        """
        query = "SELECT * FROM readings"
        params = []
        conditions = []

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())

        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self._connection.cursor() as cursor:
            await cursor.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_latest_reading(self) -> Optional[Dict[str, Any]]:
        """Get the most recent reading.

        Returns:
            Most recent reading as dict, or None if no readings
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                SELECT * FROM readings
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_reading_stats(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """Get statistics for readings in a time range.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Dict with min, max, avg for SpO2 and heart rate
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                SELECT
                    MIN(spo2) as spo2_min,
                    MAX(spo2) as spo2_max,
                    AVG(spo2) as spo2_avg,
                    MIN(heart_rate) as hr_min,
                    MAX(heart_rate) as hr_max,
                    AVG(heart_rate) as hr_avg,
                    COUNT(*) as count
                FROM readings
                WHERE timestamp >= ? AND timestamp <= ?
                AND is_valid = 1
            """, (start_time.isoformat(), end_time.isoformat()))
            row = await cursor.fetchone()
            return dict(row) if row else {}

    # ==================== Alert Operations ====================

    async def insert_alert(self, alert: Alert, pagerduty_dedup_key: Optional[str] = None) -> None:
        """Insert a new alert.

        Args:
            alert: Alert object to insert
            pagerduty_dedup_key: PagerDuty deduplication key for this alert
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                INSERT INTO alerts
                (id, timestamp, alert_type, severity, message, spo2, heart_rate, avaps_state, pagerduty_dedup_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert.id,
                alert.timestamp.isoformat(),
                alert.alert_type.value,
                alert.severity.value,
                alert.message,
                alert.spo2,
                alert.heart_rate,
                alert.avaps_state.value if alert.avaps_state else None,
                pagerduty_dedup_key,
            ))
            await self._connection.commit()

    async def get_alerts(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get alerts within a time range.

        Args:
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            limit: Maximum number of alerts to return

        Returns:
            List of alert dictionaries
        """
        query = "SELECT * FROM alerts"
        params = []
        conditions = []

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())

        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self._connection.cursor() as cursor:
            await cursor.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all unacknowledged alerts.

        Returns:
            List of active (unacknowledged) alerts
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                SELECT * FROM alerts
                WHERE acknowledged = FALSE AND resolved = FALSE
                ORDER BY timestamp DESC
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_alerts_pending_pagerduty(self) -> List[Dict[str, Any]]:
        """Get unresolved alerts with PagerDuty dedup keys.

        Returns:
            List of alerts that have PagerDuty incidents to check
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                SELECT * FROM alerts
                WHERE pagerduty_dedup_key IS NOT NULL
                  AND resolved = FALSE
                ORDER BY timestamp DESC
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def sync_pagerduty_status(
        self,
        alert_id: str,
        acknowledged: bool,
        resolved: bool,
        acknowledged_by: Optional[str] = None
    ) -> bool:
        """Update alert status from PagerDuty.

        Args:
            alert_id: Alert ID to update
            acknowledged: Whether PagerDuty incident was acknowledged
            resolved: Whether PagerDuty incident was resolved
            acknowledged_by: Who acknowledged (from PagerDuty)

        Returns:
            True if alert was updated
        """
        async with self._connection.cursor() as cursor:
            if resolved:
                await cursor.execute("""
                    UPDATE alerts
                    SET resolved = TRUE,
                        resolved_at = ?,
                        acknowledged = TRUE,
                        acknowledged_at = COALESCE(acknowledged_at, ?),
                        acknowledged_by = COALESCE(acknowledged_by, ?)
                    WHERE id = ? AND resolved = FALSE
                """, (
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                    acknowledged_by or 'PagerDuty',
                    alert_id
                ))
            elif acknowledged:
                await cursor.execute("""
                    UPDATE alerts
                    SET acknowledged = TRUE,
                        acknowledged_at = COALESCE(acknowledged_at, ?),
                        acknowledged_by = COALESCE(acknowledged_by, ?)
                    WHERE id = ? AND acknowledged = FALSE
                """, (
                    datetime.now().isoformat(),
                    acknowledged_by or 'PagerDuty',
                    alert_id
                ))
            await self._connection.commit()
            return cursor.rowcount > 0

    async def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str = "user"
    ) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: ID of alert to acknowledge
            acknowledged_by: Who acknowledged the alert

        Returns:
            True if alert was found and updated
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                UPDATE alerts
                SET acknowledged = TRUE,
                    acknowledged_at = ?,
                    acknowledged_by = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), acknowledged_by, alert_id))
            await self._connection.commit()
            return cursor.rowcount > 0

    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert.

        Args:
            alert_id: ID of alert to resolve

        Returns:
            True if alert was found and updated
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                UPDATE alerts
                SET resolved = TRUE,
                    resolved_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), alert_id))
            await self._connection.commit()
            return cursor.rowcount > 0

    # ==================== System Event Operations ====================

    async def log_event(
        self,
        event_type: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Log a system event.

        Args:
            event_type: Type of event (e.g., "connection", "error")
            message: Event description
            metadata: Optional additional data as dict

        Returns:
            ID of the inserted event
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                INSERT INTO system_events
                (timestamp, event_type, message, metadata)
                VALUES (?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                event_type,
                message,
                json.dumps(metadata) if metadata else None,
            ))
            await self._connection.commit()
            return cursor.lastrowid

    async def get_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get system events.

        Args:
            start_time: Start of time range (inclusive)
            end_time: End of time range (inclusive)
            event_type: Filter by event type
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        query = "SELECT * FROM system_events"
        params = []
        conditions = []

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())

        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self._connection.cursor() as cursor:
            await cursor.execute(query, params)
            rows = await cursor.fetchall()

            # Parse metadata JSON
            results = []
            for row in rows:
                d = dict(row)
                if d.get("metadata"):
                    d["metadata"] = json.loads(d["metadata"])
                results.append(d)
            return results

    # ==================== User/Session Operations ====================

    async def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username.

        Args:
            username: Username to look up

        Returns:
            User dict or None if not found
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                SELECT * FROM users WHERE username = ?
            """, (username,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_user(
        self,
        username: str,
        password_hash: str
    ) -> int:
        """Create a new user.

        Args:
            username: Unique username
            password_hash: bcrypt password hash

        Returns:
            ID of the created user
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                INSERT INTO users (username, password_hash, created_at)
                VALUES (?, ?, ?)
            """, (username, password_hash, datetime.now().isoformat()))
            await self._connection.commit()
            return cursor.lastrowid

    async def update_user_login(self, user_id: int) -> None:
        """Update user's last login time.

        Args:
            user_id: ID of user to update
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                UPDATE users SET last_login = ? WHERE id = ?
            """, (datetime.now().isoformat(), user_id))
            await self._connection.commit()

    async def create_session(
        self,
        user_id: int,
        session_id: str,
        expires_minutes: int = 30
    ) -> None:
        """Create a new session.

        Args:
            user_id: ID of user for session
            session_id: Unique session identifier
            expires_minutes: Session expiration time in minutes
        """
        now = datetime.now()
        expires_at = now + timedelta(minutes=expires_minutes)

        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                INSERT INTO sessions
                (session_id, user_id, created_at, last_activity, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session_id,
                user_id,
                now.isoformat(),
                now.isoformat(),
                expires_at.isoformat(),
            ))
            await self._connection.commit()

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session dict or None if not found/expired
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                SELECT s.*, u.username
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_id = ? AND s.expires_at > ?
            """, (session_id, datetime.now().isoformat()))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_session_activity(self, session_id: str) -> None:
        """Update session last activity time.

        Args:
            session_id: Session identifier
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                UPDATE sessions SET last_activity = ? WHERE session_id = ?
            """, (datetime.now().isoformat(), session_id))
            await self._connection.commit()

    async def delete_session(self, session_id: str) -> None:
        """Delete a session.

        Args:
            session_id: Session identifier to delete
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                DELETE FROM sessions WHERE session_id = ?
            """, (session_id,))
            await self._connection.commit()

    async def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions.

        Returns:
            Number of sessions deleted
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                DELETE FROM sessions WHERE expires_at < ?
            """, (datetime.now().isoformat(),))
            await self._connection.commit()
            return cursor.rowcount

    # ==================== API Token Operations ====================

    async def create_api_token(
        self,
        username: str,
        token: str,
        expires_days: int = 30,
        device_name: Optional[str] = None
    ) -> None:
        """Create a new API token.

        Args:
            username: Username the token belongs to
            token: The token string
            expires_days: Days until token expires
            device_name: Optional device identifier
        """
        now = datetime.now()
        expires_at = now + timedelta(days=expires_days)

        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                INSERT INTO api_tokens (token, username, created_at, expires_at, device_name)
                VALUES (?, ?, ?, ?, ?)
            """, (token, username, now.isoformat(), expires_at.isoformat(), device_name))
            await self._connection.commit()

    async def get_api_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Get API token if valid (not expired).

        Args:
            token: Token string to look up

        Returns:
            Token dict or None if not found/expired
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                SELECT * FROM api_tokens
                WHERE token = ? AND expires_at > ?
            """, (token, datetime.now().isoformat()))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_token_last_used(self, token: str) -> None:
        """Update token's last used timestamp.

        Args:
            token: Token string
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                UPDATE api_tokens SET last_used_at = ? WHERE token = ?
            """, (datetime.now().isoformat(), token))
            await self._connection.commit()

    async def delete_api_token(self, token: str) -> bool:
        """Delete an API token.

        Args:
            token: Token to delete

        Returns:
            True if token was deleted
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                DELETE FROM api_tokens WHERE token = ?
            """, (token,))
            await self._connection.commit()
            return cursor.rowcount > 0

    async def delete_user_tokens(self, username: str) -> int:
        """Delete all tokens for a user.

        Args:
            username: Username whose tokens to delete

        Returns:
            Number of tokens deleted
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                DELETE FROM api_tokens WHERE username = ?
            """, (username,))
            await self._connection.commit()
            return cursor.rowcount

    async def cleanup_expired_tokens(self) -> int:
        """Delete all expired API tokens.

        Returns:
            Number of tokens deleted
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                DELETE FROM api_tokens WHERE expires_at < ?
            """, (datetime.now().isoformat(),))
            await self._connection.commit()
            return cursor.rowcount

    # ==================== Data Retention ====================

    async def cleanup_old_data(
        self,
        readings_days: int = 30,
        alerts_days: int = 365,
        events_days: int = 90
    ) -> Dict[str, int]:
        """Clean up old data based on retention policy.

        Args:
            readings_days: Delete readings older than this many days
            alerts_days: Delete alerts older than this many days
            events_days: Delete events older than this many days

        Returns:
            Dict with counts of deleted records by table
        """
        now = datetime.now()
        deleted = {}

        async with self._connection.cursor() as cursor:
            # Delete old readings
            cutoff = (now - timedelta(days=readings_days)).isoformat()
            await cursor.execute("""
                DELETE FROM readings WHERE timestamp < ?
            """, (cutoff,))
            deleted["readings"] = cursor.rowcount

            # Delete old alerts
            cutoff = (now - timedelta(days=alerts_days)).isoformat()
            await cursor.execute("""
                DELETE FROM alerts WHERE timestamp < ?
            """, (cutoff,))
            deleted["alerts"] = cursor.rowcount

            # Delete old events
            cutoff = (now - timedelta(days=events_days)).isoformat()
            await cursor.execute("""
                DELETE FROM system_events WHERE timestamp < ?
            """, (cutoff,))
            deleted["events"] = cursor.rowcount

            await self._connection.commit()

        logger.info(f"Data cleanup: {deleted}")
        return deleted


# Command-line interface for testing
if __name__ == "__main__":
    import argparse
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    parser = argparse.ArgumentParser(description="Test database module")
    parser.add_argument("--db", default="data/test_history.db",
                        help="Database path")
    parser.add_argument("--clean", action="store_true",
                        help="Remove test database after")
    args = parser.parse_args()

    async def main():
        print("=" * 50)
        print("Database Module Test")
        print("=" * 50)
        print(f"Database: {args.db}")
        print()

        db = Database(args.db)
        await db.initialize()

        # Test reading operations
        print("Testing reading operations...")
        reading = OxiReading(
            timestamp=datetime.now(),
            spo2=97,
            heart_rate=72,
            battery_level=85,
            movement=0,
            is_valid=True,
        )
        row_id = await db.insert_reading(reading, AVAPSState.OFF)
        print(f"  Inserted reading ID: {row_id}")

        latest = await db.get_latest_reading()
        print(f"  Latest reading: SpO2={latest['spo2']}%, HR={latest['heart_rate']}bpm")

        # Test alert operations
        print("\nTesting alert operations...")
        alert = Alert(
            id="test-alert-001",
            timestamp=datetime.now(),
            alert_type=AlertType.TEST,
            severity=AlertSeverity.INFO,
            message="Test alert",
            spo2=97,
            heart_rate=72,
            avaps_state=AVAPSState.OFF,
        )
        await db.insert_alert(alert)
        print(f"  Inserted alert: {alert.id}")

        active = await db.get_active_alerts()
        print(f"  Active alerts: {len(active)}")

        await db.acknowledge_alert(alert.id, "test_user")
        print(f"  Acknowledged alert: {alert.id}")

        # Test event operations
        print("\nTesting event operations...")
        event_id = await db.log_event(
            "test",
            "Test event message",
            {"key": "value"}
        )
        print(f"  Logged event ID: {event_id}")

        events = await db.get_events(event_type="test")
        print(f"  Retrieved {len(events)} test events")

        # Test user/session operations
        print("\nTesting user/session operations...")
        try:
            user_id = await db.create_user("testuser", "hashed_password_here")
            print(f"  Created user ID: {user_id}")
        except Exception as e:
            print(f"  User already exists or error: {e}")
            user = await db.get_user("testuser")
            user_id = user["id"] if user else None

        if user_id:
            await db.create_session(user_id, "test-session-123")
            print(f"  Created session")

            session = await db.get_session("test-session-123")
            print(f"  Session user: {session['username'] if session else 'Not found'}")

            await db.delete_session("test-session-123")
            print(f"  Deleted session")

        # Get stats
        print("\nTesting stats...")
        now = datetime.now()
        stats = await db.get_reading_stats(
            now - timedelta(hours=1),
            now
        )
        print(f"  Stats: {stats}")

        await db.close()

        print()
        print("=" * 50)
        print("All tests passed!")
        print("=" * 50)

        if args.clean and os.path.exists(args.db):
            os.remove(args.db)
            print(f"Removed test database: {args.db}")

    asyncio.run(main())
