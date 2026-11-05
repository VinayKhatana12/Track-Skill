"""Admin domain services: state KPIs, PPI leaderboard, allocations, events."""

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.ai import skills as ai_skills
from app.core.config import get_settings
from app.core.constants import WORKING_STATUSES
from app.models import (
    EmploymentRecord,
    Event,
    FollowUp,
    FundAllocation,
    ProviderScore,
    ProviderStaff,
    Trainee,
    TrainingCentre,
    User,
    Verification,
)
from app.models.enums import FollowUpMilestone, FollowUpState, TraineeStatus
from app.services import ppi
from app.services.realtime import NotificationDraft, publish_event

logger = logging.getLogger(__name__)


def state_overview(db: Session) -> dict:
    """State-wide KPIs plus district heat data."""
    trainees = db.execute(select(Trainee)).scalars().all()
    trainee_ids = [trainee.id for trainee in trainees]
    records: list[EmploymentRecord] = []
    followups: list[FollowUp] = []
    if trainee_ids:
        records = list(
            db.execute(
                select(EmploymentRecord).where(EmploymentRecord.trainee_id.in_(trainee_ids))
            ).scalars()
        )
        followups = list(
            db.execute(select(FollowUp).where(FollowUp.trainee_id.in_(trainee_ids))).scalars()
        )
    verifications = db.execute(select(Verification)).scalars().all()
    signals_by_record = {
        verification.employment_record_id: (
            verification.trainee_signal,
            verification.employer_signal,
        )
        for verification in verifications
    }

    certified = [
        trainee
        for trainee in trainees
        if trainee.status is TraineeStatus.CERTIFIED and trainee.certified_on is not None
    ]
    record_by_trainee: dict[UUID, EmploymentRecord] = {}
    for record in records:
        record_by_trainee[record.trainee_id] = record

    weighted = 0.0
    working = 0
    self_employed = 0
    for trainee in certified:
        record = record_by_trainee.get(trainee.id)
        if record is None or record.status not in WORKING_STATUSES:
            continue
        working += 1
        if record.status.value == "SELF_EMPLOYED":
            self_employed += 1
        weighted += 1.0 if ppi.is_verified(signals_by_record.get(record.id)) else 0.5
    employment_rate = weighted / len(certified) if certified else 0.0
    self_employment_share = self_employed / working if working else 0.0

    today = datetime.now(UTC).date()
    retention: dict[str, float] = {}
    for milestone in (FollowUpMilestone.M3, FollowUpMilestone.M6, FollowUpMilestone.M12):
        responded = [
            followup
            for followup in followups
            if followup.milestone is milestone
            and followup.state is FollowUpState.RESPONDED
            and followup.due_on <= today
        ]
        still_working = [
            followup
            for followup in responded
            if (followup.response_json or {}).get("employment")
            in {status_value.value for status_value in WORKING_STATUSES}
        ]
        retention[milestone.value] = (
            round(len(still_working) / len(responded), 4) if responded else 0.0
        )

    wage_by_trainee: dict[UUID, dict[FollowUpMilestone, float]] = {}
    for followup in followups:
        if followup.state is not FollowUpState.RESPONDED:
            continue
        wage = (followup.response_json or {}).get("wage")
        if wage is None:
            continue
        wage_by_trainee.setdefault(followup.trainee_id, {})[followup.milestone] = float(wage)
    growths = []
    for milestones in wage_by_trainee.values():
        wage_3 = milestones.get(FollowUpMilestone.M3)
        wage_12 = milestones.get(FollowUpMilestone.M12)
        if wage_3 and wage_12:
            growths.append((wage_12 - wage_3) / wage_3)
    growths.sort()
    median_uplift = 0.0
    if growths:
        middle = len(growths) // 2
        median_uplift = (
            growths[middle]
            if len(growths) % 2
            else (growths[middle - 1] + growths[middle]) / 2
        )

    verification_rate = 0.0
    if verifications:
        verification_rate = (
            sum(ppi.is_verified(signals) for signals in signals_by_record.values())
            / len(verifications)
        )

    districts: dict[str, dict] = {}
    for trainee in trainees:
        entry = districts.setdefault(
            trainee.district,
            {"district": trainee.district, "trainees": 0, "certified": 0, "working": 0},
        )
        entry["trainees"] += 1
        if trainee in certified:
            entry["certified"] += 1
        record = record_by_trainee.get(trainee.id)
        if record is not None and record.status in WORKING_STATUSES:
            entry["working"] += 1
    district_rows = []
    for entry in districts.values():
        certified_count = entry["certified"]
        employment_rate = round(entry["working"] / certified_count, 4) if certified_count else 0.0
        district_rows.append({**entry, "employment_rate": employment_rate})
    district_rows.sort(key=lambda item: (-item["employment_rate"], item["district"]))

    return {
        "trainees": len(trainees),
        "certified": len(certified),
        "placed": working,
        "employment_rate": round(employment_rate, 4),
        "retention_3m": retention["M3"],
        "retention_6m": retention["M6"],
        "retention_12m": retention["M12"],
        "median_wage_uplift": round(median_uplift, 4),
        "self_employment_share": round(self_employment_share, 4),
        "verification_rate": round(verification_rate, 4),
        "districts": district_rows,
    }


