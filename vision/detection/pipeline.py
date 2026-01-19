# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Detection pipeline orchestrator.

Coordinates face recognition, eye state detection, and mask detection
into a single processing pipeline for each frame.
"""

import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from vision.config import Settings, get_settings
from vision.detection.eye_state import EyeStateDetector
from vision.detection.face_recognition import FaceRecognizer
from vision.detection.mask_detection import MaskDetector
from vision.models.camera import (
    DetectionResult,
    EyeState,
    MaskState,
    PersonIdentity,
)

logger = logging.getLogger(__name__)


class DetectionPipeline:
    """Orchestrates the detection pipeline for a single frame.

    Pipeline stages:
    1. Face detection + recognition (is it dad?)
    2. Eye state detection (open/closed via EAR)
    3. Mask detection (AVAPS mask present?)

    Stages 2 and 3 only run if dad is detected (optimization).
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        embeddings_dir: Optional[Path] = None,
    ):
        """Initialize detection pipeline.

        Args:
            settings: Vision settings (uses global if not provided)
            embeddings_dir: Directory for face embeddings (uses settings if not provided)
        """
        self.settings = settings or get_settings()

        # Initialize detection modules
        embeddings_path = embeddings_dir or self.settings.embeddings_dir
        self._face_recognizer = FaceRecognizer(embeddings_path)
        self._eye_detector = EyeStateDetector(
            closed_threshold=self.settings.detection.ear_closed_threshold,
            open_threshold=self.settings.detection.ear_open_threshold,
        )
        self._mask_detector = MaskDetector()

        self._models_loaded = False

    def load_models(self) -> bool:
        """Load all detection models.

        Returns:
            True if all models loaded successfully
        """
        logger.info("Loading detection models...")
        start_time = time.time()

        success = True

        # Load face recognition model
        if not self._face_recognizer.load_model():
            logger.error("Failed to load face recognition model")
            success = False

        # Load enrolled face embeddings
        self._face_recognizer.load_embeddings()

        # Load eye detection model
        if not self._eye_detector.load_model():
            logger.error("Failed to load eye detection model")
            success = False

        # Load mask detection model
        if not self._mask_detector.load_model():
            logger.warning("Mask detection using heuristic fallback")
            # Not a failure - heuristic still works

        elapsed = time.time() - start_time
        logger.info(f"Detection models loaded in {elapsed:.2f}s")

        self._models_loaded = success
        return success

    @property
    def is_models_loaded(self) -> bool:
        """Check if models are loaded."""
        return self._models_loaded

    @property
    def enrolled_faces_count(self) -> int:
        """Number of enrolled face embeddings."""
        return self._face_recognizer.enrolled_count

    def enroll_face(self, frame: np.ndarray, name: str = "dad") -> Optional[Path]:
        """Enroll a face from an image frame.

        Args:
            frame: BGR image
            name: Base name for embedding file

        Returns:
            Path to saved embedding, or None if failed
        """
        return self._face_recognizer.enroll_face(frame, name)

    def delete_all_embeddings(self) -> int:
        """Delete all enrolled face embeddings.

        Returns:
            Number of embeddings deleted
        """
        return self._face_recognizer.delete_all_embeddings()

    def process_frame(
        self,
        frame: np.ndarray,
        camera_id: str = "",
        skip_if_not_dad: bool = True,
    ) -> DetectionResult:
        """Process a single frame through the detection pipeline.

        Args:
            frame: BGR image (OpenCV format)
            camera_id: ID of the camera (for tracking)
            skip_if_not_dad: If True, skip eye/mask detection if dad not detected

        Returns:
            DetectionResult with all detection information
        """
        start_time = time.time()

        result = DetectionResult(camera_id=camera_id)

        try:
            # Stage 1: Face detection + recognition
            face_result = self._face_recognizer.detect_and_recognize(
                frame,
                threshold=self.settings.detection.face_similarity_threshold,
            )

            if face_result.error:
                result.error = f"Face detection error: {face_result.error}"
                return result

            if not face_result.face_detected:
                # No face found
                result.face_detected = False
                result.person = PersonIdentity.NO_FACE
                result.inference_time_ms = (time.time() - start_time) * 1000
                return result

            # Face detected
            result.face_detected = True
            result.face_bbox = face_result.bbox
            result.face_confidence = face_result.confidence

            if face_result.is_target:
                result.person = PersonIdentity.DAD
            else:
                result.person = PersonIdentity.UNKNOWN

            # Early exit if not dad and skip_if_not_dad is True
            if skip_if_not_dad and result.person != PersonIdentity.DAD:
                result.inference_time_ms = (time.time() - start_time) * 1000
                return result

            # Stage 2: Eye state detection
            if face_result.bbox:
                eye_result = self._eye_detector.detect_with_bbox(frame, face_result.bbox)
            else:
                eye_result = self._eye_detector.detect(frame)

            if eye_result.detected:
                result.ear_left = eye_result.ear_left
                result.ear_right = eye_result.ear_right
                result.ear_average = eye_result.ear_average

                if eye_result.is_closed:
                    result.eye_state = EyeState.CLOSED
                else:
                    result.eye_state = EyeState.OPEN
            else:
                result.eye_state = EyeState.UNKNOWN
                if eye_result.error:
                    logger.debug(f"Eye detection issue: {eye_result.error}")

            # Stage 3: Mask detection
            if face_result.bbox:
                mask_result = self._mask_detector.detect_simple(frame, face_result.bbox)
            else:
                mask_result = self._mask_detector.detect(frame)

            if mask_result.detected:
                result.mask_confidence = mask_result.confidence
                if mask_result.mask_present:
                    result.mask_state = MaskState.PRESENT
                else:
                    result.mask_state = MaskState.ABSENT
            else:
                result.mask_state = MaskState.UNKNOWN
                if mask_result.error:
                    logger.debug(f"Mask detection issue: {mask_result.error}")

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            result.error = str(e)

        result.inference_time_ms = (time.time() - start_time) * 1000
        return result

    def check_alert_condition(self, result: DetectionResult) -> bool:
        """Check if detection result meets alert criteria.

        Alert condition:
            dad detected AND eyes closed AND no mask

        Args:
            result: Detection result to check

        Returns:
            True if alert condition is met
        """
        return (
            result.person == PersonIdentity.DAD
            and result.eye_state == EyeState.CLOSED
            and result.mask_state == MaskState.ABSENT
        )


# Global pipeline instance (lazy loaded)
_pipeline: Optional[DetectionPipeline] = None


def get_pipeline() -> DetectionPipeline:
    """Get or create the global detection pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = DetectionPipeline()
    return _pipeline
