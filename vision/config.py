# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Configuration management for vision service.

Uses Pydantic Settings for environment variable and .env file support.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DetectionSettings(BaseSettings):
    """Detection threshold settings."""

    model_config = SettingsConfigDict(env_prefix="VISION_DETECTION_")

    # Face recognition
    face_similarity_threshold: float = Field(
        default=0.6,
        description="Cosine similarity threshold for face matching (0-1)"
    )

    # Eye state detection (Eye Aspect Ratio)
    ear_closed_threshold: float = Field(
        default=0.2,
        description="EAR below this = eyes closed"
    )
    ear_open_threshold: float = Field(
        default=0.25,
        description="EAR above this = eyes open (hysteresis)"
    )

    # Alert timing
    eyes_closed_alert_seconds: float = Field(
        default=300.0,
        description="Seconds of closed eyes before alert (5 min)"
    )
    dad_gone_timeout_seconds: float = Field(
        default=600.0,
        description="Seconds without dad detected before returning to IDLE (10 min)"
    )


class CameraSettings(BaseSettings):
    """Camera polling settings."""

    model_config = SettingsConfigDict(env_prefix="VISION_CAMERA_")

    idle_poll_seconds: float = Field(
        default=300.0,
        description="Polling interval in IDLE state (5 min)"
    )
    active_poll_seconds: float = Field(
        default=60.0,
        description="Polling interval in ACTIVE state (1 min)"
    )
    alert_poll_seconds: float = Field(
        default=60.0,
        description="Polling interval in ALERT state (1 min)"
    )
    stagger_offset_factor: float = Field(
        default=1.0,
        description="Multiplier for stagger offset calculation"
    )
    max_cameras: int = Field(
        default=5,
        description="Maximum number of cameras supported"
    )
    rtsp_timeout_seconds: float = Field(
        default=10.0,
        description="Timeout for RTSP connection"
    )


class GPUSettings(BaseSettings):
    """GPU/CUDA settings."""

    model_config = SettingsConfigDict(env_prefix="VISION_GPU_")

    device_id: int = Field(
        default=0,
        description="CUDA device ID to use"
    )
    memory_fraction: float = Field(
        default=0.8,
        description="Fraction of GPU memory to allow (0-1)"
    )


class ServerSettings(BaseSettings):
    """FastAPI server settings."""

    model_config = SettingsConfigDict(env_prefix="VISION_SERVER_")

    host: str = Field(
        default="0.0.0.0",
        description="Host to bind to"
    )
    port: int = Field(
        default=8100,
        description="Port to listen on"
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )


class Settings(BaseSettings):
    """Root settings for vision service.

    Settings are loaded from environment variables with VISION_ prefix,
    or from a .env file in the vision directory.

    Example environment variables:
        VISION_SERVER_PORT=8100
        VISION_DETECTION_EYES_CLOSED_ALERT_SECONDS=300
        VISION_GPU_DEVICE_ID=0
    """

    model_config = SettingsConfigDict(
        env_prefix="VISION_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Nested settings
    detection: DetectionSettings = Field(default_factory=DetectionSettings)
    camera: CameraSettings = Field(default_factory=CameraSettings)
    gpu: GPUSettings = Field(default_factory=GPUSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)

    # Paths
    data_dir: Path = Field(
        default=Path(__file__).parent / "data",
        description="Directory for runtime data (embeddings, configs)"
    )

    @property
    def cameras_file(self) -> Path:
        """Path to cameras configuration JSON file."""
        return self.data_dir / "cameras.json"

    @property
    def embeddings_dir(self) -> Path:
        """Directory for face embeddings."""
        return self.data_dir / "embeddings"

    @property
    def snapshots_dir(self) -> Path:
        """Directory for debug snapshots."""
        return self.data_dir / "snapshots"

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.embeddings_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance (lazy loaded)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings


def configure_gpu() -> None:
    """Configure GPU settings before importing torch/CUDA libraries.

    IMPORTANT: Call this before importing torch, insightface, etc.
    """
    settings = get_settings()
    os.environ["CUDA_VISIBLE_DEVICES"] = str(settings.gpu.device_id)
