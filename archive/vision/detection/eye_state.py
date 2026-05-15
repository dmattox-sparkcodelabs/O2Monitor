# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Eye state detection using MediaPipe Face Mesh and Eye Aspect Ratio (EAR).

Detects whether eyes are open or closed based on facial landmarks.
Uses the Eye Aspect Ratio (EAR) algorithm from Soukupová and Čech (2016).
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Lazy import mediapipe
_face_mesh = None


def _get_face_mesh():
    """Lazy load MediaPipe Face Mesh."""
    global _face_mesh
    if _face_mesh is None:
        try:
            import mediapipe as mp

            _face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=1,
                refine_landmarks=True,  # Include iris landmarks
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            logger.info("MediaPipe Face Mesh loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load MediaPipe Face Mesh: {e}")
            raise
    return _face_mesh


# MediaPipe Face Mesh landmark indices for eyes
# Reference: https://github.com/google/mediapipe/blob/master/mediapipe/modules/face_geometry/data/canonical_face_model_uv_visualization.png

# Left eye landmarks (from viewer's perspective, person's right eye)
LEFT_EYE_INDICES = {
    "p1": 33,  # Outer corner
    "p2": 160,  # Upper lid outer
    "p3": 158,  # Upper lid inner
    "p4": 133,  # Inner corner
    "p5": 153,  # Lower lid inner
    "p6": 144,  # Lower lid outer
}

# Right eye landmarks (from viewer's perspective, person's left eye)
RIGHT_EYE_INDICES = {
    "p1": 362,  # Outer corner
    "p2": 385,  # Upper lid outer
    "p3": 387,  # Upper lid inner
    "p4": 263,  # Inner corner
    "p5": 373,  # Lower lid inner
    "p6": 380,  # Lower lid outer
}


@dataclass
class EyeStateResult:
    """Result of eye state detection."""

    detected: bool = False
    ear_left: float = 0.0
    ear_right: float = 0.0
    ear_average: float = 0.0
    is_closed: bool = False
    error: Optional[str] = None


class EyeStateDetector:
    """Detects eye state (open/closed) using MediaPipe Face Mesh.

    Uses Eye Aspect Ratio (EAR) to determine if eyes are open or closed.
    EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)

    Where p1-p6 are eye landmarks:
    - p1, p4: Horizontal corners
    - p2, p3: Upper lid
    - p5, p6: Lower lid

    Lower EAR values indicate closed eyes.
    """

    def __init__(
        self,
        closed_threshold: float = 0.2,
        open_threshold: float = 0.25,
    ):
        """Initialize eye state detector.

        Args:
            closed_threshold: EAR below this = eyes closed
            open_threshold: EAR above this = eyes open (hysteresis)
        """
        self.closed_threshold = closed_threshold
        self.open_threshold = open_threshold
        self._model_loaded = False
        self._last_state_closed = False  # For hysteresis

    def load_model(self) -> bool:
        """Load the MediaPipe Face Mesh model.

        Returns:
            True if model loaded successfully
        """
        try:
            _get_face_mesh()
            self._model_loaded = True
            return True
        except Exception as e:
            logger.error(f"Failed to load eye detection model: {e}")
            return False

    @property
    def is_model_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model_loaded

    def _euclidean_distance(self, p1: np.ndarray, p2: np.ndarray) -> float:
        """Calculate Euclidean distance between two points."""
        return float(np.linalg.norm(p1 - p2))

    def _calculate_ear(
        self,
        landmarks: np.ndarray,
        eye_indices: dict,
        image_width: int,
        image_height: int,
    ) -> float:
        """Calculate Eye Aspect Ratio for one eye.

        Args:
            landmarks: MediaPipe face landmarks
            eye_indices: Dictionary with p1-p6 landmark indices
            image_width: Image width for denormalization
            image_height: Image height for denormalization

        Returns:
            EAR value (higher = more open)
        """

        def get_point(idx: int) -> np.ndarray:
            lm = landmarks[idx]
            return np.array([lm.x * image_width, lm.y * image_height])

        # Get eye landmark points
        p1 = get_point(eye_indices["p1"])
        p2 = get_point(eye_indices["p2"])
        p3 = get_point(eye_indices["p3"])
        p4 = get_point(eye_indices["p4"])
        p5 = get_point(eye_indices["p5"])
        p6 = get_point(eye_indices["p6"])

        # Calculate EAR
        # Vertical distances
        v1 = self._euclidean_distance(p2, p6)
        v2 = self._euclidean_distance(p3, p5)
        # Horizontal distance
        h = self._euclidean_distance(p1, p4)

        if h == 0:
            return 0.0

        ear = (v1 + v2) / (2.0 * h)
        return ear

    def detect(self, frame: np.ndarray) -> EyeStateResult:
        """Detect eye state from an image frame.

        Args:
            frame: BGR image (OpenCV format)

        Returns:
            EyeStateResult with EAR values and closed state
        """
        if not self._model_loaded:
            self.load_model()

        try:
            import cv2

            # Convert BGR to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width = frame.shape[:2]

            # Process with Face Mesh
            face_mesh = _get_face_mesh()
            results = face_mesh.process(rgb_frame)

            if not results.multi_face_landmarks:
                return EyeStateResult(detected=False)

            # Use first detected face
            landmarks = results.multi_face_landmarks[0].landmark

            # Calculate EAR for both eyes
            ear_left = self._calculate_ear(landmarks, LEFT_EYE_INDICES, width, height)
            ear_right = self._calculate_ear(landmarks, RIGHT_EYE_INDICES, width, height)
            ear_avg = (ear_left + ear_right) / 2.0

            # Determine if eyes are closed using hysteresis
            if self._last_state_closed:
                # Currently closed, need EAR above open_threshold to be considered open
                is_closed = ear_avg < self.open_threshold
            else:
                # Currently open, need EAR below closed_threshold to be considered closed
                is_closed = ear_avg < self.closed_threshold

            self._last_state_closed = is_closed

            return EyeStateResult(
                detected=True,
                ear_left=ear_left,
                ear_right=ear_right,
                ear_average=ear_avg,
                is_closed=is_closed,
            )

        except Exception as e:
            logger.error(f"Eye state detection error: {e}")
            return EyeStateResult(detected=False, error=str(e))

    def detect_with_bbox(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        padding: float = 0.2,
    ) -> EyeStateResult:
        """Detect eye state within a bounding box region.

        Crops the frame to the face region before processing.
        This can improve accuracy when face is already detected.

        Args:
            frame: BGR image (OpenCV format)
            bbox: Face bounding box (x, y, w, h)
            padding: Extra padding around bbox as fraction of size

        Returns:
            EyeStateResult with EAR values and closed state
        """
        try:
            x, y, w, h = bbox
            height, width = frame.shape[:2]

            # Add padding
            pad_w = int(w * padding)
            pad_h = int(h * padding)

            # Clamp to image bounds
            x1 = max(0, x - pad_w)
            y1 = max(0, y - pad_h)
            x2 = min(width, x + w + pad_w)
            y2 = min(height, y + h + pad_h)

            # Crop face region
            face_crop = frame[y1:y2, x1:x2]

            # Detect on cropped region
            return self.detect(face_crop)

        except Exception as e:
            logger.error(f"Eye state detection with bbox error: {e}")
            return EyeStateResult(detected=False, error=str(e))

    def reset_state(self) -> None:
        """Reset hysteresis state."""
        self._last_state_closed = False
