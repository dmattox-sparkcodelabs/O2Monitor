# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""HTTP snapshot capture for IP cameras.

Captures single frames via HTTP snapshot endpoints. This is simpler and
more reliable than RTSP for cameras that support it (like Amcrest).

Amcrest snapshot URL: http://admin:password@IP/cgi-bin/snapshot.cgi
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse

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


class HTTPCapture:
    """Captures frames via HTTP snapshot endpoint.

    Designed for cameras with HTTP snapshot support like Amcrest.
    Much simpler than RTSP - just fetches a JPEG and decodes it.

    Amcrest URL formats:
        Snapshot: http://user:pass@ip/cgi-bin/snapshot.cgi
        Snapshot with channel: http://user:pass@ip/cgi-bin/snapshot.cgi?channel=1

    Usage:
        capture = HTTPCapture(snapshot_url)
        result = capture.grab_frame()
        if result.success:
            process(result.frame)
    """

    def __init__(
        self,
        snapshot_url: str,
        timeout_seconds: float = 10.0,
    ):
        """Initialize HTTP capture.

        Args:
            snapshot_url: Full URL with credentials (e.g., http://admin:pass@ip/cgi-bin/snapshot.cgi)
            timeout_seconds: Timeout for HTTP request
        """
        self.snapshot_url = snapshot_url
        self.timeout_seconds = timeout_seconds

        # Validate URL format
        parsed = urlparse(snapshot_url)
        if parsed.scheme.lower() not in ("http", "https"):
            logger.warning(f"URL scheme is '{parsed.scheme}', expected 'http' or 'https'")

    @property
    def snapshot_url_masked(self) -> str:
        """Return URL with password masked for logging."""
        try:
            parsed = urlparse(self.snapshot_url)
            if parsed.password:
                masked = self.snapshot_url.replace(f":{parsed.password}@", ":****@")
                return masked
            return self.snapshot_url
        except Exception:
            return self.snapshot_url

    def grab_frame(self) -> CaptureResult:
        """Grab a single frame via HTTP snapshot.

        Returns:
            CaptureResult with frame data or error
        """
        import cv2
        import urllib.request
        import urllib.error

        start_time = time.time()

        try:
            logger.debug(f"Fetching snapshot from {self.snapshot_url_masked}")

            # Create request with timeout
            request = urllib.request.Request(self.snapshot_url)

            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                # Read image data
                image_data = response.read()

                if not image_data:
                    elapsed = (time.time() - start_time) * 1000
                    return CaptureResult(
                        success=False,
                        capture_time_ms=elapsed,
                        error="Empty response from camera",
                    )

                # Decode JPEG to numpy array
                nparr = np.frombuffer(image_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is None:
                    elapsed = (time.time() - start_time) * 1000
                    return CaptureResult(
                        success=False,
                        capture_time_ms=elapsed,
                        error="Failed to decode image data",
                    )

                elapsed = (time.time() - start_time) * 1000
                height, width = frame.shape[:2]

                logger.debug(f"Captured snapshot {width}x{height} in {elapsed:.0f}ms")

                return CaptureResult(
                    success=True,
                    frame=frame,
                    width=width,
                    height=height,
                    capture_time_ms=elapsed,
                )

        except urllib.error.HTTPError as e:
            elapsed = (time.time() - start_time) * 1000
            error_msg = f"HTTP {e.code}: {e.reason}"
            logger.error(f"HTTP error fetching snapshot: {error_msg}")
            return CaptureResult(
                success=False,
                capture_time_ms=elapsed,
                error=error_msg,
            )

        except urllib.error.URLError as e:
            elapsed = (time.time() - start_time) * 1000
            error_msg = f"URL error: {e.reason}"
            logger.error(f"URL error fetching snapshot: {error_msg}")
            return CaptureResult(
                success=False,
                capture_time_ms=elapsed,
                error=error_msg,
            )

        except TimeoutError:
            elapsed = (time.time() - start_time) * 1000
            logger.error("Timeout fetching snapshot")
            return CaptureResult(
                success=False,
                capture_time_ms=elapsed,
                error="Connection timeout",
            )

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error fetching snapshot: {e}")
            return CaptureResult(
                success=False,
                capture_time_ms=elapsed,
                error=str(e),
            )

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
                    logger.info(f"Snapshot capture succeeded on attempt {attempt + 1}")
                return result

            last_result = result

            if attempt < max_retries:
                logger.warning(
                    f"Snapshot capture failed (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{result.error}. Retrying in {retry_delay_seconds}s..."
                )
                time.sleep(retry_delay_seconds)

        logger.error(f"Snapshot capture failed after {max_retries + 1} attempts")
        return last_result

    def test_connection(self) -> Tuple[bool, str]:
        """Test if the snapshot endpoint is accessible.

        Returns:
            Tuple of (success, message)
        """
        result = self.grab_frame()

        if result.success:
            return True, f"Connected successfully ({result.width}x{result.height})"
        else:
            return False, result.error or "Unknown error"


def build_amcrest_snapshot_url(
    ip: str,
    username: str = "admin",
    password: str = "",
    port: int = 80,
    channel: int = 1,
) -> str:
    """Build Amcrest snapshot URL from components.

    Args:
        ip: Camera IP address
        username: Camera username (default: admin)
        password: Camera password
        port: HTTP port (default: 80)
        channel: Camera channel (default: 1)

    Returns:
        Full snapshot URL
    """
    if port == 80:
        return f"http://{username}:{password}@{ip}/cgi-bin/snapshot.cgi?channel={channel}"
    else:
        return f"http://{username}:{password}@{ip}:{port}/cgi-bin/snapshot.cgi?channel={channel}"


def build_amcrest_rtsp_url(
    ip: str,
    username: str = "admin",
    password: str = "",
    port: int = 554,
    channel: int = 1,
    subtype: int = 1,  # 0=main, 1=sub
) -> str:
    """Build Amcrest RTSP URL from components.

    Args:
        ip: Camera IP address
        username: Camera username (default: admin)
        password: Camera password
        port: RTSP port (default: 554)
        channel: Camera channel (default: 1)
        subtype: Stream type - 0=main (high res), 1=sub (low res)

    Returns:
        Full RTSP URL
    """
    return f"rtsp://{username}:{password}@{ip}:{port}/cam/realmonitor?channel={channel}&subtype={subtype}"
