# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Camera capture and management modules."""

from vision.capture.http_snapshot import HTTPCapture
from vision.capture.rtsp_stream import RTSPCapture

__all__ = ["HTTPCapture", "RTSPCapture"]
