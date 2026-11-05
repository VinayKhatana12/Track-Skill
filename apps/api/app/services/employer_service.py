"""Employer domain services: verifications, hiring, talent pool."""

import logging
from datetime import date
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import anomalies
from app.core.constants import WORKING_STATUSES
from app.models import (
    Consent,
    Course,
    Employer,
    EmploymentRecord,
    FollowUp,
    MarketDemand,
    Trainee,
    User,
    Verification,
)
from app.models.enums import FollowUpMilestone, FollowUpState, TraineeStatus, VerificationSignal
from app.services import ppi
from app.services.realtime import NotificationDraft, publish_event

logger = logging.getLogger(__name__)


def own_employer(db: Session, user_id: UUID) -> Employer:
    employer = db.execute(
        select(Employer).where(Employer.user_id == user_id)
    ).scalar_one_or_none()
    if employer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employer profile is linked to this account yet.",
        )
    return employer


def pending_verifications(db: Session, employer: Employer) -> list[dict]:
    rows = db.execute(
        select(Verification, EmploymentRecord, Trainee, User)
        .join(EmploymentRecord, Verification.employment_record_id == EmploymentRecord.id)
        .join(Trainee, EmploymentRecord.trainee_id == Trainee.id)
        .join(User, Trainee.user_id == User.id)
        .where(
            EmploymentRecord.employer_id == employer.id,
            Verification.employer_signal == VerificationSignal.PENDING,
        )
        .order_by(Verification.created_at)
    ).all()
    return [
        {
            "verification_id": str(verification.id),
            "trainee_id": str(trainee.id),
            "trainee_name": user_row.name,
            "employment_status": record.status.value,
            "job_title": record.job_title,
            "monthly_wage": float(record.monthly_wage) if record.monthly_wage else None,
            "trainee_signal": verification.trainee_signal.value,
            "claimed_at": verification.created_at.isoformat() if verification.created_at else None,
        }
        for verification, record, trainee, user_row in rows
    ]


def _own_verification(db: Session, employer: Employer, verification_id: UUID) -> Verification:
    verification = db.get(Verification, verification_id)
    if verification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification not found.")
    record = db.get(EmploymentRecord, verification.employment_record_id)
    if record is None or record.employer_id != employer.id:
        # Do not reveal other employers' verifications.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification not found.")
    return verification


async def confirm_verification(
    db: Session, *, employer: Employer, verification_id: UUID
) -> dict:
    """Confirm a claim; when both signals agree the verification completes
    and the centre's PPI is recalculated live."""
    verification = _own_verification(db, employer, verification_id)
    if verification.employer_signal is not VerificationSignal.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This verification has already been processed.",
        )

    verification.employer_signal = VerificationSignal.CONFIRMED
    record = db.get(EmploymentRecord, verification.employment_record_id)
    trainee = db.get(Trainee, record.trainee_id)
    db.flush()

    # Statistical anomaly checks raise FLAG_RAISED events for Admin.
    await anomalies.check_employment_record(db, record)

    if ppi.is_verified((verification.trainee_signal, verification.employer_signal)):
        await publish_event(
            db,
            event_type="VERIFICATION_COMPLETE",
            actor_user_id=employer.user_id,
            actor_role="EMPLOYER",
            payload={
                "verification_id": str(verification.id),
                "trainee_id": str(trainee.id),
                "centre_id": str(trainee.centre_id),
            },
            audience_roles=["PROVIDER", "ADMIN"],
            audience_user_ids=[trainee.user_id],
            notifications=[
                NotificationDraft(
                    user_id=trainee.user_id,
                    title="Your employment is verified",
                    body=(
                        "Your employer confirmed your employment. "
                        "Your outcome now counts in full."
                    ),
                    link="/dashboard/trainee",
                )
            ],
        )
        score = ppi.recalculate_for_centre(db, trainee.centre_id)
        await publish_event(
            db,
            event_type="PPI_RECALCULATED",
            actor_user_id=employer.user_id,
            actor_role="EMPLOYER",
            payload={
                "centre_id": str(trainee.centre_id),
                "period": score.period.isoformat(),
                "ppi_score": score.ppi_score,
            },
            audience_roles=["PROVIDER", "ADMIN"],
        )
        completed = True
    else:
        await publish_event(
            db,
            event_type="VERIFICATION_EMPLOYER_CONFIRMED",
            actor_user_id=employer.user_id,
            actor_role="EMPLOYER",
            payload={
                "verification_id": str(verification.id),
                "trainee_id": str(trainee.id),
            },
            audience_roles=["PROVIDER"],
            audience_user_ids=[trainee.user_id],
        )
        completed = False

    logger.info("Verification %s confirmed (complete=%s)", verification.id, completed)
    return {
        "verification_id": str(verification.id),
        "trainee_signal": verification.trainee_signal.value,
        "employer_signal": verification.employer_signal.value,
        "verified": completed,
    }


