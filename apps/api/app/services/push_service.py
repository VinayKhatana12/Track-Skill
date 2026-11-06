"""Web Push delivery (Phase 10): send encrypted notifications to a user's
browsers via their push services, prune dead subscriptions.

Delivery is fire-and-forget: the realtime event publisher snapshots the
subscription rows and hands them here; network I/O runs in a worker thread so
request latency is untouched, and every failure is logged, never raised.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.vapid import load_or_create_keypair
from app.models.push import PushSubscription

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

PushTarget = tuple[str, str, str]  # (endpoint, p256dh, auth)


def snapshot_subscriptions(db: "Session", user_ids: list) -> list[PushTarget]:
    """Read subscription rows synchronously (inside the caller's session)."""
    if not user_ids:
        return []
    rows = db.execute(
        select(
            PushSubscription.endpoint,
            PushSubscription.p256dh,
            PushSubscription.auth,
        ).where(PushSubscription.user_id.in_(user_ids))
    ).all()
    return [(row[0], row[1], row[2]) for row in rows]


def _send_one(target: PushTarget, payload: dict) -> None:
    """Blocking single send; raises on failure for the caller to classify."""
    private_key, _ = load_or_create_keypair()
    settings = get_settings()
    endpoint, p256dh, auth = target
    webpush(
        subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
        data=json.dumps(payload),
        vapid_private_key=private_key,
        vapid_claims={"sub": settings.push_subject},
    )


def _prune(endpoints: list[str]) -> None:
    with SessionLocal() as session:
        session.execute(delete(PushSubscription).where(PushSubscription.endpoint.in_(endpoints)))
        session.commit()


def _dispatch(targets: list[PushTarget], payload: dict, user_ids: list) -> None:
    """Send to every target in this thread; prune endpoints the push service
    reports as gone (404/410)."""
    sent = 0
    failed = 0
    gone: list[str] = []
    for target in targets:
        try:
            _send_one(target, payload)
            sent += 1
        except WebPushException as error:
            response = getattr(error, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code in (404, 410):
                gone.append(target[0])
            else:
                failed += 1
                logger.warning("Push to %s failed: %s", target[0][:64], error)
        except Exception as error:
            failed += 1
            logger.warning("Push to %s failed unexpectedly: %s", target[0][:64], error)

    if sent and user_ids:
        with SessionLocal() as session:
            for user_id in user_ids:
                session.execute(
                    PushSubscription.__table__.update()
                    .where(PushSubscription.user_id == user_id)
                    .values(last_pushed_at=datetime.now(UTC))
                )
            session.commit()
    if gone:
        _prune(gone)

    if sent or failed:
        logger.info("Web push batch: sent=%d failed=%d pruned=%d", sent, failed, len(gone))


def dispatch_push_async(targets: list[PushTarget], payload: dict, user_ids: list) -> None:
    """Schedule the blocking sends in a worker thread from async code."""
    if not targets:
        return
    asyncio.get_running_loop().run_in_executor(None, _dispatch, targets, payload, user_ids)


def send_to_user_sync(db: "Session", user_id, payload: dict) -> dict:
    """Synchronous send used by the /push/test endpoint and tests.

    Returns counters; prunes subscriptions that the push service reports as
    gone. Runs in-thread, so tests can monkeypatch ``_send_one``.
    """
    targets = snapshot_subscriptions(db, [user_id])
    sent = 0
    failed = 0
    gone: list[str] = []
    for target in targets:
        try:
            _send_one(target, payload)
            sent += 1
        except WebPushException as error:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            if status_code in (404, 410):
                gone.append(target[0])
            else:
                failed += 1
        except Exception:
            failed += 1
    if gone:
        db.execute(delete(PushSubscription).where(PushSubscription.endpoint.in_(gone)))
        db.flush()
    return {"sent": sent, "failed": failed, "pruned": len(gone)}
