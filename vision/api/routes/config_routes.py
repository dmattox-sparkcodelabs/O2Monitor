# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Configuration endpoints."""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from vision.config import get_settings

router = APIRouter()


class ConfigUpdate(BaseModel):
    """Request body for updating configuration."""

    # Detection thresholds
    eyes_closed_alert_seconds: Optional[int] = Field(
        None,
        ge=30,
        le=1800,
        description="Seconds eyes must be closed before alert (30-1800)",
    )
    dad_gone_timeout_seconds: Optional[int] = Field(
        None,
        ge=60,
        le=3600,
        description="Seconds before returning to IDLE when dad leaves (60-3600)",
    )
    face_similarity_threshold: Optional[float] = Field(
        None,
        ge=0.3,
        le=0.95,
        description="Face similarity threshold for recognition (0.3-0.95)",
    )
    ear_closed_threshold: Optional[float] = Field(
        None,
        ge=0.1,
        le=0.3,
        description="EAR below this = eyes closed (0.1-0.3)",
    )
    ear_open_threshold: Optional[float] = Field(
        None,
        ge=0.15,
        le=0.4,
        description="EAR above this = eyes open (0.15-0.4)",
    )

    # Polling intervals
    idle_poll_seconds: Optional[int] = Field(
        None,
        ge=30,
        le=600,
        description="Poll interval in IDLE state (30-600)",
    )
    active_poll_seconds: Optional[int] = Field(
        None,
        ge=10,
        le=120,
        description="Poll interval in ACTIVE state (10-120)",
    )
    alert_poll_seconds: Optional[int] = Field(
        None,
        ge=10,
        le=120,
        description="Poll interval in ALERT state (10-120)",
    )


@router.get("")
async def get_config():
    """Get current configuration.

    Returns:
        Current settings for detection and polling
    """
    settings = get_settings()
    return {
        "detection": {
            "eyes_closed_alert_seconds": settings.detection.eyes_closed_alert_seconds,
            "dad_gone_timeout_seconds": settings.detection.dad_gone_timeout_seconds,
            "face_similarity_threshold": settings.detection.face_similarity_threshold,
            "ear_closed_threshold": settings.detection.ear_closed_threshold,
            "ear_open_threshold": settings.detection.ear_open_threshold,
        },
        "camera": {
            "idle_poll_seconds": settings.camera.idle_poll_seconds,
            "active_poll_seconds": settings.camera.active_poll_seconds,
            "alert_poll_seconds": settings.camera.alert_poll_seconds,
            "rtsp_timeout_seconds": settings.camera.rtsp_timeout_seconds,
            "max_retries": settings.camera.max_retries,
        },
        "server": {
            "api_host": settings.server.api_host,
            "api_port": settings.server.api_port,
        },
        "gpu": {
            "device": settings.gpu.device,
        },
    }


@router.post("")
async def update_config(update: ConfigUpdate):
    """Update configuration.

    Note: Changes are applied in-memory only. For persistence,
    set environment variables or config files.

    Args:
        update: Configuration values to update

    Returns:
        Updated configuration
    """
    settings = get_settings()

    # Update detection settings
    if update.eyes_closed_alert_seconds is not None:
        settings.detection.eyes_closed_alert_seconds = update.eyes_closed_alert_seconds
    if update.dad_gone_timeout_seconds is not None:
        settings.detection.dad_gone_timeout_seconds = update.dad_gone_timeout_seconds
    if update.face_similarity_threshold is not None:
        settings.detection.face_similarity_threshold = update.face_similarity_threshold
    if update.ear_closed_threshold is not None:
        settings.detection.ear_closed_threshold = update.ear_closed_threshold
    if update.ear_open_threshold is not None:
        settings.detection.ear_open_threshold = update.ear_open_threshold

    # Update camera settings
    if update.idle_poll_seconds is not None:
        settings.camera.idle_poll_seconds = update.idle_poll_seconds
    if update.active_poll_seconds is not None:
        settings.camera.active_poll_seconds = update.active_poll_seconds
    if update.alert_poll_seconds is not None:
        settings.camera.alert_poll_seconds = update.alert_poll_seconds

    return await get_config()


@router.post("/reset")
async def reset_config():
    """Reset configuration to defaults.

    Note: This creates a new settings instance with default values.

    Returns:
        Default configuration
    """
    from vision.config import Settings

    # Reset global settings
    import vision.config

    vision.config._settings = Settings()

    return await get_config()
