# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""RTSP stream capture for Reolink cameras.

Captures single frames from RTSP streams on demand rather than
continuous streaming to minimize resource usage.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CaptureResult:
    """Result of a frame capture operation."""

    success: bool = False
    frame: Optional[np.ndarray] = None
    width: int = 0
    height: int = 0
    capture_time_ms: float = 0.0
    error: Optional[str] = None


class RTSPCapture:
    """Captures frames from RTSP streams.

    Designed for on-demand single frame capture rather than continuous
    streaming. Each capture opens a fresh connection to ensure we get
    the latest frame (not a buffered old frame).

    Reolink RTSP URL formats:
        Main stream (high res): rtsp://user:pass@ip:554/h264Preview_01_main
        Sub stream (low res):   rtsp://user:pass@ip:554/h264Preview_01_sub

    Usage:
        capture = RTSPCapture(rtsp_url)
        result = capture.grab_frame()
        if result.success:
            process(result.frame)
    """

    def __init__(
        self,
        rtsp_url: str,
        timeout_seconds: float = 10.0,
        use_tcp: bool = True,
    ):
        """Initialize RTSP capture.

        Args:
            rtsp_url: Full RTSP URL with credentials
            timeout_seconds: Timeout for connection and frame grab
            use_tcp: Use TCP transport (more reliable than UDP)
        """
        self.rtsp_url = rtsp_url
        self.timeout_seconds = timeout_seconds
        self.use_tcp = use_tcp

        # Validate URL format
        parsed = urlparse(rtsp_url)
        if parsed.scheme.lower() != "rtsp":
            logger.warning(f"URL scheme is '{parsed.scheme}', expected 'rtsp'")

        self._lock = threading.Lock()

    @property
    def rtsp_url_masked(self) -> str:
        """Return URL with password masked for logging."""
        try:
            parsed = urlparse(self.rtsp_url)
            if parsed.password:
                masked = self.rtsp_url.replace(f":{parsed.password}@", ":****@")
                return masked
            return self.rtsp_url
        except Exception:
            return self.rtsp_url

    def _create_capture(self) -> cv2.VideoCapture:
        """Create a new VideoCapture with optimized settings."""
        # Set environment for RTSP over TCP
        cap = cv2.VideoCapture()

        # Set options before opening
        if self.use_tcp:
            # Force TCP transport (more reliable for single frame grabs)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"H264"))

        # Set timeout (in milliseconds)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(self.timeout_seconds * 1000))
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(self.timeout_seconds * 1000))

        # Reduce buffer size to get fresher frames
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Open the stream
        # For RTSP over TCP, append transport option to URL
        url = self.rtsp_url
        if self.use_tcp and "rtsp_transport" not in url:
            # FFmpeg/GStreamer style TCP transport
            if "?" in url:
                url += "&rtsp_transport=tcp"
            else:
                url += "?rtsp_transport=tcp"

        cap.open(url, cv2.CAP_FFMPEG)

        return cap

    def grab_frame(self) -> CaptureResult:
        """Grab a single frame from the RTSP stream.

        Opens a fresh connection, grabs one frame, and closes.
        This ensures we get the latest frame, not a buffered one.

        Returns:
            CaptureResult with frame data or error
        """
        start_time = time.time()

        with self._lock:
            cap = None
            try:
                logger.debug(f"Connecting to {self.rtsp_url_masked}")
                cap = self._create_capture()

                if not cap.isOpened():
                    elapsed = (time.time() - start_time) * 1000
                    return CaptureResult(
                        success=False,
                        capture_time_ms=elapsed,
                        error="Failed to open RTSP stream",
                    )

                # Read a frame
                ret, frame = cap.read()

                if not ret or frame is None:
                    elapsed = (time.time() - start_time) * 1000
                    return CaptureResult(
                        success=False,
                        capture_time_ms=elapsed,
                        error="Failed to read frame from stream",
                    )

                elapsed = (time.time() - start_time) * 1000
                height, width = frame.shape[:2]

                logger.debug(f"Captured frame {width}x{height} in {elapsed:.0f}ms")

                return CaptureResult(
                    success=True,
                    frame=frame,
                    width=width,
                    height=height,
                    capture_time_ms=elapsed,
                )

            except cv2.error as e:
                elapsed = (time.time() - start_time) * 1000
                logger.error(f"OpenCV error capturing frame: {e}")
                return CaptureResult(
                    success=False,
                    capture_time_ms=elapsed,
                    error=f"OpenCV error: {e}",
                )

            except Exception as e:
                elapsed = (time.time() - start_time) * 1000
                logger.error(f"Error capturing frame: {e}")
                return CaptureResult(
                    success=False,
                    capture_time_ms=elapsed,
                    error=str(e),
                )

            finally:
                if cap is not None:
                    cap.release()

    def grab_frame_with_retry(
        self,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> CaptureResult:
        """Grab a frame with automatic retry on failure.

        Args:
            max_retries: Maximum number of retry attempts
            retry_delay_seconds: Delay between retries

        Returns:
            CaptureResult from successful attempt or last failure
        """
        last_result = None

        for attempt in range(max_retries + 1):
            result = self.grab_frame()

            if result.success:
                if attempt > 0:
                    logger.info(f"Frame capture succeeded on attempt {attempt + 1}")
                return result

            last_result = result

            if attempt < max_retries:
                logger.warning(
                    f"Frame capture failed (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{result.error}. Retrying in {retry_delay_seconds}s..."
                )
                time.sleep(retry_delay_seconds)

        logger.error(f"Frame capture failed after {max_retries + 1} attempts")
        return last_result

    def test_connection(self) -> Tuple[bool, str]:
        """Test if the RTSP stream is accessible.

        Returns:
            Tuple of (success, message)
        """
        result = self.grab_frame()

        if result.success:
            return True, f"Connected successfully ({result.width}x{result.height})"
        else:
            return False, result.error or "Unknown error"

    def get_stream_info(self) -> dict:
        """Get information about the stream.

        Returns:
            Dictionary with stream properties
        """
        with self._lock:
            cap = None
            try:
                cap = self._create_capture()

                if not cap.isOpened():
                    return {"error": "Failed to open stream"}

                info = {
                    "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    "fps": cap.get(cv2.CAP_PROP_FPS),
                    "codec": int(cap.get(cv2.CAP_PROP_FOURCC)),
                    "backend": cap.getBackendName(),
                }

                return info

            except Exception as e:
                return {"error": str(e)}

            finally:
                if cap is not None:
                    cap.release()


def frame_to_jpeg(
    frame: np.ndarray,
    quality: int = 85,
) -> Optional[bytes]:
    """Convert a frame to JPEG bytes.

    Args:
        frame: BGR image (OpenCV format)
        quality: JPEG quality (0-100)

    Returns:
        JPEG bytes or None on error
    """
    try:
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        success, encoded = cv2.imencode(".jpg", frame, encode_params)

        if success:
            return encoded.tobytes()
        return None

    except Exception as e:
        logger.error(f"Error encoding frame to JPEG: {e}")
        return None


def resize_frame(
    frame: np.ndarray,
    max_width: int = 1280,
    max_height: int = 720,
) -> np.ndarray:
    """Resize frame while maintaining aspect ratio.

    Args:
        frame: BGR image
        max_width: Maximum width
        max_height: Maximum height

    Returns:
        Resized frame
    """
    height, width = frame.shape[:2]

    # Check if resize needed
    if width <= max_width and height <= max_height:
        return frame

    # Calculate scale factor
    scale_w = max_width / width
    scale_h = max_height / height
    scale = min(scale_w, scale_h)

    new_width = int(width * scale)
    new_height = int(height * scale)

    return cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
