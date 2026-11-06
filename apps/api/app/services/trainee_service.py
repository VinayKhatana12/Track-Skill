"""Trainee domain services: consent, follow-up responses, journey, skills."""

import logging
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai import skills as ai_skills
from app.ai import tracer_nlp
from app.core.constants import (
    CONSENT_PURPOSE,
    CONSENT_VERSION,
    WORKING_STATUSES,
)
from app.models import (
    Consent,
    Course,
    Employer,
    EmploymentRecord,
    Event,
    FollowUp,
    Notification,
    ProviderStaff,
    PushSubscription,
    Trainee,
    TrainingCentre,
    User,
    Verification,
)
from app.models.enums import (
    EmploymentStatus,
    FollowUpState,
    VerificationSignal,
)
from app.services import tracer_service
from app.services.realtime import NotificationDraft, publish_event

logger = logging.getLogger(__name__)


def own_trainee(db: Session, user_id: UUID) -> Trainee:
    trainee = db.execute(select(Trainee).where(Trainee.user_id == user_id)).scalar_one_or_none()
    if trainee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No trainee profile is linked to this account yet.",
        )
    return trainee


async def set_consent(db: Session, *, trainee: Trainee, channel, granted: bool) -> dict:
    """Grant or revoke consent for one channel, enforcing the tracing rule.

    Granting schedules missing milestone tracers for a certified trainee.
    Revoking cancels every tracer that has not happened yet — a trainee
    without active consent is never traced.
    """
    consent = db.execute(
        select(Consent).where(
            Consent.trainee_id == trainee.id,
            Consent.channel == channel,
            Consent.version == CONSENT_VERSION,
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)

    followups_scheduled = 0
    followups_cancelled = 0
    if granted:
        if consent is None:
            consent = Consent(
                id=uuid4(),
                trainee_id=trainee.id,
                channel=channel,
                granted=True,
                granted_at=now,
                revoked_at=None,
                purpose_text=CONSENT_PURPOSE,
                version=CONSENT_VERSION,
            )
            db.add(consent)
        else:
            consent.granted = True
            consent.granted_at = now
            consent.revoked_at = None
        # Sessions run with autoflush off — make the consent visible to the
        # scheduler's queries before scheduling tracers.
        db.flush()
        followups_scheduled = tracer_service.schedule_missing_followups(db, trainee)
    else:
        if consent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No consent record exists for this channel.",
            )
        if consent.revoked_at is None:
            consent.revoked_at = now
        followups_cancelled = tracer_service.cancel_pending_followups(db, trainee.id)
    db.flush()

    await publish_event(
        db,
        event_type="CONSENT_GRANTED" if granted else "CONSENT_REVOKED",
        actor_user_id=trainee.user_id,
        actor_role="TRAINEE",
        payload={
            "trainee_id": str(trainee.id),
            "channel": channel.value,
            "granted": granted,
            "followups_scheduled": followups_scheduled,
            "followups_cancelled": followups_cancelled,
        },
        audience_roles=["PROVIDER"],
    )
    logger.info("Consent updated for trainee %s (channel %s)", trainee.id, channel.value)
    return {
        "channel": channel.value,
        "granted": granted,
        "followups_scheduled": followups_scheduled,
        "followups_cancelled": followups_cancelled,
    }


