# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Data models for vision service cameras and detection results."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class CaptureType(Enum):
    """Camera capture method."""

    RTSP = "rtsp"  # RTSP video stream (use for cameras with only RTSP)
    HTTP = "http"  # HTTP snapshot endpoint (simpler, preferred for Amcrest)


class CameraState(Enum):
    """Camera monitoring state machine states."""

    IDLE = "idle"  # Dad not detected, polling every 5 min
    ACTIVE = "active"  # Dad detected, polling every 1 min
    ALERT = "alert"  # Eyes closed + no mask > threshold


class EyeState(Enum):
    """Eye state detection result."""

    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"  # Face not detected or eyes obscured


class MaskState(Enum):
    """AVAPS mask detection result."""

    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"  # Cannot determine


class PersonIdentity(Enum):
    """Identity classification result."""

    DAD = "dad"
    UNKNOWN = "unknown"
    NO_FACE = "no_face"


@dataclass
class DetectionResult:
    """Result from a single detection pipeline run on one frame."""

    timestamp: datetime = field(default_factory=datetime.now)
    camera_id: str = ""

    # Face recognition
    face_detected: bool = False
    person: PersonIdentity = PersonIdentity.NO_FACE
    face_confidence: float = 0.0
    face_bbox: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)

    # Eye state
    eye_state: EyeState = EyeState.UNKNOWN
    ear_left: float = 0.0
    ear_right: float = 0.0
    ear_average: float = 0.0

    # Mask detection
    mask_state: MaskState = MaskState.UNKNOWN
    mask_confidence: float = 0.0

    # Processing metadata
    inference_time_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "camera_id": self.camera_id,
            "face_detected": self.face_detected,
            "person": self.person.value,
            "face_confidence": self.face_confidence,
            "face_bbox": self.face_bbox,
            "eye_state": self.eye_state.value,
            "ear_left": self.ear_left,
            "ear_right": self.ear_right,
            "ear_average": self.ear_average,
            "mask_state": self.mask_state.value,
            "mask_confidence": self.mask_confidence,
            "inference_time_ms": self.inference_time_ms,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DetectionResult":
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(),
            camera_id=data.get("camera_id", ""),
            face_detected=data.get("face_detected", False),
            person=PersonIdentity(data.get("person", "no_face")),
            face_confidence=data.get("face_confidence", 0.0),
            face_bbox=tuple(data["face_bbox"]) if data.get("face_bbox") else None,
            eye_state=EyeState(data.get("eye_state", "unknown")),
            ear_left=data.get("ear_left", 0.0),
            ear_right=data.get("ear_right", 0.0),
            ear_average=data.get("ear_average", 0.0),
            mask_state=MaskState(data.get("mask_state", "unknown")),
            mask_confidence=data.get("mask_confidence", 0.0),
            inference_time_ms=data.get("inference_time_ms", 0.0),
            error=data.get("error"),
        )


