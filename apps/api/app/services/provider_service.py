"""Provider domain services: enrolment, certification, CSV import, overview."""

import csv
import io
import logging
import secrets
from datetime import date, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import tracer_nlp
from app.core.security import hash_password
from app.models import (
    Consent,
    Course,
    FollowUp,
    ProviderStaff,
    Trainee,
    TrainingCentre,
    User,
)
from app.models.enums import FollowUpState, TraineeStatus, UserRole
from app.services import ppi, tracer_service
from app.services.realtime import NotificationDraft, publish_event

logger = logging.getLogger(__name__)

csv.field_size_limit(1024 * 1024)


def provider_centre_ids(db: Session, user: User) -> list[UUID]:
    rows = db.execute(
        select(ProviderStaff.centre_id).where(ProviderStaff.user_id == user.id)
    ).scalars().all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No training centre is linked to this provider account.",
        )
    return list(rows)


def ensure_centre_access(db: Session, user: User, centre_id: UUID | None) -> UUID:
    allowed = provider_centre_ids(db, user)
    if centre_id is None:
        return allowed[0]
    if centre_id not in allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found.")
    return centre_id


def list_trainees(db: Session, user: User) -> list[dict]:
    centre_ids = provider_centre_ids(db, user)
    trainees = db.execute(
        select(Trainee).where(Trainee.centre_id.in_(centre_ids)).order_by(Trainee.enrolled_on)
    ).scalars().all()
    if not trainees:
        return []

    users = {
        row.id: row
        for row in db.execute(
            select(User).where(User.id.in_([trainee.user_id for trainee in trainees]))
        ).scalars()
    }
    courses = {
        row.id: row
        for row in db.execute(
            select(Course).where(Course.id.in_([trainee.course_id for trainee in trainees]))
        ).scalars()
    }
    consented = set(
        db.execute(
            select(Consent.trainee_id).where(
                Consent.trainee_id.in_([trainee.id for trainee in trainees]),
                Consent.granted.is_(True),
                Consent.revoked_at.is_(None),
            )
        ).scalars()
    )

    return [
        {
            "id": str(trainee.id),
            "name": users[trainee.user_id].name,
            "email": users[trainee.user_id].email,
            "course_id": str(trainee.course_id),
            "course_title": (
                courses[trainee.course_id].title if trainee.course_id in courses else None
            ),
            "status": trainee.status.value,
            "enrolled_on": trainee.enrolled_on.isoformat(),
            "certified_on": trainee.certified_on.isoformat() if trainee.certified_on else None,
            "consent_active": trainee.id in consented,
        }
        for trainee in trainees
    ]


