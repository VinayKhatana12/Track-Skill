"""Realtime connection registry.

Sockets join channel sets: authenticated clients join ``user:<id>`` and
``role:<ROLE>`` channels; anonymous clients (landing demo) join
``public:<name>`` sandboxes. Domain events are broadcast only to the
audience channels of each event.
"""

import json
import logging
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks WebSocket clients per channel and broadcasts JSON events."""

    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, channels: Sequence[str], websocket: WebSocket) -> None:
        """Accept a socket and register it on every given channel."""
        await websocket.accept()
        for channel in channels:
            self._channels[channel].add(websocket)
        logger.info(
            "WebSocket joined %s channel(s) (%s tracked)",
            list(channels),
            sum(len(sockets) for sockets in self._channels.values()),
        )

    def disconnect(self, channels: Sequence[str], websocket: WebSocket) -> None:
        """Remove a socket from its channels (idempotent)."""
        for channel in channels:
            self._channels[channel].discard(websocket)

    async def send_to(
        self, websocket: WebSocket, event: str, payload: dict[str, Any] | None = None
    ) -> None:
        """Send a private event to a single client."""
        message = json.dumps({"event": event, "payload": payload or {}}, default=str)
        try:
            await websocket.send_text(message)
        except Exception:
            logger.warning("Failed to deliver event '%s' to a WebSocket client", event)

    async def broadcast(
        self, channel: str, event: str, payload: dict[str, Any] | None = None
    ) -> None:
        """Send an event to every client on a channel, dropping dead sockets."""
        message = json.dumps({"event": event, "payload": payload or {}}, default=str)
        dead: list[WebSocket] = []
        for websocket in tuple(self._channels.get(channel, ())):
            try:
                await websocket.send_text(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            for sockets in self._channels.values():
                sockets.discard(websocket)
        if dead:
            logger.warning("Dropped %s dead socket(s) from channel '%s'", len(dead), channel)

    def channel_sizes(self) -> dict[str, int]:
        """Snapshot of connected client counts per channel."""
        return {channel: len(sockets) for channel, sockets in self._channels.items() if sockets}


manager = ConnectionManager()