@dataclass
class Camera:
    """Camera configuration and runtime state."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""

    # Capture configuration - use either RTSP or HTTP snapshot
    capture_type: CaptureType = CaptureType.HTTP  # Default to HTTP (simpler)
    rtsp_url: str = ""  # RTSP stream URL (for capture_type=RTSP)
    snapshot_url: str = ""  # HTTP snapshot URL (for capture_type=HTTP, preferred)

    enabled: bool = True

    # State machine
    state: CameraState = CameraState.IDLE
    state_changed_at: datetime = field(default_factory=datetime.now)

    # Detection state
    last_poll_time: Optional[datetime] = None
    last_detection: Optional[DetectionResult] = None

    # Timing for alert logic
    dad_detected_at: Optional[datetime] = None
    eyes_closed_since: Optional[datetime] = None
    dad_gone_since: Optional[datetime] = None

    # Scheduling
    next_poll_time: Optional[datetime] = None

    def __post_init__(self):
        """Validate camera configuration."""
        if not self.id:
            self.id = str(uuid.uuid4())[:8]

    @property
    def eyes_closed_seconds(self) -> Optional[float]:
        """Calculate how long eyes have been closed."""
        if self.eyes_closed_since is None:
            return None
        return (datetime.now() - self.eyes_closed_since).total_seconds()

    @property
    def dad_gone_seconds(self) -> Optional[float]:
        """Calculate how long dad has been gone from frame."""
        if self.dad_gone_since is None:
            return None
        return (datetime.now() - self.dad_gone_since).total_seconds()

    @property
    def seconds_since_poll(self) -> Optional[float]:
        """Calculate seconds since last poll."""
        if self.last_poll_time is None:
            return None
        return (datetime.now() - self.last_poll_time).total_seconds()

    @property
    def active_url(self) -> str:
        """Get the active URL based on capture type."""
        if self.capture_type == CaptureType.HTTP:
            return self.snapshot_url
        return self.rtsp_url

    @staticmethod
    def _mask_url(url: str) -> str:
        """Mask password in URL for display."""
        if "://" not in url:
            return url
        # Mask password in scheme://user:password@host format
        try:
            prefix, rest = url.split("://", 1)
            if "@" in rest:
                auth, host = rest.rsplit("@", 1)
                if ":" in auth:
                    user, _ = auth.split(":", 1)
                    return f"{prefix}://{user}:****@{host}"
            return url
        except Exception:
            return url

    @property
    def rtsp_url_masked(self) -> str:
        """Return RTSP URL with password masked for display."""
        return self._mask_url(self.rtsp_url)

    @property
    def snapshot_url_masked(self) -> str:
        """Return snapshot URL with password masked for display."""
        return self._mask_url(self.snapshot_url)

    @property
    def active_url_masked(self) -> str:
        """Return the active URL (based on capture_type) with password masked."""
        return self._mask_url(self.active_url)

    def to_dict(self, include_urls: bool = False) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary.

        Args:
            include_urls: If True, include full URLs. If False, mask passwords.
        """
        return {
            "id": self.id,
            "name": self.name,
            "capture_type": self.capture_type.value,
            "rtsp_url": self.rtsp_url if include_urls else self.rtsp_url_masked,
            "snapshot_url": self.snapshot_url if include_urls else self.snapshot_url_masked,
            "enabled": self.enabled,
            "state": self.state.value,
            "state_changed_at": self.state_changed_at.isoformat() if self.state_changed_at else None,
            "last_poll_time": self.last_poll_time.isoformat() if self.last_poll_time else None,
            "eyes_closed_seconds": self.eyes_closed_seconds,
            "next_poll_time": self.next_poll_time.isoformat() if self.next_poll_time else None,
            "last_detection": self.last_detection.to_dict() if self.last_detection else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Camera":
        """Create from dictionary (for loading from JSON)."""
        # Determine capture type - default to HTTP if snapshot_url provided, RTSP otherwise
        capture_type = CaptureType.HTTP
        if "capture_type" in data:
            capture_type = CaptureType(data["capture_type"])
        elif data.get("snapshot_url"):
            capture_type = CaptureType.HTTP
        elif data.get("rtsp_url"):
            capture_type = CaptureType.RTSP

        camera = cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            capture_type=capture_type,
            rtsp_url=data.get("rtsp_url", ""),
            snapshot_url=data.get("snapshot_url", ""),
            enabled=data.get("enabled", True),
        )
        if "state" in data:
            camera.state = CameraState(data["state"])
        if data.get("state_changed_at"):
            camera.state_changed_at = datetime.fromisoformat(data["state_changed_at"])
        return camera

    def transition_to(self, new_state: CameraState) -> None:
        """Transition to a new state, updating timestamp."""
        if new_state != self.state:
            self.state = new_state
            self.state_changed_at = datetime.now()

    def update_detection(self, result: DetectionResult) -> None:
        """Update camera state based on detection result."""
        self.last_poll_time = datetime.now()
        self.last_detection = result

        # Track dad presence
        if result.person == PersonIdentity.DAD:
            self.dad_detected_at = datetime.now()
            self.dad_gone_since = None

            # Track eye state
            if result.eye_state == EyeState.CLOSED:
                if self.eyes_closed_since is None:
                    self.eyes_closed_since = datetime.now()
            else:
                self.eyes_closed_since = None
        else:
            # Dad not detected
            if self.dad_gone_since is None and self.dad_detected_at is not None:
                self.dad_gone_since = datetime.now()
            # Reset eye tracking when dad not visible
            self.eyes_closed_since = None


@dataclass
class CameraStatus:
    """Status of a single camera for API responses."""

    id: str
    name: str
    state: str
    enabled: bool
    last_poll_time: Optional[str]
    eyes_closed_seconds: Optional[float]
    last_detection: Optional[Dict[str, Any]]

    @classmethod
    def from_camera(cls, camera: Camera) -> "CameraStatus":
        """Create from Camera instance."""
        return cls(
            id=camera.id,
            name=camera.name,
            state=camera.state.value,
            enabled=camera.enabled,
            last_poll_time=camera.last_poll_time.isoformat() if camera.last_poll_time else None,
            eyes_closed_seconds=camera.eyes_closed_seconds,
            last_detection=camera.last_detection.to_dict() if camera.last_detection else None,
        )


@dataclass
class VisionStatus:
    """Overall vision service status for Pi polling (GET /status)."""

    timestamp: datetime = field(default_factory=datetime.now)

    # Alert state
    alert_active: bool = False
    alert_reason: Optional[str] = None
    alert_camera_id: Optional[str] = None
    alert_camera_name: Optional[str] = None
    eyes_closed_seconds: Optional[float] = None

    # Camera summaries
    cameras: List[Dict[str, Any]] = field(default_factory=list)

    # System health
    models_loaded: bool = False
    gpu_available: bool = False
    gpu_memory_used_mb: Optional[float] = None
    uptime_seconds: float = 0.0
    enrolled_faces: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "alert_active": self.alert_active,
            "alert_reason": self.alert_reason,
            "alert_camera_id": self.alert_camera_id,
            "alert_camera_name": self.alert_camera_name,
            "eyes_closed_seconds": self.eyes_closed_seconds,
            "cameras": self.cameras,
            "system": {
                "models_loaded": self.models_loaded,
                "gpu_available": self.gpu_available,
                "gpu_memory_used_mb": self.gpu_memory_used_mb,
                "uptime_seconds": self.uptime_seconds,
                "enrolled_faces": self.enrolled_faces,
            },
        }
