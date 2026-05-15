# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""FastAPI application factory for vision service."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vision.api.routes import cameras, config_routes, enrollment, health, status
from vision.capture.camera_manager import get_camera_manager
from vision.config import get_settings
from vision.detection.pipeline import get_pipeline

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Vision service starting...")

    settings = get_settings()

    # Load detection models
    pipeline = get_pipeline()
    if not pipeline.load_models():
        logger.error("Failed to load detection models")
    else:
        logger.info(f"Detection models loaded, {pipeline.enrolled_faces_count} faces enrolled")

    # Load cameras
    manager = get_camera_manager()
    count = manager.load_cameras()
    logger.info(f"Loaded {count} cameras")

    # Start camera scheduler
    manager.start_scheduler()

    logger.info(
        f"Vision service ready on {settings.server.api_host}:{settings.server.api_port}"
    )

    yield

    # Shutdown
    logger.info("Vision service shutting down...")
    manager.stop_scheduler()
    logger.info("Vision service stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app
    """
    settings = get_settings()

    app = FastAPI(
        title="O2Monitor Vision Service",
        description=(
            "Vision-based sleep monitoring service for detecting when "
            "the target person falls asleep without their AVAPS mask. "
            "NOT FOR MEDICAL USE - proof of concept only."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(status.router, tags=["Status"])
    app.include_router(cameras.router, prefix="/cameras", tags=["Cameras"])
    app.include_router(enrollment.router, tags=["Enrollment"])
    app.include_router(config_routes.router, prefix="/config", tags=["Configuration"])

    return app


# Create default app instance for uvicorn
app = create_app()
