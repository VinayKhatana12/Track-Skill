"""Employer REST API: verification queue, hiring, talent pool."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.dependencies import require_role
from app.models import User
from app.models.enums import UserRole
from app.schemas.domain import DisputeRequest, HireTraineeRequest
from app.services import employer_service

router = APIRouter(prefix="/employer", tags=["Employer"])


@router.get("/verifications", summary="Pending employment claims")
def verifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> list[dict]:
    employer = employer_service.own_employer(db, current_user.id)
    return employer_service.pending_verifications(db, employer)


@router.post("/verifications/{verification_id}/confirm", summary="Confirm an employment claim")
async def confirm(
    verification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> dict:
    employer = employer_service.own_employer(db, current_user.id)
    return await employer_service.confirm_verification(
        db, employer=employer, verification_id=verification_id
    )


@router.post("/verifications/{verification_id}/dispute", summary="Dispute an employment claim")
async def dispute(
    verification_id: UUID,
    payload: DisputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> dict:
    employer = employer_service.own_employer(db, current_user.id)
    return await employer_service.dispute_verification(
        db, employer=employer, verification_id=verification_id, reason=payload.reason
    )


@router.post(
    "/trainees/{trainee_id}/hire",
    status_code=status.HTTP_201_CREATED,
    summary="Record hiring a certified trainee",
)
async def hire(
    trainee_id: UUID,
    payload: HireTraineeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> dict:
    employer = employer_service.own_employer(db, current_user.id)
    return await employer_service.hire_trainee(
        db,
        employer=employer,
        trainee_id=trainee_id,
        job_title=payload.job_title,
        monthly_wage=payload.monthly_wage,
        started_on=payload.started_on,
    )


@router.get("/talent-pool", summary="Certified, consented trainees by skill")
def talent_pool(
    skill: str | None = Query(default=None, description="Substring filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> list[dict]:
    employer = employer_service.own_employer(db, current_user.id)
    return employer_service.talent_pool(db, employer, skill)
