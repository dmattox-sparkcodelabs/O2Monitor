# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Status endpoint - main polling endpoint for Pi."""

from fastapi import APIRouter

from vision.capture.camera_manager import get_camera_manager

router = APIRouter()


@router.get("/status")
async def get_status():
    """Get overall vision service status.

    This is the main endpoint that the Pi polls to check for alerts.

    Returns:
        VisionStatus with alert state and camera summaries:
        - timestamp: Current time
        - alert_active: True if alert condition met
        - alert_reason: Description of alert (if active)
        - alert_camera_id: Camera that triggered alert
        - alert_camera_name: Name of alert camera
        - eyes_closed_seconds: How long eyes have been closed
        - cameras: List of camera status summaries
        - system: System health info (models, GPU, uptime)
    """
    manager = get_camera_manager()
    status = manager.get_status()
    return status.to_dict()
