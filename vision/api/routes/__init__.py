# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""API route handlers for vision service."""

from vision.api.routes import cameras, config_routes, enrollment, health, status

__all__ = ["health", "status", "cameras", "enrollment", "config_routes"]
