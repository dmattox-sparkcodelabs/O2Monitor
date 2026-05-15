# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Camera manager with state machine and scheduler.

Manages multiple cameras, their polling schedules, and state transitions.
Coordinates with the detection pipeline to process frames.
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from vision.capture.http_snapshot import HTTPCapture
from vision.capture.rtsp_stream import RTSPCapture
from vision.config import Settings, get_settings
from vision.detection.pipeline import DetectionPipeline, get_pipeline
from vision.models.camera import (
    Camera,
    CameraState,
    CaptureType,
    DetectionResult,
    EyeState,
    MaskState,
    PersonIdentity,
    VisionStatus,
)

logger = logging.getLogger(__name__)


class CameraManager:
    """Manages cameras, scheduling, and state transitions.

    State Machine:
        IDLE   - Dad not detected, poll every idle_poll_seconds (5 min)
        ACTIVE - Dad detected, poll every active_poll_seconds (1 min)
        ALERT  - Eyes closed + no mask, poll every alert_poll_seconds (1 min)

    Transitions:
        IDLE → ACTIVE: Dad detected in frame
        ACTIVE → IDLE: Dad gone for dad_gone_timeout_seconds (10 min)
        ACTIVE → ALERT: Eyes closed + no mask for eyes_closed_alert_seconds (5 min)
        ALERT → ACTIVE: Eyes open or mask detected

    Staggered Scheduling:
        Cameras are polled at offset intervals to avoid GPU contention.
        For 3 cameras with 5-min idle polling:
        - Camera 1: 0:00, 5:00, 10:00...
        - Camera 2: 1:40, 6:40, 11:40...
        - Camera 3: 3:20, 8:20, 13:20...
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        pipeline: Optional[DetectionPipeline] = None,
        cameras_file: Optional[Path] = None,
    ):
        """Initialize camera manager.

        Args:
            settings: Vision settings (uses global if not provided)
            pipeline: Detection pipeline (uses global if not provided)
            cameras_file: Path to cameras.json (uses settings if not provided)
        """
        self.settings = settings or get_settings()
        self._pipeline = pipeline

        # Camera storage
        self._cameras: Dict[str, Camera] = {}
        self._captures: Dict[str, Union[RTSPCapture, HTTPCapture]] = {}
        self._lock = threading.RLock()

        # Persistence
        self._cameras_file = cameras_file or (self.settings.data_dir / "cameras.json")

        # Scheduling
        self._scheduler_thread: Optional[threading.Thread] = None
        self._scheduler_running = False
        self._poll_callbacks: List[Callable[[str, DetectionResult], None]] = []

        # Alert state
        self._alert_active = False
        self._alert_camera_id: Optional[str] = None
        self._alert_reason: Optional[str] = None

        # Service start time for uptime tracking
        self._start_time = datetime.now()

    @property
    def pipeline(self) -> DetectionPipeline:
        """Get the detection pipeline (lazy load)."""
        if self._pipeline is None:
            self._pipeline = get_pipeline()
        return self._pipeline

    def _create_capture(self, camera: Camera) -> Union[RTSPCapture, HTTPCapture]:
        """Create the appropriate capture instance based on camera config.

        Args:
            camera: Camera configuration

        Returns:
            RTSPCapture or HTTPCapture instance
        """
        if camera.capture_type == CaptureType.HTTP:
            return HTTPCapture(
                camera.snapshot_url,
                timeout_seconds=self.settings.camera.rtsp_timeout_seconds,
            )
        else:
            return RTSPCapture(
                camera.rtsp_url,
                timeout_seconds=self.settings.camera.rtsp_timeout_seconds,
            )

    def load_cameras(self) -> int:
        """Load cameras from JSON file.

        Returns:
            Number of cameras loaded
        """
        with self._lock:
            if not self._cameras_file.exists():
                logger.info(f"No cameras file at {self._cameras_file}")
                return 0

            try:
                with open(self._cameras_file) as f:
                    data = json.load(f)

                for cam_data in data.get("cameras", []):
                    camera = Camera.from_dict(cam_data)
                    self._cameras[camera.id] = camera
                    # Create capture instance based on capture type
                    self._captures[camera.id] = self._create_capture(camera)
                    logger.info(
                        f"Loaded camera: {camera.name} ({camera.id}) "
                        f"[{camera.capture_type.value}]"
                    )

                logger.info(f"Loaded {len(self._cameras)} cameras")
                return len(self._cameras)

            except Exception as e:
                logger.error(f"Failed to load cameras: {e}")
                return 0

    def save_cameras(self) -> bool:
        """Save cameras to JSON file.

        Returns:
            True if save succeeded
        """
        with self._lock:
            try:
                self._cameras_file.parent.mkdir(parents=True, exist_ok=True)

                data = {
                    "cameras": [
                        cam.to_dict(include_urls=True)
                        for cam in self._cameras.values()
                    ]
                }

                with open(self._cameras_file, "w") as f:
                    json.dump(data, f, indent=2)

                logger.debug(f"Saved {len(self._cameras)} cameras")
                return True

            except Exception as e:
                logger.error(f"Failed to save cameras: {e}")
                return False

    def add_camera(
        self,
        name: str,
        snapshot_url: str = "",
        rtsp_url: str = "",
        capture_type: CaptureType = CaptureType.HTTP,
        camera_id: Optional[str] = None,
        enabled: bool = True,
    ) -> Camera:
        """Add a new camera.

        Args:
            name: Camera display name
            snapshot_url: HTTP snapshot URL (for HTTP capture type)
            rtsp_url: RTSP URL with credentials (for RTSP capture type)
            capture_type: Type of capture (HTTP or RTSP)
            camera_id: Optional specific ID
            enabled: Whether camera is enabled

        Returns:
            Created Camera object
        """
        with self._lock:
            camera = Camera(
                name=name,
                capture_type=capture_type,
                snapshot_url=snapshot_url,
                rtsp_url=rtsp_url,
                enabled=enabled,
            )
            if camera_id:
                camera.id = camera_id

            self._cameras[camera.id] = camera
            self._captures[camera.id] = self._create_capture(camera)

            # Calculate staggered start time
            self._schedule_camera(camera)

            self.save_cameras()
            logger.info(
                f"Added camera: {name} ({camera.id}) [{capture_type.value}]"
            )
            return camera

    def remove_camera(self, camera_id: str) -> bool:
        """Remove a camera.

        Args:
            camera_id: ID of camera to remove

        Returns:
            True if camera was removed
        """
        with self._lock:
            if camera_id not in self._cameras:
                return False

            del self._cameras[camera_id]
            if camera_id in self._captures:
                del self._captures[camera_id]

            if self._alert_camera_id == camera_id:
                self._clear_alert()

            self.save_cameras()
            logger.info(f"Removed camera: {camera_id}")
            return True

    def get_camera(self, camera_id: str) -> Optional[Camera]:
        """Get a camera by ID."""
        return self._cameras.get(camera_id)

    def get_cameras(self) -> List[Camera]:
        """Get all cameras."""
        return list(self._cameras.values())

    def update_camera(
        self,
        camera_id: str,
        name: Optional[str] = None,
        snapshot_url: Optional[str] = None,
        rtsp_url: Optional[str] = None,
        capture_type: Optional[CaptureType] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[Camera]:
        """Update camera properties.

        Args:
            camera_id: ID of camera to update
            name: New name (if provided)
            snapshot_url: New HTTP snapshot URL (if provided)
            rtsp_url: New RTSP URL (if provided)
            capture_type: New capture type (if provided)
            enabled: New enabled state (if provided)

        Returns:
            Updated Camera or None if not found
        """
        with self._lock:
            camera = self._cameras.get(camera_id)
            if not camera:
                return None

            url_changed = False

            if name is not None:
                camera.name = name
            if capture_type is not None:
                camera.capture_type = capture_type
                url_changed = True
            if snapshot_url is not None:
                camera.snapshot_url = snapshot_url
                url_changed = True
            if rtsp_url is not None:
                camera.rtsp_url = rtsp_url
                url_changed = True
            if enabled is not None:
                camera.enabled = enabled

            # Recreate capture if URLs or type changed
            if url_changed:
                self._captures[camera_id] = self._create_capture(camera)

            self.save_cameras()
            return camera

    def enable_camera(self, camera_id: str) -> bool:
        """Enable a camera."""
        camera = self.update_camera(camera_id, enabled=True)
        return camera is not None

    def disable_camera(self, camera_id: str) -> bool:
        """Disable a camera."""
        camera = self.update_camera(camera_id, enabled=False)
        if camera and self._alert_camera_id == camera_id:
            self._clear_alert()
        return camera is not None

    def _schedule_camera(self, camera: Camera) -> None:
        """Calculate next poll time for a camera based on its state and position."""
        # Get interval based on state
        if camera.state == CameraState.IDLE:
            interval = self.settings.camera.idle_poll_seconds
        elif camera.state == CameraState.ACTIVE:
            interval = self.settings.camera.active_poll_seconds
        else:  # ALERT
            interval = self.settings.camera.alert_poll_seconds

        # Calculate staggered offset based on camera position
        camera_ids = sorted(self._cameras.keys())
        if camera.id in camera_ids:
            position = camera_ids.index(camera.id)
            total_cameras = len(camera_ids)
            if total_cameras > 1:
                offset = (interval / total_cameras) * position
            else:
                offset = 0
        else:
            offset = 0

        # Set next poll time
        if camera.last_poll_time:
            base_time = camera.last_poll_time + timedelta(seconds=interval)
        else:
            base_time = datetime.now() + timedelta(seconds=offset)

        camera.next_poll_time = base_time

    def _process_detection(self, camera: Camera, result: DetectionResult) -> None:
        """Process detection result and update camera state.

        Args:
            camera: Camera that was polled
            result: Detection result from pipeline
        """
        # Update camera with detection result
        camera.update_detection(result)

        # State transition logic
        old_state = camera.state

        if result.person == PersonIdentity.DAD:
            # Dad detected
            if camera.state == CameraState.IDLE:
                camera.transition_to(CameraState.ACTIVE)
                logger.info(f"Camera {camera.name}: IDLE → ACTIVE (dad detected)")

            # Check for alert condition
            if (
                result.eye_state == EyeState.CLOSED
                and result.mask_state == MaskState.ABSENT
            ):
                eyes_closed_secs = camera.eyes_closed_seconds or 0
                threshold = self.settings.detection.eyes_closed_alert_seconds

                if eyes_closed_secs >= threshold:
                    if camera.state != CameraState.ALERT:
                        camera.transition_to(CameraState.ALERT)
                        self._set_alert(
                            camera.id,
                            f"Eyes closed without mask for {int(eyes_closed_secs)}s",
                        )
                        logger.warning(
                            f"Camera {camera.name}: → ALERT "
                            f"(eyes closed {eyes_closed_secs:.0f}s, no mask)"
                        )
            else:
                # Eyes open or mask present - clear alert
                if camera.state == CameraState.ALERT:
                    camera.transition_to(CameraState.ACTIVE)
                    if self._alert_camera_id == camera.id:
                        self._clear_alert()
                    logger.info(
                        f"Camera {camera.name}: ALERT → ACTIVE "
                        f"(eyes={result.eye_state.value}, mask={result.mask_state.value})"
                    )

        else:
            # Dad not detected
            if camera.state in (CameraState.ACTIVE, CameraState.ALERT):
                dad_gone_secs = camera.dad_gone_seconds or 0
                timeout = self.settings.detection.dad_gone_timeout_seconds

                if dad_gone_secs >= timeout:
                    camera.transition_to(CameraState.IDLE)
                    if self._alert_camera_id == camera.id:
                        self._clear_alert()
                    logger.info(
                        f"Camera {camera.name}: → IDLE (dad gone {dad_gone_secs:.0f}s)"
                    )

        # Reschedule based on new state
        if camera.state != old_state:
            self._schedule_camera(camera)

        # Notify callbacks
        for callback in self._poll_callbacks:
            try:
                callback(camera.id, result)
            except Exception as e:
                logger.error(f"Poll callback error: {e}")

    def _set_alert(self, camera_id: str, reason: str) -> None:
        """Set alert state."""
        self._alert_active = True
        self._alert_camera_id = camera_id
        self._alert_reason = reason

    def _clear_alert(self) -> None:
        """Clear alert state."""
        self._alert_active = False
        self._alert_camera_id = None
        self._alert_reason = None

    def poll_camera(self, camera_id: str) -> Optional[DetectionResult]:
        """Manually poll a specific camera.

        Args:
            camera_id: ID of camera to poll

        Returns:
            DetectionResult or None if camera not found
        """
        with self._lock:
            camera = self._cameras.get(camera_id)
            capture = self._captures.get(camera_id)

            if not camera or not capture:
                return None

            if not camera.enabled:
                logger.debug(f"Skipping disabled camera: {camera.name}")
                return None

        # Capture frame (outside lock to avoid blocking)
        result = capture.grab_frame_with_retry(
            max_retries=self.settings.camera.max_retries,
            retry_delay_seconds=1.0,
        )

        if not result.success:
            logger.warning(f"Failed to capture from {camera.name}: {result.error}")
            detection = DetectionResult(
                camera_id=camera_id,
                error=result.error,
            )
            with self._lock:
                camera.last_poll_time = datetime.now()
                self._schedule_camera(camera)
            return detection

        # Run detection pipeline
        detection = self.pipeline.process_frame(
            result.frame,
            camera_id=camera_id,
        )

        # Process result and update state
        with self._lock:
            self._process_detection(camera, detection)
            self._schedule_camera(camera)

        return detection

    def capture_snapshot(self, camera_id: str) -> Optional[bytes]:
        """Capture a JPEG snapshot from a camera.

        Args:
            camera_id: ID of camera

        Returns:
            JPEG bytes or None if failed
        """
        from vision.capture.rtsp_stream import frame_to_jpeg

        capture = self._captures.get(camera_id)
        if not capture:
            return None

        result = capture.grab_frame()
        if not result.success:
            return None

        return frame_to_jpeg(result.frame)

    def add_poll_callback(
        self,
        callback: Callable[[str, DetectionResult], None],
    ) -> None:
        """Add a callback to be called after each poll.

        Args:
            callback: Function(camera_id, result) to call
        """
        self._poll_callbacks.append(callback)

    def start_scheduler(self) -> None:
        """Start the background scheduler thread."""
        if self._scheduler_running:
            return

        self._scheduler_running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="CameraScheduler",
        )
        self._scheduler_thread.start()
        logger.info("Camera scheduler started")

    def stop_scheduler(self) -> None:
        """Stop the background scheduler thread."""
        self._scheduler_running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5.0)
            self._scheduler_thread = None
        logger.info("Camera scheduler stopped")

    def _scheduler_loop(self) -> None:
        """Main scheduler loop - polls cameras when their time comes."""
        while self._scheduler_running:
            try:
                now = datetime.now()

                # Find cameras that need polling
                cameras_to_poll = []
                with self._lock:
                    for camera in self._cameras.values():
                        if not camera.enabled:
                            continue
                        if camera.next_poll_time and now >= camera.next_poll_time:
                            cameras_to_poll.append(camera.id)
                        elif camera.next_poll_time is None:
                            # Never scheduled - schedule now
                            self._schedule_camera(camera)

                # Poll due cameras (one at a time to manage GPU)
                for camera_id in cameras_to_poll:
                    if not self._scheduler_running:
                        break
                    logger.debug(f"Scheduler polling camera: {camera_id}")
                    self.poll_camera(camera_id)

                # Sleep briefly before checking again
                time.sleep(1.0)

            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(5.0)

    def get_status(self) -> VisionStatus:
        """Get current vision service status for Pi polling.

        Returns:
            VisionStatus with alert state and camera summaries
        """
        with self._lock:
            alert_camera = None
            if self._alert_camera_id:
                alert_camera = self._cameras.get(self._alert_camera_id)

            eyes_closed_seconds = None
            if alert_camera:
                eyes_closed_seconds = alert_camera.eyes_closed_seconds

            cameras_data = [
                cam.to_dict(include_urls=False) for cam in self._cameras.values()
            ]

            uptime = (datetime.now() - self._start_time).total_seconds()

            return VisionStatus(
                alert_active=self._alert_active,
                alert_reason=self._alert_reason,
                alert_camera_id=self._alert_camera_id,
                alert_camera_name=alert_camera.name if alert_camera else None,
                eyes_closed_seconds=eyes_closed_seconds,
                cameras=cameras_data,
                models_loaded=self.pipeline.is_models_loaded,
                gpu_available=self._check_gpu_available(),
                gpu_memory_used_mb=self._get_gpu_memory_usage(),
                uptime_seconds=uptime,
                enrolled_faces=self.pipeline.enrolled_faces_count,
            )

    def _check_gpu_available(self) -> bool:
        """Check if CUDA GPU is available."""
        try:
            import torch

            return torch.cuda.is_available()
        except ImportError:
            return False

    def _get_gpu_memory_usage(self) -> Optional[float]:
        """Get GPU memory usage in MB."""
        try:
            import torch

            if torch.cuda.is_available():
                return torch.cuda.memory_allocated() / (1024 * 1024)
            return None
        except ImportError:
            return None


# Global manager instance (lazy loaded)
_manager: Optional[CameraManager] = None


def get_camera_manager() -> CameraManager:
    """Get or create the global camera manager instance."""
    global _manager
    if _manager is None:
        _manager = CameraManager()
    return _manager
