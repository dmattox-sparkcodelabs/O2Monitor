# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Vision service entry point.

Starts the FastAPI server with uvicorn.

Usage:
    python -m vision.main
    python -m vision.main --host 0.0.0.0 --port 8100
"""

import argparse
import logging
import sys

import uvicorn

from vision.config import get_settings


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the vision service."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main():
    """Main entry point for vision service."""
    parser = argparse.ArgumentParser(
        description="O2Monitor Vision Service - Sleep monitoring with computer vision"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host to bind to (default: from settings)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind to (default: from settings)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    # Get settings
    settings = get_settings()

    # Override with CLI args if provided
    host = args.host or settings.server.api_host
    port = args.port or settings.server.api_port

    logger.info("=" * 60)
    logger.info("O2Monitor Vision Service")
    logger.info("NOT FOR MEDICAL USE - Proof of concept only")
    logger.info("=" * 60)
    logger.info(f"Starting server on {host}:{port}")

    # Run server
    uvicorn.run(
        "vision.api.server:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