def _upsert_job_claim(
    db: Session, *, trainee: Trainee, payload, employer_id: UUID | None
) -> Verification:
    record = db.execute(
        select(EmploymentRecord)
        .where(EmploymentRecord.trainee_id == trainee.id)
        .order_by(EmploymentRecord.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if record is None:
        record = EmploymentRecord(
            id=uuid4(),
            trainee_id=trainee.id,
            employer_id=employer_id,
            status=payload.employment_status,
            job_title=payload.job_title,
            monthly_wage=payload.monthly_wage,
            started_on=date.today(),
        )
        verification = None
    else:
        record.status = payload.employment_status
        record.employer_id = employer_id or record.employer_id
        record.job_title = payload.job_title or record.job_title
        if payload.monthly_wage is not None:
            record.monthly_wage = payload.monthly_wage
        verification = db.execute(
            select(Verification).where(Verification.employment_record_id == record.id)
        ).scalar_one_or_none()

    db.add(record)
    db.flush()

    if verification is None:
        verification = Verification(
            id=uuid4(),
            employment_record_id=record.id,
            trainee_signal=VerificationSignal.CONFIRMED,
            employer_signal=VerificationSignal.PENDING,
        )
        db.add(verification)
    else:
        verification.trainee_signal = VerificationSignal.CONFIRMED
    db.flush()
    return verification


async def respond_followup(db: Session, *, trainee: Trainee, followup_id: UUID, payload) -> dict:
    """Record a tracer response; a job claim creates a pending verification."""
    followup = db.get(FollowUp, followup_id)
    if followup is None or followup.trainee_id != trainee.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up not found.")
    if followup.state is FollowUpState.RESPONDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This follow-up was already answered."
        )
    if followup.state is FollowUpState.MISSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This follow-up window has closed."
        )

    employer_id = payload.employer_id
    if employer_id is not None and db.get(Employer, employer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employer not found.")

    followup.state = FollowUpState.RESPONDED
    followup.responded_at = datetime.now(UTC)
    followup.response_json = {
        "employment": payload.employment_status.value,
        "job_title": payload.job_title,
        "wage": payload.monthly_wage,
        "employer_id": str(employer_id) if employer_id else None,
        "channel": followup.channel.value.lower(),
    }

    verification: Verification | None = None
    if payload.employment_status in WORKING_STATUSES:
        verification = _upsert_job_claim(
            db, trainee=trainee, payload=payload, employer_id=employer_id
        )

    employer_user_id = None
    if employer_id is not None:
        employer = db.get(Employer, employer_id)
        employer_user_id = employer.user_id if employer else None

    notifications = []
    if employer_user_id:
        notifications.append(
            NotificationDraft(
                user_id=employer_user_id,
                title="New employment claim to verify",
                body=(
                    "A trainee named you as their employer for a role as "
                    f"{payload.job_title or payload.employment_status.value}. "
                    "Confirm or dispute it."
                ),
                link="/dashboard/employer",
            )
        )

    await publish_event(
        db,
        event_type="FOLLOWUP_RESPONDED",
        actor_user_id=trainee.user_id,
        actor_role="TRAINEE",
        payload={
            "followup_id": str(followup.id),
            "trainee_id": str(trainee.id),
            "milestone": followup.milestone.value,
            "employment": payload.employment_status.value,
            "employer_id": str(employer_id) if employer_id else None,
            "verification_id": str(verification.id) if verification else None,
        },
        audience_roles=["PROVIDER"],
        audience_user_ids=[employer_user_id] if employer_user_id else [],
        notifications=notifications,
    )
    return {
        "followup_id": str(followup.id),
        "state": followup.state.value,
        "verification_id": str(verification.id) if verification else None,
    }


def me_view(db: Session, trainee: Trainee) -> dict:
    user = db.get(User, trainee.user_id)
    course = db.get(Course, trainee.course_id)
    followups = db.execute(
        select(FollowUp).where(FollowUp.trainee_id == trainee.id).order_by(FollowUp.due_on)
    ).scalars().all()
    consents = db.execute(
        select(Consent).where(Consent.trainee_id == trainee.id).order_by(Consent.granted_at)
    ).scalars().all()
    records = db.execute(
        select(EmploymentRecord).where(EmploymentRecord.trainee_id == trainee.id)
    ).scalars().all()

    timeline = [
        {
            "date": trainee.enrolled_on.isoformat(),
            "type": "ENROLLED",
            "title": f"Enrolled in {course.title}" if course else "Enrolled",
            "detail": trainee.district,
        }
    ]
    for consent in consents:
        revoked = consent.revoked_at is not None
        timeline.append(
            {
                "date": (consent.revoked_at or consent.granted_at).date().isoformat(),
                "type": "CONSENT_REVOKED" if revoked else "CONSENT_GRANTED",
                "title": f"Consent for {consent.channel.value}",
                "detail": CONSENT_PURPOSE,
            }
        )
    if trainee.certified_on:
        timeline.append(
            {
                "date": trainee.certified_on.isoformat(),
                "type": "CERTIFIED",
                "title": "Certified",
                "detail": course.title if course else None,
            }
        )
    for record in records:
        if record.started_on:
            timeline.append(
                {
                    "date": record.started_on.isoformat(),
                    "type": "EMPLOYMENT",
                    "title": record.job_title or record.status.value,
                    "detail": record.status.value,
                }
            )
    for followup in followups:
        if followup.responded_at:
            timeline.append(
                {
                    "date": followup.responded_at.date().isoformat(),
                    "type": "FOLLOWUP_RESPONDED",
                    "title": f"{followup.milestone.value} follow-up answered",
                    "detail": (followup.response_json or {}).get("employment"),
                }
            )

    timeline.sort(key=lambda item: item["date"] or "")
    centre = db.get(TrainingCentre, trainee.centre_id)
    course_title = course.title if course else "your course"
    trainee_name = user.name if user else "Trainee"
    upcoming = [
        {
            "followup_id": str(followup.id),
            "milestone": followup.milestone.value,
            "due_on": followup.due_on.isoformat(),
            "channel": followup.channel.value,
            "state": followup.state.value,
            "message": tracer_nlp.build_followup_message(
                channel=followup.channel.value,
                trainee_name=trainee_name,
                course_title=course_title,
                milestone=followup.milestone.value,
                centre_name=centre.name if centre else "your training centre",
            ),
        }
        for followup in followups
        if followup.state in (FollowUpState.SCHEDULED, FollowUpState.SENT)
    ]

    verification_signals = {
        verification.employment_record_id: (
            verification.trainee_signal,
            verification.employer_signal,
        )
        for verification in db.execute(
            select(Verification).where(
                Verification.employment_record_id.in_(
                    [record.id for record in records] or [uuid4()]
                )
            )
        ).scalars()
    }
    from app.services.ppi import is_verified

    employment = None
    if records:
        record = records[-1]
        signals = verification_signals.get(record.id, (None, None))
        employment = {
            "employment_record_id": str(record.id),
            "status": record.status.value,
            "job_title": record.job_title,
            "monthly_wage": float(record.monthly_wage) if record.monthly_wage else None,
            "started_on": record.started_on.isoformat() if record.started_on else None,
            "employer_id": str(record.employer_id) if record.employer_id else None,
            "trainee_signal": signals[0].value if signals[0] else None,
            "employer_signal": signals[1].value if signals[1] else None,
            "verified": is_verified(signals),
        }

    consent_state = [
        {
            "channel": consent.channel.value,
            "granted": consent.granted,
            "active": consent.granted and consent.revoked_at is None,
            "version": consent.version,
        }
        for consent in consents
    ]

    return {
        "profile": {
            "id": str(trainee.id),
            "name": user.name if user else None,
            "district": trainee.district,
            "gender": trainee.gender,
            "enrolled_on": trainee.enrolled_on.isoformat(),
            "certified_on": trainee.certified_on.isoformat() if trainee.certified_on else None,
            "status": trainee.status.value,
            "course_title": course.title if course else None,
        },
        "consents": consent_state,
        "employment": employment,
        "timeline": timeline,
        "upcoming": upcoming,
    }


def skills_view(db: Session, trainee: Trainee) -> dict:
    course = db.get(Course, trainee.course_id)
    own_skills = list(course.skills) if course and course.skills else []
    return {
        "skills": own_skills,
        "recommendations": ai_skills.recommended_skills(
            db, own_skills, district=trainee.district, limit=5
        ),
    }


async def report_employment(db: Session, *, trainee: Trainee, payload) -> dict:
    """Trainee self-reports current employment (dashboard employment card).

    Creates or updates the employment record and its dual-signal
    verification: the trainee signal is CONFIRMED (own report) and the
    employer signal stays PENDING until the employer confirms.
    """
    employer_id = payload.employer_id
    if employer_id is not None and db.get(Employer, employer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employer not found.")

    record = db.execute(
        select(EmploymentRecord)
        .where(EmploymentRecord.trainee_id == trainee.id)
        .order_by(EmploymentRecord.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if record is None:
        record = EmploymentRecord(
            id=uuid4(),
            trainee_id=trainee.id,
            employer_id=employer_id,
            status=payload.employment_status,
            job_title=payload.job_title,
            monthly_wage=payload.monthly_wage,
            started_on=payload.started_on or date.today(),
        )
        verification = None
    else:
        record.status = payload.employment_status
        record.job_title = payload.job_title or record.job_title
        if payload.monthly_wage is not None:
            record.monthly_wage = payload.monthly_wage
        if employer_id is not None:
            record.employer_id = employer_id
        verification = db.execute(
            select(Verification).where(Verification.employment_record_id == record.id)
        ).scalar_one_or_none()

    db.add(record)
    db.flush()

    if verification is None:
        verification = Verification(
            id=uuid4(),
            employment_record_id=record.id,
            trainee_signal=VerificationSignal.CONFIRMED,
            employer_signal=VerificationSignal.PENDING,
        )
        db.add(verification)
    elif payload.employment_status in WORKING_STATUSES:
        verification.trainee_signal = VerificationSignal.CONFIRMED
    db.flush()

    employer_user_id = None
    if record.employer_id:
        employer = db.get(Employer, record.employer_id)
        employer_user_id = employer.user_id if employer else None

    await publish_event(
        db,
        event_type="EMPLOYMENT_SELF_REPORTED",
        actor_user_id=trainee.user_id,
        actor_role="TRAINEE",
        payload={
            "trainee_id": str(trainee.id),
            "employment_record_id": str(record.id),
            "status": record.status.value,
            "job_title": record.job_title,
            "monthly_wage": float(record.monthly_wage) if record.monthly_wage else None,
            "verification_id": str(verification.id),
        },
        audience_roles=["PROVIDER"],
        audience_user_ids=[employer_user_id] if employer_user_id else [],
        notifications=[
            NotificationDraft(
                user_id=employer_user_id,
                title="Trainee reported employment",
                body=(
                    f"{payload.job_title or 'A role'} was self-reported at your company. "
                    "Verify it when ready."
                ),
                link="/dashboard/employer",
            )
        ]
        if employer_user_id
        else [],
    )
    return {
        "employment_record_id": str(record.id),
        "verification_id": str(verification.id),
        "trainee_signal": verification.trainee_signal.value,
        "employer_signal": verification.employer_signal.value,
        "verified": verification.trainee_signal is VerificationSignal.CONFIRMED
        and verification.employer_signal is VerificationSignal.CONFIRMED,
    }


async def respond_followup_text(
    db: Session, *, trainee: Trainee, followup_id: UUID, message_text: str
) -> dict:
    """Free-text tracer reply: parse with confidence; route low confidence
    to manual review instead of auto-creating a verification."""
    parsed = tracer_nlp.parse_reply(message_text)
    if parsed.needs_review or parsed.employment_status is None:
        return await _record_manual_review_response(
            db, trainee=trainee, followup_id=followup_id, parsed=parsed, raw_text=message_text
        )

    payload = SimpleNamespace(
        employment_status=EmploymentStatus(parsed.employment_status),
        job_title=parsed.job_title,
        monthly_wage=parsed.monthly_wage,
        employer_id=_match_employer(db, message_text),
    )
    result = await respond_followup(db, trainee=trainee, followup_id=followup_id, payload=payload)

    followup = db.get(FollowUp, UUID(result["followup_id"]))
    followup.response_json = {
        **(followup.response_json or {}),
        "parsed_from_text": parsed.to_dict(),
        "raw_text": message_text,
    }
    db.flush()
    result["needs_review"] = False
    result["confidence"] = parsed.confidence
    result["parsed"] = parsed.to_dict()
    return result


def _match_employer(db: Session, text: str) -> UUID | None:
    """Resolve an employer mention by company-name substring (longest match)."""
    lowered = text.lower()
    best: Employer | None = None
    for employer in db.execute(select(Employer)).scalars():
        mentioned = employer.company_name.lower() in lowered
        longer = best is None or len(employer.company_name) > len(best.company_name)
        if mentioned and longer:
            best = employer
    return best.id if best else None


async def _record_manual_review_response(
    db: Session,
    *,
    trainee: Trainee,
    followup_id: UUID,
    parsed: tracer_nlp.ParsedReply,
    raw_text: str,
) -> dict:
    """Record a reply the parser could not trust; flag it for review."""
    followup = db.get(FollowUp, followup_id)
    if followup is None or followup.trainee_id != trainee.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up not found.")
    if followup.state is FollowUpState.RESPONDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This follow-up was already answered."
        )
    if followup.state is FollowUpState.MISSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This follow-up window has closed."
        )

    followup.state = FollowUpState.RESPONDED
    followup.responded_at = datetime.now(UTC)
    followup.response_json = {
        "raw_text": raw_text,
        "parsed": parsed.to_dict(),
        "needs_review": True,
        "channel": followup.channel.value.lower(),
    }
    db.flush()

    staff_user_ids = list(
        db.execute(
            select(ProviderStaff.user_id).where(ProviderStaff.centre_id == trainee.centre_id)
        ).scalars()
    )
    await publish_event(
        db,
        event_type="FOLLOWUP_RESPONDED",
        actor_user_id=trainee.user_id,
        actor_role="TRAINEE",
        payload={
            "followup_id": str(followup.id),
            "trainee_id": str(trainee.id),
            "milestone": followup.milestone.value,
            "needs_review": True,
        },
        audience_roles=["PROVIDER"],
        notifications=[
            NotificationDraft(
                user_id=user_id,
                title="Manual review needed",
                body=(
                    "A tracer reply could not be parsed with confidence. "
                    "Please review it and record the outcome."
                ),
                link="/dashboard/provider",
            )
            for user_id in staff_user_ids
        ],
    )
    return {
        "followup_id": str(followup.id),
        "state": followup.state.value,
        "verification_id": None,
        "needs_review": True,
        "confidence": parsed.confidence,
        "parsed": parsed.to_dict(),
    }


# ── Data rights (Phase 11): export and erasure ───────────────────────────────


def export_my_data(db: Session, *, trainee: Trainee) -> dict:
    """Machine-readable copy of everything the platform stores about me.

    DPDP-aligned data access right: the export is the trainee's own record —
    profile, consents (including revoked ones), tracer messages, employment
    claims, notifications and the audit events they triggered. Written for
    transparency, not for re-import.
    """
    user = db.get(User, trainee.user_id)
    followups = db.execute(
        select(FollowUp).where(FollowUp.trainee_id == trainee.id).order_by(FollowUp.due_on)
    ).scalars().all()
    consents = db.execute(
        select(Consent).where(Consent.trainee_id == trainee.id).order_by(Consent.created_at)
    ).scalars().all()
    employment = db.execute(
        select(EmploymentRecord).where(EmploymentRecord.trainee_id == trainee.id)
    ).scalars().all()
    verifications = db.execute(
        select(Verification).join(
            EmploymentRecord, Verification.employment_record_id == EmploymentRecord.id
        ).where(EmploymentRecord.trainee_id == trainee.id)
    ).scalars().all()
    notifications = db.execute(
        select(Notification).where(Notification.user_id == trainee.user_id)
    ).scalars().all()
    read_events = db.execute(
        select(Event).where(
            Event.type == "READ_AUDIT",
            Event.actor_user_id == trainee.user_id,
        )
    ).scalars().all()

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": {
            "name": user.name if user else None,
            "email": user.email if user else None,
            "phone": trainee.phone,
            "district": trainee.district,
            "gender": trainee.gender,
            "enrolled_on": trainee.enrolled_on.isoformat(),
            "certified_on": trainee.certified_on.isoformat() if trainee.certified_on else None,
            "status": trainee.status.value,
        },
        "consents": [
            {
                "channel": consent.channel.value,
                "granted": consent.granted,
                "granted_at": consent.granted_at.isoformat() if consent.granted_at else None,
                "revoked_at": consent.revoked_at.isoformat() if consent.revoked_at else None,
                "version": consent.version,
                "purpose": consent.purpose_text,
            }
            for consent in consents
        ],
        "tracers": [
            {
                "milestone": followup.milestone.value,
                "channel": followup.channel.value,
                "state": followup.state.value,
                "due_on": followup.due_on.isoformat(),
                "attempts": followup.attempts,
                "sent_at": followup.sent_at.isoformat() if followup.sent_at else None,
                "response": followup.response_json,
            }
            for followup in followups
        ],
        "employment_records": [
            {
                "job_title": record.job_title,
                "monthly_wage": record.monthly_wage,
                "started_on": record.started_on.isoformat() if record.started_on else None,
                "ended_on": record.ended_on.isoformat() if record.ended_on else None,
                "employer_id": str(record.employer_id) if record.employer_id else None,
            }
            for record in employment
        ],
        "verifications": [
            {
                "trainee_signal": verification.trainee_signal.value,
                "employer_signal": verification.employer_signal.value,
                "verified": verification.verified,
            }
            for verification in verifications
        ],
        "notifications": [
            {"title": item.title, "body": item.body, "read": item.read}
            for item in notifications
        ],
        "audit_events_about_me": [
            {"type": event.type, "at": event.created_at.isoformat() if event.created_at else None}
            for event in read_events
        ],
    }


