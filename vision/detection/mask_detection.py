# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""AVAPS mask detection using YOLO or heuristic approaches.

Detects whether the AVAPS/CPAP mask is present on the face.

Initial implementation uses a face mask detection model as a proxy,
since both cover the lower face. Can be improved with custom training
on AVAPS mask images.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Lazy import ultralytics
_yolo_model = None


def _get_yolo_model():
    """Lazy load YOLO model for mask detection.

    Uses a pre-trained face mask detection model.
    """
    global _yolo_model
    if _yolo_model is None:
        try:
            from ultralytics import YOLO

            # Use YOLOv8n (nano) for speed - can upgrade to larger model if needed
            # This model detects general objects; we'll look for face-related classes
            # For production, train a custom model on AVAPS mask images
            _yolo_model = YOLO("yolov8n.pt")
            logger.info("YOLO model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise
    return _yolo_model


@dataclass
class MaskDetectionResult:
    """Result of mask detection."""

    detected: bool = False  # True if analysis was performed
    mask_present: bool = False  # True if mask detected
    confidence: float = 0.0
    bbox: Optional[Tuple[int, int, int, int]] = None  # Mask bounding box
    method: str = "none"  # Detection method used
    error: Optional[str] = None


class MaskDetector:
    """Detects AVAPS/CPAP mask presence.

    Uses multiple detection strategies:
    1. YOLO object detection (if trained model available)
    2. Lower face occlusion analysis (heuristic fallback)

    The AVAPS mask covers nose and mouth, similar to medical face masks
    but with distinctive straps and shape.
    """

    def __init__(self, confidence_threshold: float = 0.5):
        """Initialize mask detector.

        Args:
            confidence_threshold: Minimum confidence for detection
        """
        self.confidence_threshold = confidence_threshold
        self._model_loaded = False
        self._use_heuristic = False  # Fall back to heuristic if YOLO unavailable

    def load_model(self) -> bool:
        """Load the YOLO model.

        Returns:
            True if model loaded successfully
        """
        try:
            _get_yolo_model()
            self._model_loaded = True
            return True
        except Exception as e:
            logger.warning(f"YOLO model not available, using heuristic detection: {e}")
            self._use_heuristic = True
            self._model_loaded = True  # Mark as loaded even with fallback
            return True

    @property
    def is_model_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model_loaded

    def _detect_with_yolo(
        self,
        frame: np.ndarray,
        bbox: Optional[Tuple[int, int, int, int]] = None,
    ) -> MaskDetectionResult:
        """Detect mask using YOLO.

        Note: Standard YOLO models don't have an AVAPS mask class.
        This is a placeholder for when a custom-trained model is available.

        For now, we use the presence/absence of face occlusion as a proxy.
        """
        try:
            model = _get_yolo_model()

            # Run detection on full frame or cropped region
            if bbox:
                x, y, w, h = bbox
                # Add padding for lower face region
                y_lower = y + int(h * 0.4)  # Focus on lower 60% of face
                crop = frame[y_lower : y + h, x : x + w]
                results = model(crop, verbose=False)
            else:
                results = model(frame, verbose=False)

            # Look for objects that might indicate mask presence
            # Standard YOLO classes that might relate to masks:
            # - "person" (class 0) - face visible
            # - Objects covering face area

            # For now, return unknown - needs custom model
            return MaskDetectionResult(
                detected=True,
                mask_present=False,  # Default to no mask without custom model
                confidence=0.0,
                method="yolo_placeholder",
            )

        except Exception as e:
            logger.error(f"YOLO detection error: {e}")
            return MaskDetectionResult(detected=False, error=str(e))

    def _detect_with_heuristic(
        self,
        frame: np.ndarray,
        bbox: Optional[Tuple[int, int, int, int]] = None,
        face_landmarks: Optional[np.ndarray] = None,
    ) -> MaskDetectionResult:
        """Detect mask using heuristic analysis.

        Analyzes the lower face region for characteristics of mask presence:
        - Color uniformity (masks tend to be uniform color)
        - Edge patterns (mask edges are distinctive)
        - Skin visibility (less skin visible with mask)

        This is a simple heuristic and may have false positives/negatives.
        """
        try:
            import cv2

            if bbox is None:
                # Can't do heuristic without face location
                return MaskDetectionResult(
                    detected=False,
                    error="Face bbox required for heuristic detection",
                )

            x, y, w, h = bbox
            height, width = frame.shape[:2]

            # Extract lower face region (nose and mouth area)
            y_lower = y + int(h * 0.4)
            y_bottom = min(y + h, height)
            x_left = max(0, x)
            x_right = min(x + w, width)

            if y_lower >= y_bottom or x_left >= x_right:
                return MaskDetectionResult(detected=False, error="Invalid face region")

            lower_face = frame[y_lower:y_bottom, x_left:x_right]

            if lower_face.size == 0:
                return MaskDetectionResult(detected=False, error="Empty face region")

            # Convert to different color spaces for analysis
            hsv = cv2.cvtColor(lower_face, cv2.COLOR_BGR2HSV)
            gray = cv2.cvtColor(lower_face, cv2.COLOR_BGR2GRAY)

            # Heuristic 1: Color variance
            # Masks tend to have lower color variance than skin
            color_std = np.std(hsv[:, :, 0])  # Hue channel variance

            # Heuristic 2: Edge density
            # Masks have distinct edges (straps, outline)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size

            # Heuristic 3: Saturation
            # Skin typically has higher saturation than masks
            avg_saturation = np.mean(hsv[:, :, 1])

            # Combine heuristics (tuned thresholds)
            # These thresholds may need adjustment based on actual AVAPS mask appearance
            mask_indicators = 0

            if color_std < 30:  # Low hue variance suggests mask
                mask_indicators += 1
            if edge_density > 0.05:  # High edge density suggests mask straps
                mask_indicators += 1
            if avg_saturation < 80:  # Low saturation suggests mask
                mask_indicators += 1

            # Require at least 2 indicators for mask detection
            mask_present = mask_indicators >= 2
            confidence = mask_indicators / 3.0

            return MaskDetectionResult(
                detected=True,
                mask_present=mask_present,
                confidence=confidence,
                method="heuristic",
            )

        except Exception as e:
            logger.error(f"Heuristic detection error: {e}")
            return MaskDetectionResult(detected=False, error=str(e))

    def detect(
        self,
        frame: np.ndarray,
        bbox: Optional[Tuple[int, int, int, int]] = None,
        face_landmarks: Optional[np.ndarray] = None,
    ) -> MaskDetectionResult:
        """Detect if AVAPS mask is present.

        Args:
            frame: BGR image (OpenCV format)
            bbox: Face bounding box (x, y, w, h) for focused detection
            face_landmarks: Optional facial landmarks for improved accuracy

        Returns:
            MaskDetectionResult with detection status
        """
        if not self._model_loaded:
            self.load_model()

        # Use heuristic if YOLO not available or bbox provided
        if self._use_heuristic or bbox is not None:
            return self._detect_with_heuristic(frame, bbox, face_landmarks)
        else:
            return self._detect_with_yolo(frame, bbox)

    def detect_simple(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
    ) -> MaskDetectionResult:
        """Simple mask detection focused on face region.

        This is a simplified interface that always uses heuristic detection
        with the provided face bounding box.

        Args:
            frame: BGR image
            bbox: Face bounding box (x, y, w, h)

        Returns:
            MaskDetectionResult
        """
        return self._detect_with_heuristic(frame, bbox)