async def enrol_trainee(
    db: Session,
    *,
    provider: User,
    centre_id: UUID,
    name: str,
    email: str,
    phone: str,
    course_id: UUID,
    gender: str,
) -> tuple[Trainee, str]:
    """Enrol a new trainee: creates the account and profile.

    Returns the trainee and a one-time temporary password the provider hands
    over out of band (the trainee is expected to change it later).
    """
    centre = db.get(TrainingCentre, centre_id)
    course = db.get(Course, course_id)
    if centre is None or course is None or course.centre_id != centre.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Course not found for this training centre.",
        )

    normalized_email = email.strip().lower()
    if (
        db.execute(select(User.id).where(User.email == normalized_email)).scalar_one_or_none()
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    temporary_password = secrets.token_urlsafe(12)
    user = User(
        id=uuid4(),
        name=name.strip(),
        email=normalized_email,
        password_hash=hash_password(temporary_password),
        role=UserRole.TRAINEE,
        is_demo=False,
        is_active=True,
    )
    trainee = Trainee(
        id=uuid4(),
        user_id=user.id,
        centre_id=centre.id,
        course_id=course.id,
        phone=phone.strip(),
        district=centre.district,
        gender=gender,
        enrolled_on=date.today(),
        certified_on=None,
        status=TraineeStatus.ENROLLED,
    )
    db.add_all([user, trainee])
    db.flush()

    await publish_event(
        db,
        event_type="TRAINEE_ENROLLED",
        actor_user_id=provider.id,
        actor_role=provider.role.value,
        payload={
            "trainee_id": str(trainee.id),
            "centre_id": str(centre.id),
            "course_title": course.title,
        },
        audience_user_ids=[user.id],
        audience_roles=[UserRole.PROVIDER.value],
        notifications=[
            NotificationDraft(
                user_id=user.id,
                title="You have been enrolled",
                body=(
                    f"{centre.name} enrolled you in {course.title}. Grant consent "
                    "to receive your milestone follow-ups."
                ),
                link="/dashboard/trainee",
            )
        ],
    )
    logger.info("Enrolled trainee %s", trainee.id)
    return trainee, temporary_password


async def bulk_import_csv(db: Session, *, provider: User, centre_id: UUID, content: str) -> dict:
    """Enrol many trainees from CSV (name,email,phone,course_id)."""
    centre = db.get(TrainingCentre, centre_id)
    if centre is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found.")

    reader = csv.DictReader(io.StringIO(content))
    required = {"name", "email", "phone", "course_id"}
    if reader.fieldnames is None or not required.issubset({f.strip() for f in reader.fieldnames}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must have a header with columns: name,email,phone,course_id",
        )

    batch_password = secrets.token_urlsafe(12)
    password_hash = hash_password(batch_password)
    created = skipped = 0
    errors: list[dict] = []

    for row_number, row in enumerate(reader, start=2):
        name = (row.get("name") or "").strip()
        email = (row.get("email") or "").strip().lower()
        phone = (row.get("phone") or "").strip()
        course_id = (row.get("course_id") or "").strip()
        try:
            if not name or not email or not phone or not course_id:
                raise ValueError("All columns are required")
            course = db.get(Course, UUID(course_id))
            if course is None or course.centre_id != centre.id:
                raise ValueError("Course not found for this training centre")
            if (
                db.execute(select(User.id).where(User.email == email)).scalar_one_or_none()
                is not None
            ):
                skipped += 1
                continue
            user = User(
                id=uuid4(),
                name=name,
                email=email,
                password_hash=password_hash,
                role=UserRole.TRAINEE,
                is_demo=False,
                is_active=True,
            )
            trainee = Trainee(
                id=uuid4(),
                user_id=user.id,
                centre_id=centre.id,
                course_id=course.id,
                phone=phone,
                district=centre.district,
                gender="UNSPECIFIED",
                enrolled_on=date.today(),
                certified_on=None,
                status=TraineeStatus.ENROLLED,
            )
            db.add_all([user, trainee])
            db.flush()
            created += 1
        except (ValueError, KeyError) as exc:
            errors.append({"row": row_number, "error": str(exc)})

    db.flush()
    await publish_event(
        db,
        event_type="TRAINEES_IMPORTED",
        actor_user_id=provider.id,
        actor_role=provider.role.value,
        payload={"centre_id": str(centre.id), "created": created, "skipped": skipped},
        audience_roles=[UserRole.PROVIDER.value],
    )
    logger.info("CSV import created %s trainees", created)
    return {"created": created, "skipped": skipped, "errors": errors}


async def certify_trainee(
    db: Session, *, provider: User, trainee_id: UUID, certified_on: date | None
) -> dict:
    trainee = db.get(Trainee, trainee_id)
    centre_ids = provider_centre_ids(db, provider)
    if trainee is None or trainee.centre_id not in centre_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trainee not found.")
    if trainee.status is TraineeStatus.CERTIFIED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Trainee is already certified."
        )

    trainee.status = TraineeStatus.CERTIFIED
    trainee.certified_on = certified_on or date.today()
    consent_active = tracer_service.has_active_consent(db, trainee.id)
    followups_scheduled = tracer_service.schedule_missing_followups(db, trainee)
    db.flush()

    await publish_event(
        db,
        event_type="TRAINEE_CERTIFIED",
        actor_user_id=provider.id,
        actor_role=provider.role.value,
        payload={
            "trainee_id": str(trainee.id),
            "certified_on": trainee.certified_on.isoformat(),
            "consent_active": consent_active,
            "followups_scheduled": followups_scheduled,
        },
        audience_user_ids=[trainee.user_id],
        audience_roles=[UserRole.PROVIDER.value],
        notifications=[
            NotificationDraft(
                user_id=trainee.user_id,
                title="Congratulations — you are certified!",
                body=(
                    "Grant consent for WhatsApp/IVR/SMS so we can follow up on "
                    "your employment at 3, 6 and 12 months."
                ),
                link="/dashboard/trainee",
            )
        ],
    )
    logger.info("Certified trainee %s", trainee.id)
    return {
        "trainee_id": str(trainee.id),
        "certified_on": trainee.certified_on.isoformat(),
        "consent_active": consent_active,
        "followups_scheduled": followups_scheduled,
    }


