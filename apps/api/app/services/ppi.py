"""Provider Performance Index (PPI) computation and live recalculation.

Formula (documented in README and enforced here):

    PPI = 100 x (0.30 * placement_rate + 0.25 * retention_weighted
                 + 0.20 * wage_growth_norm + 0.15 * verification_rate
                 + 0.10 * response_rate)

    retention_weighted = 0.2 * R3 + 0.3 * R6 + 0.5 * R12

Business rules baked into the numbers:
- Unverified outcomes count at reduced weight in analytics: a placement whose
  dual-signal verification is not (CONFIRMED, CONFIRMED) contributes 0.5
  instead of 1.0 to placement_rate.
- wage_growth_norm: median relative wage growth between the M3 and M12
  follow-up responses, clamped at 50% growth.
- response_rate: responded / (responded + missed) among past-due follow-ups.
"""

import statistics
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import WORKING_STATUSES
from app.models import (
    EmploymentRecord,
    FollowUp,
    ProviderScore,
    Trainee,
    TrainingCentre,
    Verification,
)
from app.models.enums import (
    FollowUpMilestone,
    FollowUpState,
    TraineeStatus,
    VerificationSignal,
)

PPI_WEIGHTS = {
    "placement": 0.30,
    "retention": 0.25,
    "wage_growth": 0.20,
    "verification": 0.15,
    "response": 0.10,
}
RETENTION_WEIGHTS = {
    FollowUpMilestone.M3: 0.2,
    FollowUpMilestone.M6: 0.3,
    FollowUpMilestone.M12: 0.5,
}
WAGE_GROWTH_CAP = 0.5
UNVERIFIED_PLACEMENT_WEIGHT = 0.5

CONFIRMED_PAIR = (VerificationSignal.CONFIRMED, VerificationSignal.CONFIRMED)


def is_verified(signals: tuple[VerificationSignal, VerificationSignal] | None) -> bool:
    """Dual-signal rule: verified only when both signals are CONFIRMED."""
    return signals is not None and tuple(signals) == CONFIRMED_PAIR


def current_period(today: date | None = None) -> date:
    today = today or date.today()
    return date(today.year, today.month, 1)


