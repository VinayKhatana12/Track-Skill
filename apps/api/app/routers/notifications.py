"""Notification endpoints: list mine, mark read, mark all read."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.dependencies import require_role
from app.models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", summary="My notifications (newest first)")
def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    items = db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    ).scalars().all()
    unread = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == current_user.id, Notification.read.is_(False))
    ).scalar_one()
    return {
        "unread": unread,
        "items": [
            {
                "id": str(item.id),
                "title": item.title,
                "body": item.body,
                "link": item.link,
                "read": item.read,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
    }


@router.post("/{notification_id}/read", summary="Mark one notification read")
def mark_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    notification.read = True
    db.flush()
    return {"read": True}


@router.post("/read-all", summary="Mark all my notifications read")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.read.is_(False))
        .values(read=True)
    )
    db.flush()
    return {"updated": result.rowcount or 0}
