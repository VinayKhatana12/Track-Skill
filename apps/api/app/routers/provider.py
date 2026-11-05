"""Provider REST API: enrolment, certification, overview, follow-ups."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.dependencies import require_role
from app.models import User
from app.models.enums import UserRole
from app.schemas.domain import CertifyTraineeRequest, EnrolTraineeRequest
from app.services import provider_service

router = APIRouter(prefix="/provider", tags=["Provider"])
logger = logging.getLogger(__name__)


@router.get("/trainees", summary="List the centre's trainees")
def list_trainees(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.PROVIDER)),
) -> list[dict]:
    return provider_service.list_trainees(db, current_user)


@router.post("/trainees", status_code=status.HTTP_201_CREATED, summary="Enrol a trainee")
async def enrol_trainee(
    payload: EnrolTraineeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.PROVIDER)),
) -> dict:
    centre_id = provider_service.ensure_centre_access(db, current_user, payload.centre_id)
    trainee, temporary_password = await provider_service.enrol_trainee(
        db,
        provider=current_user,
        centre_id=centre_id,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        course_id=payload.course_id,
        gender=payload.gender,
    )
    return {
        "trainee": {
            "id": str(trainee.id),
            "name": payload.name,
            "email": payload.email,
            "status": trainee.status.value,
        },
        # Shown once to the provider to hand to the trainee.
        "temporary_password": temporary_password,
    }


@router.post("/trainees/import", status_code=status.HTTP_201_CREATED, summary="Bulk CSV import")
async def import_trainees(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.PROVIDER)),
) -> dict:
    centre_id = provider_service.ensure_centre_access(db, current_user, None)
    content = (await file.read()).decode("utf-8")
    return await provider_service.bulk_import_csv(
        db, provider=current_user, centre_id=centre_id, content=content
    )


@router.patch("/trainees/{trainee_id}/certify", summary="Certify a trainee")
async def certify_trainee(
    trainee_id: UUID,
    payload: CertifyTraineeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.PROVIDER)),
) -> dict:
    return await provider_service.certify_trainee(
        db, provider=current_user, trainee_id=trainee_id, certified_on=payload.certified_on
    )


@router.get("/courses", summary="Courses offered by my centre(s)")
def courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.PROVIDER)),
) -> list[dict]:
    return provider_service.provider_courses(db, current_user)


@router.get("/overview", summary="Centre KPIs, PPI and rank")
def overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.PROVIDER)),
) -> dict:
    return provider_service.provider_overview(db, current_user)


@router.get("/curriculum-gaps", summary="Curriculum-demand gap alerts for your courses")
def curriculum_gaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.PROVIDER)),
) -> list[dict]:
    from app.ai.curriculum_matcher import course_gap_report

    centre_ids = set(provider_service.provider_centre_ids(db, current_user))
    report = course_gap_report(db, limit=200)
    return [row for row in report if row["course_id"] in {str(cid) for cid in centre_ids}]


@router.get("/followups", summary="Due and overdue milestone tracers")
def followups(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.PROVIDER)),
) -> dict:
    return provider_service.provider_followups(db, current_user)