async def dispute_verification(
    db: Session, *, employer: Employer, verification_id: UUID, reason: str
) -> dict:
    verification = _own_verification(db, employer, verification_id)
    if verification.employer_signal is not VerificationSignal.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This verification has already been processed.",
        )
    verification.employer_signal = VerificationSignal.DISPUTED
    record = db.get(EmploymentRecord, verification.employment_record_id)
    trainee = db.get(Trainee, record.trainee_id)
    db.flush()

    await publish_event(
        db,
        event_type="VERIFICATION_DISPUTED",
        actor_user_id=employer.user_id,
        actor_role="EMPLOYER",
        payload={
            "verification_id": str(verification.id),
            "trainee_id": str(trainee.id),
            "reason": reason,
        },
        audience_roles=["PROVIDER"],
        audience_user_ids=[trainee.user_id],
    )
    logger.info("Verification %s disputed", verification.id)
    return {
        "verification_id": str(verification.id),
        "employer_signal": verification.employer_signal.value,
    }


async def hire_trainee(
    db: Session,
    *,
    employer: Employer,
    trainee_id: UUID,
    job_title: str,
    monthly_wage: float,
    started_on: date | None,
) -> dict:
    """Employer-initiated employment record with the employer signal pre-confirmed."""
    trainee = db.get(Trainee, trainee_id)
    if trainee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trainee not found.")
    if trainee.status is not TraineeStatus.CERTIFIED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only certified trainees can be hired through the platform.",
        )
    existing = db.execute(
        select(EmploymentRecord.id).where(EmploymentRecord.trainee_id == trainee.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This trainee already has an employment record.",
        )

    record = EmploymentRecord(
        id=uuid4(),
        trainee_id=trainee.id,
        employer_id=employer.id,
        status=next(iter(WORKING_STATUSES)),
        job_title=job_title,
        monthly_wage=monthly_wage,
        started_on=started_on or date.today(),
    )
    verification = Verification(
        id=uuid4(),
        employment_record_id=record.id,
        trainee_signal=VerificationSignal.PENDING,
        employer_signal=VerificationSignal.CONFIRMED,
    )
    db.add_all([record, verification])
    db.flush()

    # Statistical anomaly checks raise FLAG_RAISED events for Admin.
    await anomalies.check_employment_record(db, record)
    await anomalies.check_employer_confirmation_volume(db, employer.id)

    await publish_event(
        db,
        event_type="EMPLOYER_HIRED",
        actor_user_id=employer.user_id,
        actor_role="EMPLOYER",
        payload={
            "trainee_id": str(trainee.id),
            "verification_id": str(verification.id),
            "job_title": job_title,
        },
        audience_roles=["PROVIDER"],
        audience_user_ids=[trainee.user_id],
        notifications=[
            NotificationDraft(
                user_id=trainee.user_id,
                title="Confirm your new job",
                body=(
                    f"{employer.company_name} recorded you as hired for {job_title}. "
                    "Confirm the claim in your next follow-up."
                ),
                link="/dashboard/trainee",
            )
        ],
    )
    logger.info("Employer %s hired trainee %s", employer.id, trainee.id)
    return {
        "trainee_id": str(trainee.id),
        "employment_record_id": str(record.id),
        "verification_id": str(verification.id),
    }


def talent_pool(
    db: Session,
    employer: Employer,
    skill_filter: str | None = None,
    district_filter: str | None = None,
) -> list[dict]:
    """Certified trainees with active consent, grouped by their skills.

    match_score blends the market demand for the skill with embedding
    similarity when a search term is given (light-NLP mode keeps it lexical).
    """
    rows = db.execute(
        select(Trainee, User, Course)
        .join(User, Trainee.user_id == User.id)
        .join(Course, Trainee.course_id == Course.id)
        .where(Trainee.status == TraineeStatus.CERTIFIED)
    ).all()
    consented_ids = set(
        db.execute(
            select(Consent.trainee_id).where(
                Consent.granted.is_(True), Consent.revoked_at.is_(None)
            )
        ).scalars()
    )

    pool: dict[str, dict] = {}
    for trainee, user, course in rows:
        if trainee.id not in consented_ids:
            continue
        if district_filter and trainee.district.lower() != district_filter.lower():
            continue
        for skill in course.skills or []:
            if skill_filter and skill_filter.lower() not in skill.lower():
                continue
            entry = pool.setdefault(
                skill,
                {"count": 0, "districts": set(), "names": []},
            )
            entry["count"] += 1
            entry["districts"].add(trainee.district)
            if len(entry["names"]) < 3:
                entry["names"].append(user.name)

    from app.ai.embedder import cosine, get_embedder

    demand_by_skill: dict[str, float] = {}
    months = db.execute(select(MarketDemand.month).distinct()).scalars().all()
    if months:
        latest = max(months)
        for row in db.execute(select(MarketDemand).where(MarketDemand.month == latest)).scalars():
            demand_by_skill[row.skill] = row.demand_score

    embedder = get_embedder()
    search_vector = (
        embedder.encode([skill_filter])[0] if skill_filter and skill_filter.strip() else None
    )

    results = []
    for skill, entry in pool.items():
        demand = demand_by_skill.get(skill, 40.0) / 100.0
        match = demand
        if search_vector is not None:
            skill_vector = embedder.encode([skill])[0]
            match = max(demand * 0.5, cosine(search_vector, skill_vector))
        results.append(
            {
                "skill": skill,
                "trainee_count": entry["count"],
                "districts": sorted(entry["districts"]),
                "trainee_names": entry["names"],
                "match_score": round(min(1.0, match), 2),
            }
        )
    results.sort(key=lambda item: (-item["match_score"], -item["trainee_count"], item["skill"]))
    return results


def impact(db: Session, employer: Employer) -> dict:
    """Retention and verification stats for this employer's hires."""
    records = db.execute(
        select(EmploymentRecord).where(EmploymentRecord.employer_id == employer.id)
    ).scalars().all()
    trainee_ids = [record.trainee_id for record in records]
    verifications = {}
    if trainee_ids:
        for verification in db.execute(
            select(Verification).where(Verification.employment_record_id.in_(
                [record.id for record in records]
            ))
        ).scalars():
            verifications[verification.employment_record_id] = (
                verification.trainee_signal,
                verification.employer_signal,
            )
    from app.services.ppi import is_verified

    verified_count = sum(is_verified(signals) for signals in verifications.values())
    working = [r for r in records if r.status in WORKING_STATUSES]

    followups: list = []
    if trainee_ids:
        followups = db.execute(
            select(FollowUp).where(FollowUp.trainee_id.in_(trainee_ids))
        ).scalars().all()
    retention = {}
    for milestone in (FollowUpMilestone.M3, FollowUpMilestone.M6, FollowUpMilestone.M12):
        responded = [
            f for f in followups
            if f.milestone is milestone and f.state is FollowUpState.RESPONDED
        ]
        still_working = [
            f for f in responded
            if (f.response_json or {}).get("employment")
            in {s.value for s in WORKING_STATUSES}
        ]
        retention[milestone.value] = (
            round(len(still_working) / len(responded), 4) if responded else 0.0
        )

    wages = [float(r.monthly_wage) for r in working if r.monthly_wage]
    avg_wage = round(sum(wages) / len(wages), 2) if wages else 0.0

    return {
        "hires": len(records),
        "verified_hires": verified_count,
        "working": len(working),
        "retention_3m": retention["M3"],
        "retention_6m": retention["M6"],
        "retention_12m": retention["M12"],
        "avg_monthly_wage": avg_wage,
    }
