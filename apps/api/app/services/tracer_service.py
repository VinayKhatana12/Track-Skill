"""Tracer engine: creation, delivery, expiry, retries, demo fast-forward.

State machine (every transition publishes a realtime event):

    (created) --schedule--> SCHEDULED --send--> SENT --reply--> RESPONDED
                                   |              |
                                   +--max retries-+--> MISSED <--expiry--+

Consent rule (hard): tracers are created and sent ONLY for trainees with an
active consent row (granted, not revoked). Revoking consent cancels every
tracer that has not happened yet.

Delivery goes through a ChannelAdapter (simulated gateways in the demo);
failures retry with exponential backoff, up to tracer_max_attempts, then the
tracer is MISSED. A SENT tracer with no reply after tracer_expiry_days is
also MISSED.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.tracer_nlp import build_followup_message
from app.core.config import get_settings
from app.core.constants import MILESTONE_OFFSET_DAYS
from app.models import Consent, Course, FollowUp, Trainee, TrainingCentre, User
from app.models.enums import FollowUpState, TraineeStatus
from app.services.realtime import NotificationDraft, publish_event
from app.services.tracer_channels import get_adapter

logger = logging.getLogger(__name__)


# ── Consent-scoped scheduling (shared by certify / consent / scheduler) ──────


def has_active_consent(db: Session, trainee_id: UUID) -> bool:
    return (
        db.execute(
            select(Consent.id).where(
                Consent.trainee_id == trainee_id,
                Consent.granted.is_(True),
                Consent.revoked_at.is_(None),
            )
        ).first()
        is not None
    )


def active_channels(db: Session, trainee_id: UUID) -> list:
    return list(
        db.execute(
            select(Consent.channel).where(
                Consent.trainee_id == trainee_id,
                Consent.granted.is_(True),
                Consent.revoked_at.is_(None),
            )
        ).scalars()
    )


def cancel_pending_followups(db: Session, trainee_id: UUID) -> int:
    """Withdraw every tracer that has not happened yet (consent revoked)."""
    from sqlalchemy import delete

    result = db.execute(
        delete(FollowUp).where(
            FollowUp.trainee_id == trainee_id,
            FollowUp.state.in_([FollowUpState.SCHEDULED, FollowUpState.SENT]),
        )
    )
    return result.rowcount or 0


def schedule_missing_followups(db: Session, trainee: Trainee) -> int:
    """Create missing M3/M6/M12 tracers — only with active consent."""
    if trainee.status is not TraineeStatus.CERTIFIED or trainee.certified_on is None:
        return 0
    channels = active_channels(db, trainee.id)
    if not channels:
        return 0
    existing = set(
        db.execute(select(FollowUp.milestone).where(FollowUp.trainee_id == trainee.id)).scalars()
    )
    created = 0
    for milestone, offset in MILESTONE_OFFSET_DAYS.items():
        if milestone in existing:
            continue
        db.add(
            FollowUp(
                id=uuid4(),
                trainee_id=trainee.id,
                milestone=milestone,
                due_on=trainee.certified_on + timedelta(days=offset),
                channel=channels[0],
                state=FollowUpState.SCHEDULED,
            )
        )
        created += 1
    if created:
        db.flush()
    return created


# ── Scheduler jobs ───────────────────────────────────────────────────────────


async def create_due_followups(db: Session) -> int:
    """Scheduler sweep: create missing milestone tracers for certified
    trainees with active consent (consent rule enforced here too)."""
    created_total = 0
    certified = db.execute(
        select(Trainee).where(Trainee.status == TraineeStatus.CERTIFIED)
    ).scalars().all()
    for trainee in certified:
        before = set(
            db.execute(
                select(FollowUp.milestone).where(FollowUp.trainee_id == trainee.id)
            ).scalars()
        )
        created = schedule_missing_followups(db, trainee)
        if created:
            created_total += created
            after = set(
                db.execute(
                    select(FollowUp.milestone).where(FollowUp.trainee_id == trainee.id)
                ).scalars()
            )
            new_milestones = after - before
            await publish_event(
                db,
                event_type="TRACER_SCHEDULED",
                actor_user_id=None,
                actor_role="SYSTEM",
                payload={
                    "trainee_id": str(trainee.id),
                    "milestones": sorted(m.value for m in new_milestones),
                },
                audience_user_ids=[trainee.user_id],
                audience_roles=["PROVIDER"],
            )
    if created_total:
        db.flush()
    return created_total


async def send_due_followups(db: Session) -> list[dict]:
    """Send every SCHEDULED tracer that is due, honouring consent + retries."""
    settings = get_settings()
    today = date.today()
    now = datetime.now(UTC)

    rows = db.execute(
        select(FollowUp, Trainee, User)
        .join(Trainee, FollowUp.trainee_id == Trainee.id)
        .join(User, Trainee.user_id == User.id)
        .where(
            FollowUp.state == FollowUpState.SCHEDULED,
            FollowUp.due_on <= today,
        )
        .order_by(FollowUp.due_on)
    ).all()

    sent: list[dict] = []
    for followup, trainee, user in rows:
        # Consent rule: revoke-before-send means the tracer never goes out.
        if not has_active_consent(db, trainee.id):
            followup.state = FollowUpState.MISSED
            await publish_event(
                db,
                event_type="TRACER_MISSED",
                actor_user_id=None,
                actor_role="SYSTEM",
                payload={
                    "followup_id": str(followup.id),
                    "trainee_id": str(trainee.id),
                    "milestone": followup.milestone.value,
                    "reason": "consent_not_active",
                },
                audience_roles=["PROVIDER"],
                audience_user_ids=[trainee.user_id],
            )
            continue

        # Retry backoff: 2^(attempts-1) minutes between attempts.
        if followup.attempts > 0 and followup.updated_at is not None:
            backoff = timedelta(minutes=2 ** (followup.attempts - 1))
            if now - followup.updated_at < backoff:
                continue

        course = db.get(Course, trainee.course_id)
        centre = db.get(TrainingCentre, trainee.centre_id)
        message = build_followup_message(
            channel=followup.channel.value,
            trainee_name=user.name,
            course_title=course.title if course else "your course",
            milestone=followup.milestone.value,
            centre_name=centre.name if centre else "your training centre",
        )

        adapter = get_adapter(followup.channel.value)
        try:
            await adapter.send(to_user_id=user.id, to_phone=trainee.phone, message=message)
        except Exception as exc:
            followup.attempts += 1
            db.flush()
            if followup.attempts >= settings.tracer_max_attempts:
                followup.state = FollowUpState.MISSED
                db.flush()
                await publish_event(
                    db,
                    event_type="TRACER_MISSED",
                    actor_user_id=None,
                    actor_role="SYSTEM",
                    payload={
                        "followup_id": str(followup.id),
                        "trainee_id": str(trainee.id),
                        "milestone": followup.milestone.value,
                        "reason": "delivery_failed",
                        "attempts": followup.attempts,
                        "error": str(exc),
                    },
                    audience_roles=["PROVIDER"],
                    audience_user_ids=[trainee.user_id],
                )
            logger.warning(
                "Tracer %s delivery failed (attempt %s): %s",
                followup.id,
                followup.attempts,
                exc,
            )
            continue

        followup.state = FollowUpState.SENT
        followup.sent_at = now
        followup.attempts += 1
        db.flush()
        await publish_event(
            db,
            event_type="TRACER_SENT",
            actor_user_id=None,
            actor_role="SYSTEM",
            payload={
                "followup_id": str(followup.id),
                "trainee_id": str(trainee.id),
                "milestone": followup.milestone.value,
                "channel": followup.channel.value,
                "message": message,
                "due_on": followup.due_on.isoformat(),
            },
            audience_user_ids=[trainee.user_id],
            audience_roles=["PROVIDER"],
            notifications=[
                NotificationDraft(
                    user_id=trainee.user_id,
                    title=f"{followup.milestone.value} follow-up via {followup.channel.value}",
                    body=message,
                    link="/dashboard/trainee",
                )
            ],
        )
        sent.append(
            {
                "followup_id": str(followup.id),
                "trainee_id": str(trainee.id),
                "trainee_name": user.name,
                "milestone": followup.milestone.value,
                "channel": followup.channel.value,
            }
        )
    return sent


async def expire_overdue_followups(db: Session) -> list[dict]:
    """SENT tracers with no reply after the expiry window become MISSED."""
    settings = get_settings()
    expiry_days = settings.tracer_expiry_days
    rows = db.execute(
        select(FollowUp, Trainee)
        .join(Trainee, FollowUp.trainee_id == Trainee.id)
        .where(
            FollowUp.state == FollowUpState.SENT,
            FollowUp.due_on < date.today() - timedelta(days=expiry_days),
        )
    ).all()
    missed: list[dict] = []
    for followup, trainee in rows:
        followup.state = FollowUpState.MISSED
        db.flush()
        await publish_event(
            db,
            event_type="TRACER_MISSED",
            actor_user_id=None,
            actor_role="SYSTEM",
            payload={
                "followup_id": str(followup.id),
                "trainee_id": str(trainee.id),
                "milestone": followup.milestone.value,
                "reason": "no_response",
                "expiry_days": expiry_days,
            },
            audience_roles=["PROVIDER"],
            audience_user_ids=[trainee.user_id],
        )
        missed.append({"followup_id": str(followup.id), "milestone": followup.milestone.value})
    return missed


async def run_tracer_cycle(db: Session) -> dict:
    """One scheduler tick: create, send, expire."""
    created = await create_due_followups(db)
    sent = await send_due_followups(db)
    missed = await expire_overdue_followups(db)
    return {"created": created, "sent": sent, "missed": missed}


# ── Demo fast-forward (Admin, DEMO_MODE only) ────────────────────────────────


async def run_tracer_now(db: Session) -> dict:
    """Demo control: pull every demo SCHEDULED tracer to today, create any
    missing ones for demo trainees, then run a full cycle immediately."""
    demo_trainee_ids = list(
        db.execute(
            select(Trainee.id).join(User, Trainee.user_id == User.id).where(User.is_demo.is_(True))
        ).scalars()
    )
    today = date.today()
    fast_forwarded = 0
    if demo_trainee_ids:
        scheduled = db.execute(
            select(FollowUp).where(
                FollowUp.trainee_id.in_(demo_trainee_ids),
                FollowUp.state == FollowUpState.SCHEDULED,
                FollowUp.due_on > today,
            )
        ).scalars().all()
        for followup in scheduled:
            followup.due_on = today
            fast_forwarded += 1
        if fast_forwarded:
            db.flush()

    created = await create_due_followups(db)
    # Freshly created tracers for demo trainees are also pulled to today so
    # they are delivered by this run.
    if demo_trainee_ids:
        scheduled = db.execute(
            select(FollowUp).where(
                FollowUp.trainee_id.in_(demo_trainee_ids),
                FollowUp.state == FollowUpState.SCHEDULED,
                FollowUp.due_on > today,
            )
        ).scalars().all()
        for followup in scheduled:
            followup.due_on = today
            fast_forwarded += 1
        if fast_forwarded:
            db.flush()

    sent = await send_due_followups(db)
    missed = await expire_overdue_followups(db)
    return {
        "fast_forwarded": fast_forwarded,
        "created": created,
        "sent": sent,
        "missed": missed,
        "sent_count": len(sent),
        "missed_count": len(missed),
    }


# ── Trainee chat view ────────────────────────────────────────────────────────


def get_trainee_messages(db: Session, trainee: Trainee) -> list[dict]:
    """Every tracer as a chat/call item for the trainee dashboard."""
    user = db.get(User, trainee.user_id)
    course = db.get(Course, trainee.course_id)
    centre = db.get(TrainingCentre, trainee.centre_id)
    followups = db.execute(
        select(FollowUp).where(FollowUp.trainee_id == trainee.id).order_by(FollowUp.due_on)
    ).scalars().all()

    messages: list[dict] = []
    for followup in followups:
        response_json = followup.response_json or {}
        messages.append(
            {
                "followup_id": str(followup.id),
                "milestone": followup.milestone.value,
                "channel": followup.channel.value,
                "kind": "call" if followup.channel.value == "IVR" else "chat",
                "state": followup.state.value,
                "due_on": followup.due_on.isoformat(),
                "sent_at": followup.sent_at.isoformat() if followup.sent_at else None,
                "attempts": followup.attempts,
                "message": build_followup_message(
                    channel=followup.channel.value,
                    trainee_name=user.name if user else "Trainee",
                    course_title=course.title if course else "your course",
                    milestone=followup.milestone.value,
                    centre_name=centre.name if centre else "your training centre",
                ),
                "responded": followup.state is FollowUpState.RESPONDED,
                "needs_review": bool(response_json.get("needs_review")),
                "response": {
                    "employment": response_json.get("employment"),
                    "job_title": response_json.get("job_title"),
                    "wage": response_json.get("wage"),
                    "raw_text": response_json.get("raw_text"),
                }
                if followup.state is FollowUpState.RESPONDED
                else None,
            }
        )
    return messages
