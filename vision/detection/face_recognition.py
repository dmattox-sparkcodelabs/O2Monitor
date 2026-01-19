# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Face detection and recognition using InsightFace/ArcFace.

Detects faces in frames and compares against enrolled embeddings to
identify the target person (dad).
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Lazy import insightface to allow GPU configuration first
_face_analysis = None


def _get_face_analysis():
    """Lazy load InsightFace FaceAnalysis."""
    global _face_analysis
    if _face_analysis is None:
        try:
            from insightface.app import FaceAnalysis

            # Use buffalo_l model - good balance of speed and accuracy
            _face_analysis = FaceAnalysis(
                name="buffalo_l",
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            # Prepare for 640x640 input (can handle other sizes)
            _face_analysis.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("InsightFace model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load InsightFace model: {e}")
            raise
    return _face_analysis


@dataclass
class FaceDetection:
    """Result of face detection on a single face."""

    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    confidence: float
    embedding: np.ndarray  # 512-dimensional embedding
    landmarks: Optional[np.ndarray] = None  # 5-point facial landmarks


@dataclass
class RecognitionResult:
    """Result of face recognition against enrolled faces."""

    face_detected: bool = False
    is_target: bool = False  # True if matched against enrolled face
    confidence: float = 0.0  # Similarity score (0-1)
    bbox: Optional[Tuple[int, int, int, int]] = None
    embedding: Optional[np.ndarray] = None
    landmarks: Optional[np.ndarray] = None
    error: Optional[str] = None


class FaceRecognizer:
    """Face detection and recognition using InsightFace.

    Usage:
        recognizer = FaceRecognizer(embeddings_dir)
        recognizer.load_embeddings()  # Load enrolled faces
        result = recognizer.detect_and_recognize(frame, threshold=0.6)
    """

    def __init__(self, embeddings_dir: Path):
        """Initialize face recognizer.

        Args:
            embeddings_dir: Directory containing enrolled face embeddings (.npy files)
        """
        self.embeddings_dir = Path(embeddings_dir)
        self.enrolled_embeddings: List[np.ndarray] = []
        self._model_loaded = False

    def load_model(self) -> bool:
        """Load the InsightFace model.

        Returns:
            True if model loaded successfully
        """
        try:
            _get_face_analysis()
            self._model_loaded = True
            return True
        except Exception as e:
            logger.error(f"Failed to load face recognition model: {e}")
            return False

    @property
    def is_model_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model_loaded

    def load_embeddings(self) -> int:
        """Load enrolled face embeddings from disk.

        Returns:
            Number of embeddings loaded
        """
        self.enrolled_embeddings = []
        self.embeddings_dir.mkdir(parents=True, exist_ok=True)

        for npy_file in self.embeddings_dir.glob("*.npy"):
            try:
                embedding = np.load(npy_file)
                if embedding.shape == (512,):
                    self.enrolled_embeddings.append(embedding)
                    logger.debug(f"Loaded embedding from {npy_file.name}")
                else:
                    logger.warning(f"Invalid embedding shape in {npy_file.name}: {embedding.shape}")
            except Exception as e:
                logger.error(f"Failed to load embedding {npy_file.name}: {e}")

        logger.info(f"Loaded {len(self.enrolled_embeddings)} enrolled face embeddings")
        return len(self.enrolled_embeddings)

    def enroll_face(self, frame: np.ndarray, name: str = "dad") -> Optional[Path]:
        """Enroll a face from an image frame.

        Args:
            frame: BGR image (OpenCV format)
            name: Base name for the embedding file

        Returns:
            Path to saved embedding file, or None if no face detected
        """
        if not self._model_loaded:
            self.load_model()

        app = _get_face_analysis()
        faces = app.get(frame)

        if not faces:
            logger.warning("No face detected in enrollment image")
            return None

        # Use the largest face (closest to camera)
        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

        # Generate unique filename
        existing = list(self.embeddings_dir.glob(f"{name}_*.npy"))
        index = len(existing) + 1
        filename = f"{name}_{index:03d}.npy"
        filepath = self.embeddings_dir / filename

        # Save embedding
        np.save(filepath, face.embedding)
        logger.info(f"Enrolled face saved to {filename}")

        # Reload embeddings
        self.load_embeddings()

        return filepath

    def delete_all_embeddings(self) -> int:
        """Delete all enrolled face embeddings.

        Returns:
            Number of embeddings deleted
        """
        count = 0
        for npy_file in self.embeddings_dir.glob("*.npy"):
            try:
                npy_file.unlink()
                count += 1
            except Exception as e:
                logger.error(f"Failed to delete {npy_file.name}: {e}")

        self.enrolled_embeddings = []
        logger.info(f"Deleted {count} face embeddings")
        return count

    def detect_faces(self, frame: np.ndarray) -> List[FaceDetection]:
        """Detect all faces in a frame.

        Args:
            frame: BGR image (OpenCV format)

        Returns:
            List of FaceDetection objects
        """
        if not self._model_loaded:
            self.load_model()

        app = _get_face_analysis()
        faces = app.get(frame)

        detections = []
        for face in faces:
            bbox = face.bbox.astype(int)
            # Convert from (x1, y1, x2, y2) to (x, y, w, h)
            x, y = int(bbox[0]), int(bbox[1])
            w, h = int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])

            detections.append(
                FaceDetection(
                    bbox=(x, y, w, h),
                    confidence=float(face.det_score),
                    embedding=face.embedding,
                    landmarks=face.kps if hasattr(face, "kps") else None,
                )
            )

        return detections

    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings.

        Args:
            embedding1: First 512-dim embedding
            embedding2: Second 512-dim embedding

        Returns:
            Similarity score (0-1, higher = more similar)
        """
        # Normalize embeddings
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        # Cosine similarity
        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)

        # Convert from [-1, 1] to [0, 1]
        return float((similarity + 1) / 2)

    def match_against_enrolled(self, embedding: np.ndarray, threshold: float = 0.6) -> Tuple[bool, float]:
        """Check if an embedding matches any enrolled face.

        Args:
            embedding: 512-dim face embedding to check
            threshold: Minimum similarity score for a match (0-1)

        Returns:
            Tuple of (is_match, best_similarity_score)
        """
        if not self.enrolled_embeddings:
            return False, 0.0

        best_similarity = 0.0
        for enrolled in self.enrolled_embeddings:
            similarity = self.compute_similarity(embedding, enrolled)
            best_similarity = max(best_similarity, similarity)

        is_match = best_similarity >= threshold
        return is_match, best_similarity

    def detect_and_recognize(
        self,
        frame: np.ndarray,
        threshold: float = 0.6,
    ) -> RecognitionResult:
        """Detect face and check if it matches enrolled person.

        Args:
            frame: BGR image (OpenCV format)
            threshold: Minimum similarity score for a match

        Returns:
            RecognitionResult with detection and recognition info
        """
        try:
            detections = self.detect_faces(frame)

            if not detections:
                return RecognitionResult(face_detected=False)

            # Use the largest face (closest to camera)
            detection = max(detections, key=lambda d: d.bbox[2] * d.bbox[3])

            # Check against enrolled faces
            is_match, similarity = self.match_against_enrolled(detection.embedding, threshold)

            return RecognitionResult(
                face_detected=True,
                is_target=is_match,
                confidence=similarity,
                bbox=detection.bbox,
                embedding=detection.embedding,
                landmarks=detection.landmarks,
            )

        except Exception as e:
            logger.error(f"Face recognition error: {e}")
            return RecognitionResult(face_detected=False, error=str(e))

    @property
    def enrolled_count(self) -> int:
        """Number of enrolled face embeddings."""
        return len(self.enrolled_embeddings)
