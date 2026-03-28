"""WebSocket connection manager and event broadcasting.

Ref: TDD-05 Section 6 (WebSocket & Notifications).

Manages connected WebSocket clients and broadcasts events to all of them.
Uses asyncio-safe data structures for concurrent connection management.

Event types:
- artifact.status_changed  {artifact_id, status, project_id}
- agent.status_changed     {agent_id, status, readiness_score}
- execution.wave_completed {artifact_id, wave_number, total_waves}
- execution.failed         {artifact_id, error_message}
- budget.warning           {usage_pct, remaining_usd}
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts events.

    Thread-safe via asyncio — all mutations happen on the event loop.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection and register it."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(
            "WebSocket client connected (%d total)", len(self._connections)
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            self._connections.discard(websocket)
        logger.info(
            "WebSocket client disconnected (%d total)", len(self._connections)
        )

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        """Send an event to all connected clients.

        Silently removes dead connections.
        """
        message = json.dumps({"type": event_type, "payload": payload})

        async with self._lock:
            connections = set(self._connections)

        dead: list[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)
            logger.debug("Cleaned up %d dead WebSocket connections", len(dead))

    @property
    def connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self._connections)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

ws_manager = WebSocketManager()


# ---------------------------------------------------------------------------
# Broadcast helpers — called from business logic
# ---------------------------------------------------------------------------


async def broadcast_event(event_type: str, payload: dict[str, Any]) -> None:
    """Convenience function to broadcast via the global manager."""
    await ws_manager.broadcast(event_type, payload)


async def broadcast_artifact_status_changed(
    artifact_id: str, status: str, project_id: str
) -> None:
    """Broadcast artifact.status_changed event."""
    await broadcast_event(
        "artifact.status_changed",
        {"artifact_id": artifact_id, "status": status, "project_id": project_id},
    )


async def broadcast_agent_status_changed(
    agent_id: str, status: str, readiness_score: int
) -> None:
    """Broadcast agent.status_changed event."""
    await broadcast_event(
        "agent.status_changed",
        {"agent_id": agent_id, "status": status, "readiness_score": readiness_score},
    )


async def broadcast_wave_completed(
    artifact_id: str, wave_number: int, total_waves: int
) -> None:
    """Broadcast execution.wave_completed event."""
    await broadcast_event(
        "execution.wave_completed",
        {
            "artifact_id": artifact_id,
            "wave_number": wave_number,
            "total_waves": total_waves,
        },
    )


async def broadcast_execution_failed(
    artifact_id: str, error_message: str
) -> None:
    """Broadcast execution.failed event."""
    await broadcast_event(
        "execution.failed",
        {"artifact_id": artifact_id, "error_message": error_message},
    )


async def broadcast_budget_warning(
    usage_pct: int, remaining_usd: float
) -> None:
    """Broadcast budget.warning event."""
    await broadcast_event(
        "budget.warning",
        {"usage_pct": usage_pct, "remaining_usd": remaining_usd},
    )