def compute_metrics(db: Session, centre_id: UUID) -> dict:
    """Compute every PPI component for a centre from current data."""
    today = date.today()
    trainees = db.execute(select(Trainee).where(Trainee.centre_id == centre_id)).scalars().all()
    trainee_ids = [trainee.id for trainee in trainees]

    record_by_trainee: dict[UUID, EmploymentRecord] = {}
    followups: list[FollowUp] = []
    if trainee_ids:
        for record in db.execute(
            select(EmploymentRecord).where(EmploymentRecord.trainee_id.in_(trainee_ids))
        ).scalars():
            keep = record_by_trainee.get(record.trainee_id)
            if keep is None or (record.updated_at or record.created_at) >= (
                keep.updated_at or keep.created_at
            ):
                record_by_trainee[record.trainee_id] = record
        followups = list(
            db.execute(select(FollowUp).where(FollowUp.trainee_id.in_(trainee_ids))).scalars()
        )

    verification_by_record: dict[UUID, tuple[VerificationSignal, VerificationSignal]] = {}
    record_ids = [record.id for record in record_by_trainee.values()]
    if record_ids:
        for verification in db.execute(
            select(Verification).where(Verification.employment_record_id.in_(record_ids))
        ).scalars():
            verification_by_record[verification.employment_record_id] = (
                verification.trainee_signal,
                verification.employer_signal,
            )

    certified = [
        trainee
        for trainee in trainees
        if trainee.status is TraineeStatus.CERTIFIED and trainee.certified_on is not None
    ]

    # Placement: verified outcomes full weight, unverified at reduced weight.
    placement_weight = 0.0
    placements = 0
    for trainee in certified:
        record = record_by_trainee.get(trainee.id)
        if record is not None and record.status in WORKING_STATUSES:
            placements += 1
            placement_weight += (
                1.0
                if is_verified(verification_by_record.get(record.id))
                else UNVERIFIED_PLACEMENT_WEIGHT
            )
    placement_rate = placement_weight / len(certified) if certified else 0.0

    # Retention at each milestone (responded, past-due follow-ups).
    retention: dict[FollowUpMilestone, float] = {}
    for milestone in RETENTION_WEIGHTS:
        responded = [
            followup
            for followup in followups
            if followup.milestone is milestone
            and followup.state is FollowUpState.RESPONDED
            and followup.due_on <= today
        ]
        working = [
            followup
            for followup in responded
            if (followup.response_json or {}).get("employment")
            in {status.value for status in WORKING_STATUSES}
        ]
        retention[milestone] = len(working) / len(responded) if responded else 0.0
    retention_weighted = sum(
        RETENTION_WEIGHTS[milestone] * retention[milestone] for milestone in RETENTION_WEIGHTS
    )

    # Response rate among past-due follow-ups.
    responded_past = [
        followup
        for followup in followups
        if followup.state is FollowUpState.RESPONDED and followup.due_on <= today
    ]
    missed_past = [
        followup
        for followup in followups
        if followup.state is FollowUpState.MISSED and followup.due_on <= today
    ]
    response_rate = len(responded_past) / max(1, len(responded_past) + len(missed_past))

    # Wage growth between M3 and M12 responses.
    wage_by_trainee: dict[UUID, dict[FollowUpMilestone, float]] = {}
    for followup in responded_past:
        wage = (followup.response_json or {}).get("wage")
        if wage is None:
            continue
        wage_by_trainee.setdefault(followup.trainee_id, {})[followup.milestone] = float(wage)
    growths = []
    for milestones in wage_by_trainee.values():
        wage_3 = milestones.get(FollowUpMilestone.M3)
        wage_12 = milestones.get(FollowUpMilestone.M12)
        if wage_3 and wage_12:
            growths.append(min(max((wage_12 - wage_3) / wage_3, -0.5), 1.5))
    median_growth = statistics.median(growths) if growths else 0.0
    wage_growth_norm = max(0.0, min(median_growth / WAGE_GROWTH_CAP, 1.0))

    # Verification rate (dual-signal).
    verification_rate = 0.0
    if verification_by_record:
        verification_rate = sum(
            is_verified(signals) for signals in verification_by_record.values()
        ) / len(verification_by_record)

    ppi = 100 * (
        PPI_WEIGHTS["placement"] * placement_rate
        + PPI_WEIGHTS["retention"] * retention_weighted
        + PPI_WEIGHTS["wage_growth"] * wage_growth_norm
        + PPI_WEIGHTS["verification"] * verification_rate
        + PPI_WEIGHTS["response"] * response_rate
    )

    return {
        "enrolled": sum(1 for trainee in trainees if trainee.status is TraineeStatus.ENROLLED),
        "certified": len(certified),
        "dropped": sum(1 for trainee in trainees if trainee.status is TraineeStatus.DROPPED),
        "placements": placements,
        "placement_rate": round(placement_rate, 4),
        "retention_3m": round(retention[FollowUpMilestone.M3], 4),
        "retention_6m": round(retention[FollowUpMilestone.M6], 4),
        "retention_12m": round(retention[FollowUpMilestone.M12], 4),
        "retention_weighted": round(retention_weighted, 4),
        "wage_growth": round(median_growth, 4),
        "wage_growth_norm": round(wage_growth_norm, 4),
        "verification_rate": round(verification_rate, 4),
        "response_rate": round(response_rate, 4),
        "ppi_score": round(ppi, 2),
    }


def recalculate_for_centre(db: Session, centre_id: UUID) -> ProviderScore:
    """Recompute the PPI and upsert the current monthly period row."""
    metrics = compute_metrics(db, centre_id)
    period = current_period()
    row = db.execute(
        select(ProviderScore).where(
            ProviderScore.centre_id == centre_id, ProviderScore.period == period
        )
    ).scalar_one_or_none()
    if row is None:
        row = ProviderScore(id=uuid4(), centre_id=centre_id, period=period)
    row.placement_rate = metrics["placement_rate"]
    row.retention_3m = metrics["retention_3m"]
    row.retention_6m = metrics["retention_6m"]
    row.retention_12m = metrics["retention_12m"]
    row.wage_growth = metrics["wage_growth"]
    row.verification_rate = metrics["verification_rate"]
    row.ppi_score = metrics["ppi_score"]
    db.add(row)
    db.flush()
    return row


def rank_centres(db: Session) -> list[dict]:
    """Fresh PPI for every centre, ranked best-first (read-only)."""
    centres = db.execute(select(TrainingCentre).order_by(TrainingCentre.name)).scalars().all()
    ranked = []
    for centre in centres:
        metrics = compute_metrics(db, centre.id)
        ranked.append(
            {
                "centre_id": str(centre.id),
                "centre_name": centre.name,
                "district": centre.district,
                **metrics,
            }
        )
    ranked.sort(key=lambda item: item["ppi_score"], reverse=True)
    for position, item in enumerate(ranked, start=1):
        item["rank"] = position
    return ranked
