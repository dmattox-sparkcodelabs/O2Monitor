# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Camera management endpoints."""

from enum import Enum
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from vision.capture.camera_manager import get_camera_manager
from vision.models.camera import CaptureType

router = APIRouter()


class CaptureTypeAPI(str, Enum):
    """Capture type for API requests."""

    http = "http"
    rtsp = "rtsp"


class CameraCreate(BaseModel):
    """Request body for creating a camera.

    Use either snapshot_url (for HTTP capture, preferred for Amcrest)
    or rtsp_url (for RTSP stream).
    """

    name: str
    capture_type: CaptureTypeAPI = CaptureTypeAPI.http
    snapshot_url: str = ""  # HTTP snapshot URL (preferred for Amcrest)
    rtsp_url: str = ""  # RTSP stream URL
    enabled: bool = True


class CameraUpdate(BaseModel):
    """Request body for updating a camera."""

    name: Optional[str] = None
    capture_type: Optional[CaptureTypeAPI] = None
    snapshot_url: Optional[str] = None
    rtsp_url: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("")
async def list_cameras():
    """List all configured cameras.

    Returns:
        List of camera configurations (URLs masked)
    """
    manager = get_camera_manager()
    cameras = manager.get_cameras()
    return [cam.to_dict(include_urls=False) for cam in cameras]


@router.post("")
async def add_camera(camera: CameraCreate):
    """Add a new camera.

    Args:
        camera: Camera configuration with either snapshot_url (HTTP) or rtsp_url (RTSP)

    Returns:
        Created camera object
    """
    manager = get_camera_manager()

    # Convert API enum to internal enum
    capture_type = CaptureType.HTTP if camera.capture_type == CaptureTypeAPI.http else CaptureType.RTSP

    created = manager.add_camera(
        name=camera.name,
        capture_type=capture_type,
        snapshot_url=camera.snapshot_url,
        rtsp_url=camera.rtsp_url,
        enabled=camera.enabled,
    )
    return created.to_dict(include_urls=False)


@router.get("/{camera_id}")
async def get_camera(camera_id: str):
    """Get a specific camera by ID.

    Args:
        camera_id: Camera ID

    Returns:
        Camera configuration
    """
    manager = get_camera_manager()
    camera = manager.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera.to_dict(include_urls=False)


@router.put("/{camera_id}")
async def update_camera(camera_id: str, update: CameraUpdate):
    """Update a camera's configuration.

    Args:
        camera_id: Camera ID
        update: Fields to update

    Returns:
        Updated camera object
    """
    manager = get_camera_manager()

    # Convert API enum to internal enum if provided
    capture_type = None
    if update.capture_type is not None:
        capture_type = CaptureType.HTTP if update.capture_type == CaptureTypeAPI.http else CaptureType.RTSP

    camera = manager.update_camera(
        camera_id,
        name=update.name,
        capture_type=capture_type,
        snapshot_url=update.snapshot_url,
        rtsp_url=update.rtsp_url,
        enabled=update.enabled,
    )
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera.to_dict(include_urls=False)


@router.delete("/{camera_id}")
async def delete_camera(camera_id: str):
    """Delete a camera.

    Args:
        camera_id: Camera ID

    Returns:
        Success message
    """
    manager = get_camera_manager()
    if not manager.remove_camera(camera_id):
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"status": "deleted", "camera_id": camera_id}


@router.get("/{camera_id}/status")
async def get_camera_status(camera_id: str):
    """Get detailed status for a specific camera.

    Args:
        camera_id: Camera ID

    Returns:
        Camera status with latest detection result
    """
    manager = get_camera_manager()
    camera = manager.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera.to_dict(include_urls=False)


@router.get("/{camera_id}/snapshot")
async def get_camera_snapshot(camera_id: str):
    """Get a live JPEG snapshot from a camera.

    Args:
        camera_id: Camera ID

    Returns:
        JPEG image
    """
    manager = get_camera_manager()
    camera = manager.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    jpeg_bytes = manager.capture_snapshot(camera_id)
    if not jpeg_bytes:
        raise HTTPException(status_code=503, detail="Failed to capture snapshot")

    return Response(content=jpeg_bytes, media_type="image/jpeg")


@router.post("/{camera_id}/poll")
async def poll_camera(camera_id: str):
    """Manually trigger a poll on a specific camera.

    Captures a frame, runs detection, and updates camera state.

    Args:
        camera_id: Camera ID

    Returns:
        Detection result
    """
    manager = get_camera_manager()
    camera = manager.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    result = manager.poll_camera(camera_id)
    if result is None:
        raise HTTPException(status_code=503, detail="Failed to poll camera")

    return result.to_dict()


@router.post("/{camera_id}/enable")
async def enable_camera(camera_id: str):
    """Enable a camera for monitoring.

    Args:
        camera_id: Camera ID

    Returns:
        Success message
    """
    manager = get_camera_manager()
    if not manager.enable_camera(camera_id):
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"status": "enabled", "camera_id": camera_id}


@router.post("/{camera_id}/disable")
async def disable_camera(camera_id: str):
    """Disable a camera from monitoring.

    Args:
        camera_id: Camera ID

    Returns:
        Success message
    """
    manager = get_camera_manager()
    if not manager.disable_camera(camera_id):
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"status": "disabled", "camera_id": camera_id}


@router.post("/{camera_id}/test")
async def test_camera_connection(camera_id: str):
    """Test connectivity to a camera.

    Args:
        camera_id: Camera ID

    Returns:
        Connection test result
    """
    from vision.capture.http_snapshot import HTTPCapture
    from vision.capture.rtsp_stream import RTSPCapture
    from vision.config import get_settings

    manager = get_camera_manager()
    camera = manager.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    settings = get_settings()

    # Create capture based on camera type
    if camera.capture_type == CaptureType.HTTP:
        capture = HTTPCapture(
            camera.snapshot_url,
            timeout_seconds=settings.camera.rtsp_timeout_seconds,
        )
    else:
        capture = RTSPCapture(
            camera.rtsp_url,
            timeout_seconds=settings.camera.rtsp_timeout_seconds,
        )

    success, message = capture.test_connection()
    return {
        "camera_id": camera_id,
        "capture_type": camera.capture_type.value,
        "success": success,
        "message": message,
    }