def provider_overview(db: Session, user: User) -> dict:
    centre_ids = provider_centre_ids(db, user)
    centre = db.get(TrainingCentre, centre_ids[0])
    metrics = ppi.compute_metrics(db, centre.id)

    trainee_ids = list(
        db.execute(select(Trainee.id).where(Trainee.centre_id.in_(centre_ids))).scalars()
    )
    consent_rate = 0.0
    if trainee_ids:
        consented = len(
            set(
                db.execute(
                    select(Consent.trainee_id).where(
                        Consent.trainee_id.in_(trainee_ids),
                        Consent.granted.is_(True),
                        Consent.revoked_at.is_(None),
                    )
                ).scalars().all()
            )
        )
        consent_rate = consented / len(set(trainee_ids))

    ranked = ppi.rank_centres(db)
    own_rank = next(
        (item for item in ranked if item["centre_id"] == str(centre.id)),
        {"rank": len(ranked), "ppi_score": metrics["ppi_score"]},
    )

    return {
        "centre": {"id": str(centre.id), "name": centre.name, "district": centre.district},
        "enrolled": metrics["enrolled"],
        "certified": metrics["certified"],
        "dropped": metrics["dropped"],
        "placements": metrics["placements"],
        "consent_rate": round(consent_rate, 4),
        "response_rate": metrics["response_rate"],
        "placement_rate": metrics["placement_rate"],
        "retention_3m": metrics["retention_3m"],
        "retention_6m": metrics["retention_6m"],
        "retention_12m": metrics["retention_12m"],
        "ppi_score": metrics["ppi_score"],
        "ppi_rank": own_rank["rank"],
        "total_centres": len(ranked),
    }


def provider_followups(db: Session, user: User) -> dict:
    """Due/overdue tracers with generated messages, plus replies flagged
    for manual review by the tracer reply parser."""
    centre_ids = provider_centre_ids(db, user)
    today = date.today()
    centre = db.get(TrainingCentre, centre_ids[0])
    centre_name = centre.name if centre else "your training centre"

    base = (
        select(FollowUp, Trainee, User)
        .join(Trainee, FollowUp.trainee_id == Trainee.id)
        .join(User, Trainee.user_id == User.id)
        .where(Trainee.centre_id.in_(centre_ids))
    )
    courses = {
        row.id: row.title
        for row in db.execute(select(Course).where(Course.centre_id.in_(centre_ids))).scalars()
    }

    def message_for(followup: FollowUp, user_row: User) -> str:
        return tracer_nlp.build_followup_message(
            channel=followup.channel.value,
            trainee_name=user_row.name,
            course_title=courses.get(
                _course_id_for_trainee(db, followup.trainee_id), "your course"
            ),
            milestone=followup.milestone.value,
            centre_name=centre_name,
        )

    def item(followup: FollowUp, trainee: Trainee, user_row: User) -> dict:
        return {
            "followup_id": str(followup.id),
            "trainee_id": str(trainee.id),
            "trainee_name": user_row.name,
            "milestone": followup.milestone.value,
            "due_on": followup.due_on.isoformat(),
            "channel": followup.channel.value,
            "state": followup.state.value,
            "message": message_for(followup, user_row),
        }

    pending_rows = db.execute(
        base.where(FollowUp.state.in_([FollowUpState.SCHEDULED, FollowUpState.SENT])).order_by(
            FollowUp.due_on
        )
    ).all()
    overdue = [
        item(followup, trainee, user_row)
        for followup, trainee, user_row in pending_rows
        if followup.due_on < today
    ]
    due_soon = [
        item(followup, trainee, user_row)
        for followup, trainee, user_row in pending_rows
        if today <= followup.due_on <= today + timedelta(days=7)
    ]

    manual_rows = db.execute(
        base.where(
            FollowUp.state == FollowUpState.RESPONDED,
            FollowUp.response_json["needs_review"].astext == "true",
        ).order_by(FollowUp.responded_at)
    ).all()
    manual_review = [
        {
            "followup_id": str(followup.id),
            "trainee_id": str(trainee.id),
            "trainee_name": user_row.name,
            "milestone": followup.milestone.value,
            "responded_at": (
                followup.responded_at.isoformat() if followup.responded_at else None
            ),
            "raw_text": (followup.response_json or {}).get("raw_text"),
            "parsed": (followup.response_json or {}).get("parsed"),
        }
        for followup, trainee, user_row in manual_rows
    ]
    return {"overdue": overdue, "due_soon": due_soon, "manual_review": manual_review}


def _course_id_for_trainee(db: Session, trainee_id: UUID) -> UUID:
    return db.execute(select(Trainee.course_id).where(Trainee.id == trainee_id)).scalar_one()


def provider_courses(db: Session, user: User) -> list[dict]:
    centre_ids = provider_centre_ids(db, user)
    courses = db.execute(
        select(Course).where(Course.centre_id.in_(centre_ids)).order_by(Course.title)
    ).scalars().all()
    return [
        {"id": str(course.id), "title": course.title, "sector": course.sector}
        for course in courses
    ]