async def create_allocation(
    db: Session, *, admin_user, centre_id: UUID, amount: float, rationale: str
) -> dict:
    """Record a fund allocation and notify the centre's staff live."""
    centre = db.get(TrainingCentre, centre_id)
    if centre is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found.")

    allocation = FundAllocation(
        id=uuid4(),
        centre_id=centre.id,
        amount=amount,
        rationale=rationale,
        decided_by=admin_user.id,
        decided_at=datetime.now(UTC),
    )
    db.add(allocation)
    db.flush()

    staff_user_ids = list(
        db.execute(
            select(ProviderStaff.user_id).where(ProviderStaff.centre_id == centre.id)
        ).scalars()
    )
    await publish_event(
        db,
        event_type="FUND_ALLOCATED",
        actor_user_id=admin_user.id,
        actor_role="ADMIN",
        payload={
            "allocation_id": str(allocation.id),
            "centre_id": str(centre.id),
            "amount": float(amount),
            "rationale": rationale,
        },
        audience_roles=["PROVIDER"],
        notifications=[
            NotificationDraft(
                user_id=user_id,
                title="Fund allocation decided",
                body=f"{centre.name} received an allocation of {amount:,.0f}. {rationale}",
                link="/dashboard/provider",
            )
            for user_id in staff_user_ids
        ],
    )
    logger.info("Allocation %s created", allocation.id)
    return {
        "allocation_id": str(allocation.id),
        "centre_id": str(centre.id),
        "amount": float(amount),
        "rationale": rationale,
    }


async def flag_provider(db: Session, *, admin_user, centre_id: UUID, reason: str) -> dict:
    centre = db.get(TrainingCentre, centre_id)
    if centre is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found.")

    staff_user_ids = list(
        db.execute(
            select(ProviderStaff.user_id).where(ProviderStaff.centre_id == centre.id)
        ).scalars()
    )
    payload = {"centre_id": str(centre.id), "centre_name": centre.name, "reason": reason}
    await publish_event(
        db,
        event_type="PROVIDER_FLAGGED",
        actor_user_id=admin_user.id,
        actor_role="ADMIN",
        payload=payload,
        audience_roles=["PROVIDER"],
        notifications=[
            NotificationDraft(
                user_id=user_id,
                title="Your centre was flagged by the mission",
                body=reason,
                link="/dashboard/provider",
            )
            for user_id in staff_user_ids
        ],
    )
    logger.info("Centre %s flagged", centre.id)
    return payload


def providers_leaderboard(db: Session) -> list[dict]:
    return ppi.rank_centres(db)


def provider_detail(db: Session, centre_id: UUID) -> dict:
    """Centre detail: fresh PPI components, score history and allocations."""
    centre = db.get(TrainingCentre, centre_id)
    if centre is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found.")
    metrics = ppi.compute_metrics(db, centre.id)
    scores = db.execute(
        select(ProviderScore)
        .where(ProviderScore.centre_id == centre.id)
        .order_by(ProviderScore.period)
    ).scalars().all()
    allocations = db.execute(
        select(FundAllocation)
        .where(FundAllocation.centre_id == centre.id)
        .order_by(FundAllocation.decided_at)
    ).scalars().all()
    staff = db.execute(
        select(User.name)
        .join(ProviderStaff, ProviderStaff.user_id == User.id)
        .where(ProviderStaff.centre_id == centre.id)
    ).scalars().all()

    return {
        "centre": {"id": str(centre.id), "name": centre.name, "district": centre.district},
        **metrics,
        "score_history": [
            {
                "period": score.period.isoformat(),
                "ppi_score": score.ppi_score,
                "placement_rate": score.placement_rate,
                "verification_rate": score.verification_rate,
            }
            for score in scores
        ],
        "allocations": [
            {
                "id": str(allocation.id),
                "amount": float(allocation.amount),
                "rationale": allocation.rationale,
                "decided_at": allocation.decided_at.isoformat() if allocation.decided_at else None,
            }
            for allocation in allocations
        ],
        "staff": list(staff),
    }


def events_feed(db: Session, limit: int = 50) -> list[dict]:
    events = db.execute(
        select(Event).order_by(Event.created_at.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": str(event.id),
            "type": event.type,
            "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
            "actor_role": event.actor_role,
            "payload": event.payload,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        for event in events
    ]


def curriculum_gaps(db: Session, limit: int = 10) -> list[dict]:
    return ai_skills.curriculum_gaps(db, limit=limit)


async def reset_demo_data(db: Session) -> dict:
    """DEMO_MODE only: wipe all domain tables and regenerate the seed."""

    import random

    from app.core.security import hash_password
    from app.seed import INGEST_ORDER, SeedIngestor, build_seed_data

    db.execute(
        sa_text(
            "TRUNCATE notifications, events, fund_allocations, provider_scores, "
            "market_demand, verifications, employment_records, followups, consents, "
            "trainees, courses, employers, provider_staff, training_centres, users, "
            "contact_messages RESTART IDENTITY CASCADE"
        )
    )

    settings = get_settings()
    rng = random.Random(20260401)
    password_hash = hash_password(settings.demo_password)
    data = build_seed_data(rng, password_hash)

    ingestor = SeedIngestor(db)
    for label, model in INGEST_ORDER:
        ingestor.ingest(label, model, data[label])
    db.flush()

    await publish_event(
        db,
        event_type="DEMO_RESET",
        actor_user_id=None,
        actor_role="SYSTEM",
        payload={"source": "admin-dashboard"},
        audience_roles=["ADMIN", "PROVIDER"],
    )
    user_count = db.execute(select(func.count()).select_from(User)).scalar_one()
    logger.info("Demo data reset: %s users restored", user_count)
    return {"status": "reset", "users": user_count}
