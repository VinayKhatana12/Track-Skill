"""Web push endpoints (Phase 10): VAPID public key, subscribe, unsubscribe,
and a test send so the demo can prove delivery end to end."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.vapid import public_key_for_browser
from app.dependencies import require_role
from app.models.push import PushSubscription
from app.models.user import User
from app.services.push_service import send_to_user_sync

router = APIRouter(prefix="/push", tags=["push"])


class SubscriptionBody(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1000)
    keys: dict[str, str]
    user_agent: str | None = None


class UnsubscribeBody(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1000)


@router.get("/public-key", summary="VAPID public key for PushManager.subscribe")
def get_public_key(current_user: User = Depends(require_role())) -> dict:
    return {"public_key": public_key_for_browser()}


@router.post("/subscriptions", summary="Register this browser for pushes")
def subscribe(
    body: SubscriptionBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    p256dh = body.keys.get("p256dh")
    auth = body.keys.get("auth")
    if not p256dh or not auth:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Subscription keys must include p256dh and auth.",
        )

    existing = db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    ).scalar_one_or_none()
    if existing is None:
        existing = PushSubscription(
            id=uuid.uuid4(),
            user_id=current_user.id,
            endpoint=body.endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=body.user_agent,
        )
        db.add(existing)
    else:
        # A subscription belongs to whoever holds it now (e.g. re-login).
        existing.user_id = current_user.id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.user_agent = body.user_agent
    db.flush()
    return {"status": "subscribed"}


@router.post("/subscriptions/delete", summary="Remove a browser subscription")
def unsubscribe(
    body: UnsubscribeBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    existing = db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    ).scalar_one_or_none()
    if existing is not None and existing.user_id == current_user.id:
        db.delete(existing)
        db.flush()
    return {"status": "unsubscribed"}


@router.post("/test", summary="Send a test push to all my devices")
def test_push(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    result = send_to_user_sync(
        db,
        current_user.id,
        {
            "title": "TrackSkill AI test notification",
            "body": "If you can read this, Web Push delivery works end to end.",
            "link": "/dashboard",
        },
    )
    return result
