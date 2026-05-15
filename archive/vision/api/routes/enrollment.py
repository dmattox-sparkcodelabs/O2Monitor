# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Face enrollment endpoints."""

import io
import logging
from typing import List

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile

from vision.detection.pipeline import get_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/enroll")
async def enroll_face(files: List[UploadFile] = File(...)):
    """Enroll face images for recognition.

    Upload one or more photos of the target person (dad).
    Each image will be processed to extract face embeddings.

    Args:
        files: JPEG/PNG image files

    Returns:
        Enrollment result with number of faces enrolled
    """
    pipeline = get_pipeline()

    if not pipeline.is_models_loaded:
        raise HTTPException(
            status_code=503,
            detail="Detection models not loaded",
        )

    enrolled = []
    errors = []

    for file in files:
        try:
            # Read image
            contents = await file.read()
            nparr = np.frombuffer(contents, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame is None:
                errors.append(f"{file.filename}: Invalid image format")
                continue

            # Enroll face
            path = pipeline.enroll_face(frame, name="dad")
            if path:
                enrolled.append(file.filename)
                logger.info(f"Enrolled face from {file.filename}")
            else:
                errors.append(f"{file.filename}: No face detected")

        except Exception as e:
            errors.append(f"{file.filename}: {str(e)}")
            logger.error(f"Error enrolling {file.filename}: {e}")

    return {
        "enrolled_count": len(enrolled),
        "enrolled_files": enrolled,
        "errors": errors if errors else None,
        "total_enrolled": pipeline.enrolled_faces_count,
    }


@router.post("/enroll/camera/{camera_id}")
async def enroll_from_camera(camera_id: str):
    """Enroll a face from a live camera capture.

    Captures a frame from the specified camera and enrolls
    any detected face.

    Args:
        camera_id: Camera ID to capture from

    Returns:
        Enrollment result
    """
    from vision.capture.camera_manager import get_camera_manager

    pipeline = get_pipeline()
    manager = get_camera_manager()

    if not pipeline.is_models_loaded:
        raise HTTPException(
            status_code=503,
            detail="Detection models not loaded",
        )

    camera = manager.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Capture frame
    from vision.capture.rtsp_stream import RTSPCapture
    from vision.config import get_settings

    settings = get_settings()
    capture = RTSPCapture(
        camera.rtsp_url,
        timeout_seconds=settings.camera.rtsp_timeout_seconds,
    )

    result = capture.grab_frame_with_retry()
    if not result.success:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to capture frame: {result.error}",
        )

    # Enroll face
    path = pipeline.enroll_face(result.frame, name="dad")
    if not path:
        raise HTTPException(
            status_code=400,
            detail="No face detected in captured frame",
        )

    return {
        "enrolled": True,
        "camera_id": camera_id,
        "embedding_file": path.name,
        "total_enrolled": pipeline.enrolled_faces_count,
    }


@router.get("/enroll/status")
async def get_enrollment_status():
    """Get current enrollment status.

    Returns:
        Number of enrolled face embeddings
    """
    pipeline = get_pipeline()
    return {
        "enrolled_count": pipeline.enrolled_faces_count,
        "models_loaded": pipeline.is_models_loaded,
    }


@router.delete("/enroll")
async def delete_all_enrollments():
    """Delete all enrolled face embeddings.

    This will require re-enrollment before recognition works.

    Returns:
        Deletion result
    """
    pipeline = get_pipeline()
    count = pipeline.delete_all_embeddings()
    return {
        "deleted_count": count,
        "total_enrolled": pipeline.enrolled_faces_count,
    }
