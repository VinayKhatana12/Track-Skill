"""Trainee REST API: journey, consent, follow-up responses, skills."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai import skill_assessment
from app.core.db import get_db
from app.dependencies import require_role
from app.models import Course, User
from app.models.enums import UserRole
from app.schemas.domain import (
    ConsentRequest,
    RespondFollowUpRequest,
    RespondTextRequest,
    SkillsAssessmentRequest,
)
from app.services import tracer_service, trainee_service

router = APIRouter(prefix="/trainee", tags=["Trainee"])


@router.get("/me", summary="Profile, journey timeline and upcoming milestones")
def me(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
) -> dict:
    trainee = trainee_service.own_trainee(db, current_user.id)
    return trainee_service.me_view(db, trainee)


@router.post("/consent", summary="Grant or revoke consent per channel")
async def consent(
    payload: ConsentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
) -> dict:
    trainee = trainee_service.own_trainee(db, current_user.id)
    return await trainee_service.set_consent(
        db, trainee=trainee, channel=payload.channel, granted=payload.granted
    )


@router.get("/messages", summary="All tracers as chat/call items for the Messages panel")
def messages(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
) -> list[dict]:
    trainee = trainee_service.own_trainee(db, current_user.id)
    return tracer_service.get_trainee_messages(db, trainee)


@router.post("/followups/{followup_id}/respond", summary="Answer a milestone tracer")
async def respond(
    followup_id: UUID,
    payload: RespondFollowUpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
) -> dict:
    trainee = trainee_service.own_trainee(db, current_user.id)
    return await trainee_service.respond_followup(
        db, trainee=trainee, followup_id=followup_id, payload=payload
    )


@router.post(
    "/followups/{followup_id}/respond/text",
    summary="Answer a tracer in free text (parsed with confidence)",
)
async def respond_text(
    followup_id: UUID,
    payload: RespondTextRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
) -> dict:
    trainee = trainee_service.own_trainee(db, current_user.id)
    return await trainee_service.respond_followup_text(
        db, trainee=trainee, followup_id=followup_id, message_text=payload.message
    )


@router.post(
    "/skills/assessment",
    summary="AI skill profile (confidence per skill) and top-5 job-role matches",
)
async def skills_assessment(
    payload: SkillsAssessmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
) -> dict:
    trainee = trainee_service.own_trainee(db, current_user.id)
    course = db.get(Course, trainee.course_id)
    course_skills = list(course.skills) if course and course.skills else []
    return skill_assessment.assess_skills(
        course_skills=course_skills,
        self_reported_skills=payload.self_reported_skills,
        free_text=payload.free_text,
    )


@router.get("/skills", summary="AI skill assessment and recommended courses")
def skills(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
) -> dict:
    trainee = trainee_service.own_trainee(db, current_user.id)
    return trainee_service.skills_view(db, trainee)