async def delete_my_data(db: Session, *, trainee: Trainee, user: User) -> dict:
    """Erase the account: profile, consents, tracers, claims, notifications.

    DPDP-aligned erasure right. Database foreign keys cascade the deletion of
    every child row; audit ``events`` rows survive with the actor reference
    nulled (SET NULL) so the audit trail stays complete without holding
    personal data. The erasure itself is audited BEFORE the rows go away.
    """
    counts = {
        "consents": 0,
        "tracers": 0,
        "employment_records": 0,
        "notifications": 0,
        "push_subscriptions": 0,
    }
    counts["consents"] = len(
        db.execute(select(Consent).where(Consent.trainee_id == trainee.id)).scalars().all()
    )
    counts["tracers"] = len(
        db.execute(select(FollowUp).where(FollowUp.trainee_id == trainee.id)).scalars().all()
    )
    counts["employment_records"] = len(
        db.execute(
            select(EmploymentRecord).where(EmploymentRecord.trainee_id == trainee.id)
        ).scalars().all()
    )
    counts["notifications"] = len(
        db.execute(
            select(Notification).where(Notification.user_id == trainee.user_id)
        ).scalars().all()
    )
    counts["push_subscriptions"] = len(
        db.execute(
            select(PushSubscription).where(PushSubscription.user_id == trainee.user_id)
        ).scalars().all()
    )

    await_publish = {
        "trainee_id": str(trainee.id),
        "erased_counts": counts,
    }

    # Delete children explicitly in dependency order (cascades exist, but an
    # explicit sweep keeps the counts honest and works across backends).
    db.execute(delete(PushSubscription).where(PushSubscription.user_id == trainee.user_id))
    db.execute(delete(Notification).where(Notification.user_id == trainee.user_id))
    verifications = db.execute(
        select(Verification.id).join(
            EmploymentRecord, Verification.employment_record_id == EmploymentRecord.id
        ).where(EmploymentRecord.trainee_id == trainee.id)
    ).scalars().all()
    if verifications:
        db.execute(delete(Verification).where(Verification.id.in_(verifications)))
    db.execute(
        delete(EmploymentRecord).where(EmploymentRecord.trainee_id == trainee.id)
    )
    db.execute(delete(FollowUp).where(FollowUp.trainee_id == trainee.id))
    db.execute(delete(Consent).where(Consent.trainee_id == trainee.id))

    # Audit BEFORE the identity disappears: actor id survives this commit only.
    await publish_event(
        db,
        event_type="TRAINEE_DATA_DELETED",
        actor_user_id=user.id,
        actor_role="TRAINEE",
        payload=await_publish,
        audience_roles=["ADMIN"],
    )

    trainee_ref = trainee.id
    user_email = user.email
    db.delete(trainee)
    db.delete(user)
    db.flush()
    logger.info(
        "Erased trainee %s (%s): %s", trainee_ref, user_email, counts
    )
    return {"status": "deleted", "erased": counts, "trainee_id": str(trainee_ref)}
