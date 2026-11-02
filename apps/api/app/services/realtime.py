"""Event publishing: audit row + notifications + realtime broadcast.

Every mutating endpoint calls :func:`publish_event` so the audit log
(``events`` table), user notifications and the WebSocket audience stay in
sync. Rows are flushed within the caller's request transaction and committed
by ``get_db`` when the request finishes.
"""

import logging
from collections.abc import Sequence
from typing import NamedTuple
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models import Event, Notification
from app.realtime.manager import manager

logger = logging.getLogger(__name__)


class NotificationDraft(NamedTuple):
    user_id: UUID
    title: str
    body: str
    link: str | None = None


async def publish_event(
    db: Session,
    *,
    event_type: str,
    actor_user_id: UUID | None,
    actor_role: str,
    payload: dict | None = None,
    audience_user_ids: Sequence[UUID] = (),
    audience_roles: Sequence[str] = (),
    notifications: Sequence[NotificationDraft] = (),
) -> UUID:
    """Persist an audit event (plus notifications) and broadcast it live.

    Audience channels are ``user:<id>`` and ``role:<ROLE>``; duplicates in
    the audience lists are collapsed while preserving order.
    """
    resolved_payload = dict(payload or {})
    event = Event(
        id=uuid4(),
        type=event_type,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        payload=resolved_payload,
    )
    db.add(event)
    for draft in notifications:
        db.add(
            Notification(
                id=uuid4(),
                user_id=draft.user_id,
                title=draft.title,
                body=draft.body,
                link=draft.link,
                read=False,
            )
        )
    db.flush()

    message_payload = {**resolved_payload, "event_id": str(event.id)}
    for user_id in dict.fromkeys(audience_user_ids):
        await manager.broadcast(f"user:{user_id}", event_type, message_payload)
    for role in dict.fromkeys(audience_roles):
        await manager.broadcast(f"role:{role}", event_type, message_payload)
    return event.id
