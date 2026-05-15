# =============================================================================
# DISCLAIMER: This software is NOT a medical device and is NOT intended for
# medical monitoring, diagnosis, or treatment. This is a proof of concept for
# educational purposes only. Do not rely on this system for health decisions.
# =============================================================================
"""Vision service client for Pi integration.

Polls the vision service running on Windows PC to check for sleep
monitoring alerts (eyes closed without mask).
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class VisionAlert:
    """Alert data from vision service."""

    active: bool = False
    reason: Optional[str] = None
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    eyes_closed_seconds: Optional[float] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class VisionStatus:
    """Status from vision service."""

    connected: bool = False
    alert: Optional[VisionAlert] = None
    models_loaded: bool = False
    gpu_available: bool = False
    uptime_seconds: float = 0.0
    enrolled_faces: int = 0
    camera_count: int = 0
    last_check_time: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "connected": self.connected,
            "alert_active": self.alert.active if self.alert else False,
            "alert_reason": self.alert.reason if self.alert else None,
            "alert_camera_name": self.alert.camera_name if self.alert else None,
            "eyes_closed_seconds": self.alert.eyes_closed_seconds if self.alert else None,
            "models_loaded": self.models_loaded,
            "gpu_available": self.gpu_available,
            "uptime_seconds": self.uptime_seconds,
            "enrolled_faces": self.enrolled_faces,
            "camera_count": self.camera_count,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "error": self.error,
        }


class VisionClient:
    """Client for polling the vision service.

    Usage:
        client = VisionClient(base_url="http://192.168.1.100:8100")
        await client.start_polling(callback=on_vision_update)

        # Or manual polling:
        status = await client.get_status()
        if status.alert and status.alert.active:
            handle_alert(status.alert)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8100",
        poll_interval_seconds: float = 30.0,
        timeout_seconds: float = 10.0,
    ):
        """Initialize vision client.

        Args:
            base_url: Vision service URL (e.g., http://192.168.1.100:8100)
            poll_interval_seconds: How often to poll (default 30s)
            timeout_seconds: Request timeout
        """
        self.base_url = base_url.rstrip("/")
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds

        self._session: Optional[aiohttp.ClientSession] = None
        self._polling_task: Optional[asyncio.Task] = None
        self._status = VisionStatus()
        self._callbacks: list[Callable[[VisionStatus], None]] = []

    @property
    def status(self) -> VisionStatus:
        """Get current vision status."""
        return self._status

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the client and cleanup resources."""
        await self.stop_polling()
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def health_check(self) -> bool:
        """Check if vision service is reachable.

        Returns:
            True if service is healthy
        """
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("status") == "ok"
                return False
        except Exception as e:
            logger.debug(f"Vision health check failed: {e}")
            return False

    async def get_status(self) -> VisionStatus:
        """Poll the vision service for current status.

        Returns:
            VisionStatus with alert info and system health
        """
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._parse_status(data)
                else:
                    return VisionStatus(
                        connected=False,
                        error=f"HTTP {resp.status}",
                        last_check_time=datetime.now(),
                    )

        except asyncio.TimeoutError:
            return VisionStatus(
                connected=False,
                error="Connection timeout",
                last_check_time=datetime.now(),
            )
        except aiohttp.ClientError as e:
            return VisionStatus(
                connected=False,
                error=f"Connection error: {e}",
                last_check_time=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Vision status error: {e}")
            return VisionStatus(
                connected=False,
                error=str(e),
                last_check_time=datetime.now(),
            )

    def _parse_status(self, data: Dict[str, Any]) -> VisionStatus:
        """Parse status response from vision service."""
        alert = None
        if data.get("alert_active"):
            alert = VisionAlert(
                active=True,
                reason=data.get("alert_reason"),
                camera_id=data.get("alert_camera_id"),
                camera_name=data.get("alert_camera_name"),
                eyes_closed_seconds=data.get("eyes_closed_seconds"),
                timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(),
            )

        system = data.get("system", {})

        return VisionStatus(
            connected=True,
            alert=alert,
            models_loaded=system.get("models_loaded", False),
            gpu_available=system.get("gpu_available", False),
            uptime_seconds=system.get("uptime_seconds", 0.0),
            enrolled_faces=system.get("enrolled_faces", 0),
            camera_count=len(data.get("cameras", [])),
            last_check_time=datetime.now(),
        )

    def add_callback(self, callback: Callable[[VisionStatus], None]) -> None:
        """Add a callback for status updates.

        Args:
            callback: Function(VisionStatus) to call on each poll
        """
        self._callbacks.append(callback)

    async def start_polling(
        self,
        callback: Optional[Callable[[VisionStatus], None]] = None,
    ) -> None:
        """Start background polling of vision service.

        Args:
            callback: Optional callback for status updates
        """
        if callback:
            self.add_callback(callback)

        if self._polling_task and not self._polling_task.done():
            return  # Already polling

        self._polling_task = asyncio.create_task(self._poll_loop())
        logger.info(f"Started vision polling at {self.base_url}")

    async def stop_polling(self) -> None:
        """Stop background polling."""
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None
            logger.info("Stopped vision polling")

    async def _poll_loop(self) -> None:
        """Background polling loop."""
        while True:
            try:
                self._status = await self.get_status()

                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        callback(self._status)
                    except Exception as e:
                        logger.error(f"Vision callback error: {e}")

                await asyncio.sleep(self.poll_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Vision poll error: {e}")
                await asyncio.sleep(self.poll_interval_seconds)


# Global client instance (lazy loaded)
_client: Optional[VisionClient] = None


def get_vision_client(base_url: Optional[str] = None) -> VisionClient:
    """Get or create the global vision client instance.

    Args:
        base_url: Vision service URL (only used on first call)

    Returns:
        VisionClient instance
    """
    global _client
    if _client is None:
        url = base_url or "http://localhost:8100"
        _client = VisionClient(base_url=url)
    return _client
