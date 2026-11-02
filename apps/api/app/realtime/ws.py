"""WebSocket gateway.

- With a valid access token: the socket joins the caller's ``user:<id>`` and
  ``role:<ROLE>`` channels and receives every domain event published to them.
- Without a token: the socket joins an isolated ``public:<channel>`` sandbox
  used by the landing-page demo; server domain events never reach it.

Clients send JSON frames ``{"event": "ping", "payload": {...}}``; a ping is
answered privately with a pong. Anonymous sockets may broadcast inside their
sandbox; authenticated sockets only receive.
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_token
from app.models import User
from app.realtime.manager import manager

router = APIRouter()
logger = logging.getLogger(__name__)

WELCOME_EVENT = "connection.established"
ERROR_EVENT = "error"


async def _reject(websocket: WebSocket, message: str) -> None:
    await websocket.accept()
    await manager.send_to(websocket, ERROR_EVENT, {"message": message})
    await websocket.close(code=4401)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    channel: str = Query(default="global", min_length=1, max_length=64),
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    channels: list[str] = [f"public:{channel}"]
    role_label = "anonymous"

    if token:
        try:
            payload = decode_token(token, expected_type="access")
            user_id = UUID(str(payload.get("sub")))
        except (InvalidTokenError, ValueError):
            await _reject(websocket, "Invalid or expired session.")
            return
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            await _reject(websocket, "Invalid or expired session.")
            return
        channels = [f"user:{user.id}", f"role:{user.role.value}"]
        role_label = user.role.value

    await manager.connect(channels, websocket)
    await manager.send_to(websocket, WELCOME_EVENT, {"channels": channels, "role": role_label})
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
                if not isinstance(frame, dict):
                    raise ValueError("frame must be a JSON object")
            except ValueError:
                await manager.send_to(
                    websocket,
                    ERROR_EVENT,
                    {"message": 'Frames must be JSON objects: {"event": "...", "payload": {}}'},
                )
                continue

            event = str(frame.get("event") or "message")
            frame_payload = frame.get("payload")
            if not isinstance(frame_payload, dict):
                frame_payload = {}

            if event == "ping":
                await manager.send_to(websocket, "pong", {"echo": frame_payload})
            elif channels[0].startswith("public:"):
                await manager.broadcast(channels[0], event, frame_payload)
            else:
                await manager.send_to(
                    websocket,
                    ERROR_EVENT,
                    {"message": "Authenticated sockets receive domain events; send pings only."},
                )
    except WebSocketDisconnect:
        manager.disconnect(channels, websocket)
        logger.info("WebSocket left channel(s) %s", channels)
