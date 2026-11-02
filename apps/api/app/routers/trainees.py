"""Trainee profile endpoints (Phase 2: ownership-scoped reads)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.dependencies import require_role
from app.models import Trainee, User
from app.models.enums import UserRole
from app.schemas import TraineePublic

router = APIRouter(prefix="/trainees", tags=["trainees"])


def _own_trainee_id(db: Session, user: User) -> UUID | None:
    return db.execute(select(Trainee.id).where(Trainee.user_id == user.id)).scalar_one_or_none()


@router.get("/me", response_model=TraineePublic)
def my_profile(
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
    db: Session = Depends(get_db),
) -> Trainee:
    """The caller's own trainee profile."""
    trainee_id = _own_trainee_id(db, current_user)
    if trainee_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No trainee profile is linked to this account yet.",
        )
    return db.get_one(Trainee, trainee_id)


@router.get("/{trainee_id}", response_model=TraineePublic)
def get_trainee(
    trainee_id: UUID,
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
    db: Session = Depends(get_db),
) -> Trainee:
    """A trainee profile is readable by its owning account only in Phase 2.

    Provider and admin scopes arrive with the profile phase. Reading another
    trainee's profile returns 404 (not 403) to avoid account enumeration.
    """
    trainee = db.get(Trainee, trainee_id)
    if trainee is None or _own_trainee_id(db, current_user) != trainee.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return trainee
