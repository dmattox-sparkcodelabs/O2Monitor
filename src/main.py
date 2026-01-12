#!/usr/bin/env python3
"""O2 Monitor - Main Entry Point.

This is the main entry point for the O2 monitoring system.
It initializes all components and starts the monitoring loop.

Usage:
    python -m src.main [--config CONFIG] [--debug] [--mock]

Or directly:
    ./src/main.py [options]

The system monitors:
- SpO2 and heart rate via Checkme O2 Max (BLE)
- AVAPS therapy device power state via Kasa smart plug (WiFi)

When SpO2 drops below threshold while AVAPS is off, it triggers
local and remote alerts.
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.alerting import AlertManager
from src.avaps_monitor import get_monitor as get_avaps_monitor
from src.ble_reader import get_reader as get_ble_reader
from src.config import load_config
from src.database import Database
from src.state_machine import O2MonitorStateMachine
from src.web.app import create_app

logger = logging.getLogger(__name__)


def setup_logging(config, debug: bool = False) -> None:
    """Configure logging based on config settings.

    Args:
        config: Configuration object
        debug: Enable debug mode
    """
    # Determine log level
    level = logging.DEBUG if debug else getattr(
        logging, config.logging.level.upper(), logging.INFO
    )

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (if configured)
    if config.logging.file:
        # Ensure log directory exists
        log_dir = os.path.dirname(config.logging.file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = RotatingFileHandler(
            config.logging.file,
            maxBytes=config.logging.max_size_mb * 1024 * 1024,
            backupCount=config.logging.backup_count,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Reduce verbosity of some noisy libraries
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    logger.info(f"Logging configured (level: {logging.getLevelName(level)})")


class O2MonitorApp:
    """Main application class for O2 Monitor.

    Coordinates all components and manages the application lifecycle.
    """

    def __init__(self, config_path: str, debug: bool = False, mock: bool = False):
        """Initialize the application.

        Args:
            config_path: Path to configuration file
            debug: Enable debug logging
            mock: Force mock mode regardless of config
        """
        self.config_path = config_path
        self.debug = debug
        self.force_mock = mock

        # Components (initialized in start())
        self.config = None
        self.database: Optional[Database] = None
        self.ble_reader = None
        self.avaps_monitor = None
        self.alert_manager: Optional[AlertManager] = None
        self.state_machine: Optional[O2MonitorStateMachine] = None
        self.web_app = None
        self._web_thread: Optional[threading.Thread] = None
        self._ble_thread: Optional[threading.Thread] = None

        # Control
        self._running = False

    async def start(self) -> None:
        """Start the monitoring application."""
        logger.info("=" * 50)
        logger.info("O2 Monitor Starting")
        logger.info("=" * 50)

        # Load configuration
        self.config = load_config(self.config_path)

        # Override mock mode if requested
        if self.force_mock:
            self.config.mock_mode = True

        # Set up logging
        setup_logging(self.config, self.debug)

        logger.info(f"Config loaded from: {self.config_path}")
        logger.info(f"Mock mode: {self.config.mock_mode}")

        # Initialize components
        await self._initialize_components()

        # Start monitoring
        self._running = True
        logger.info("Starting monitoring loop")

        try:
            await self._run_monitoring()
        finally:
            await self._shutdown()

    async def _initialize_components(self) -> None:
        """Initialize all system components."""
        logger.info("Initializing components...")

        # Database
        logger.info("  - Database")
        self.database = Database(self.config.database.path)
        await self.database.initialize()

        # Alert Manager
        logger.info("  - Alert Manager")
        self.alert_manager = AlertManager(self.config)
        await self.alert_manager.initialize()

        # BLE Reader
        logger.info("  - BLE Reader")
        self.ble_reader = get_ble_reader(self.config)

        # AVAPS Monitor
        logger.info("  - AVAPS Monitor")
        self.avaps_monitor = get_avaps_monitor(self.config)

        # State Machine
        logger.info("  - State Machine")
        self.state_machine = O2MonitorStateMachine(
            config=self.config,
            ble_reader=self.ble_reader,
            avaps_monitor=self.avaps_monitor,
            alert_manager=self.alert_manager,
            database=self.database,
        )

        # Web Server
        logger.info("  - Web Server")
        self.web_app = create_app(
            config=self.config,
            state_machine=self.state_machine,
            database=self.database,
            alert_manager=self.alert_manager,
        )

        logger.info("All components initialized")

    def _start_web_server(self) -> None:
        """Start the web server in a background thread."""
        host = self.config.web.host
        port = self.config.web.port

        def run_flask():
            # Disable Flask's reloader in production
            self.web_app.run(
                host=host,
                port=port,
                debug=False,
                use_reloader=False,
                threaded=True,
            )

        self._web_thread = threading.Thread(target=run_flask, daemon=True)
        self._web_thread.start()
        logger.info(f"Web server started on http://{host}:{port}")

    async def _run_monitoring(self) -> None:
        """Run the main monitoring loop."""
        # Start web server
        self._start_web_server()

        if self.config.mock_mode:
            # Mock mode: BLE runs synchronously, state machine in main asyncio loop
            self.ble_reader.connect()
            self.ble_reader.start()
            try:
                await self.state_machine.run()
            except asyncio.CancelledError:
                logger.info("Monitoring cancelled")
        else:
            # Real hardware mode: BLE runs in subprocess (managed by ble_reader)
            # Run BLE reader in background thread, state machine in main asyncio loop
            self._ble_thread = threading.Thread(
                target=self._run_ble_with_reconnect,
                daemon=True,
            )
            self._ble_thread.start()
            logger.info("BLE reader thread started")

            # Start watchdog in background thread
            watchdog_thread = threading.Thread(
                target=self._ble_watchdog,
                daemon=True,
            )
            watchdog_thread.start()

            # Run state machine in main asyncio loop
            try:
                await self.state_machine.run()
            except asyncio.CancelledError:
                logger.info("Monitoring cancelled")

    def _run_ble_with_reconnect(self) -> None:
        """Run BLE reader with automatic reconnection on failure."""
        reconnect_delay = 5  # seconds between reconnection attempts

        while self._running:
            try:
                logger.info("BLE reader starting...")
                # run() spawns subprocess, blocks while processing readings
                self.ble_reader.run(num_readings=-1)  # -1 = infinite
            except Exception as e:
                logger.error(f"BLE reader error: {e}")

            # If we get here, the reader stopped (disconnect, error, etc.)
            if self._running:
                logger.warning(f"BLE reader stopped, reconnecting in {reconnect_delay} seconds...")
                time.sleep(reconnect_delay)

    def _ble_watchdog(self) -> None:
        """Monitor BLE connection and force reconnect if stale."""
        stale_threshold = 60  # seconds without reading before forcing reconnect

        # Wait for BLE reader to connect initially
        time.sleep(15)

        while self._running:
            time.sleep(5)  # Check every 5 seconds

            # Skip if not connected yet
            if not self.ble_reader._connected:
                continue

            # Check if readings are stale
            last_time = self.ble_reader._last_reading_time
            if last_time > 0:
                elapsed = time.time() - last_time
                if elapsed > stale_threshold:
                    logger.warning(f"No BLE reading for {int(elapsed)}s, forcing reconnect...")
                    try:
                        self.ble_reader.stop()
                    except Exception as e:
                        logger.error(f"Error stopping BLE reader: {e}")
                    # Give time for reconnect to happen
                    time.sleep(10)

    async def _shutdown(self) -> None:
        """Clean shutdown of all components."""
        logger.info("Shutting down...")
        self._running = False

        # Stop state machine
        if self.state_machine:
            self.state_machine.stop()

        # Stop BLE reader
        if self.ble_reader:
            self.ble_reader.stop()

        # Close alert manager
        if self.alert_manager:
            await self.alert_manager.close()

        # Close database
        if self.database:
            await self.database.close()

        logger.info("Shutdown complete")

    def stop(self) -> None:
        """Request application stop."""
        self._running = False
        if self.state_machine:
            self.state_machine.stop()
        if self.ble_reader:
            self.ble_reader.stop()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="O2 Monitoring System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default config
    python -m src.main

    # Run in debug mode with mock hardware
    python -m src.main --debug --mock

    # Use custom config file
    python -m src.main --config /path/to/config.yaml
        """
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--mock", "-m",
        action="store_true",
        help="Use mock hardware (for testing)"
    )
    args = parser.parse_args()

    # Check config file exists
    if not os.path.exists(args.config):
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)

    # Create and run application
    app = O2MonitorApp(
        config_path=args.config,
        debug=args.debug,
        mock=args.mock,
    )

    # Set up signal handlers
    def handle_signal(sig, frame):
        logger.info(f"Received signal {sig}")
        app.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
