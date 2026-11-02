"""Statistical anomaly flagging for outcome data.

Three explainable rules, each raising a ``FLAG_RAISED`` audit event for the
Admin audience (with deduplication so scanning twice never double-raises):

- WAGE_OUTLIER: a monthly wage below 35% or above 300% of the median wage
  for the same sector. A fixed band around the sector median is used on
  purpose — it is easy to explain to human reviewers at demo scale.
- IMPOSSIBLE_START_DATE: employment starting in the future, before the
  trainee enrolled, or more than 14 days before certification (a small
  grace period for retro-recorded data).
- EMPLOYER_CONFIRMATION_SPIKE: one employer confirming 5+ placements —
  the "same employer confirming many hires" pattern worth a manual look.

Record-level checks run automatically after employer confirm/hire; admins
can run a full scan via ``POST /admin/anomalies/scan``.
"""

import logging
import statistics
from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, EmploymentRecord, Event, Trainee, Verification
from app.models.enums import VerificationSignal
from app.services.realtime import publish_event

logger = logging.getLogger(__name__)

RULE_WAGE_OUTLIER = "WAGE_OUTLIER"
RULE_IMPOSSIBLE_START_DATE = "IMPOSSIBLE_START_DATE"
RULE_EMPLOYER_CONFIRMATION_SPIKE = "EMPLOYER_CONFIRMATION_SPIKE"

WAGE_LOW_FACTOR = 0.35
WAGE_HIGH_FACTOR = 3.0
START_DATE_GRACE_DAYS = 14
EMPLOYER_CONFIRMATION_THRESHOLD = 5


async def _publish_flag(
    db: Session,
    *,
    rule: str,
    severity: str,
    dedupe_key: str,
    summary: str,
    details: dict,
) -> bool:
    """Raise a FLAG_RAISED event unless the same flag was raised before."""
    existing = db.execute(
        select(Event.id).where(
            Event.type == "FLAG_RAISED",
            Event.payload["dedupe_key"].astext == dedupe_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False

    event_id = await publish_event(
        db,
        event_type="FLAG_RAISED",
        actor_user_id=None,
        actor_role="SYSTEM",
        payload={
            "rule": rule,
            "severity": severity,
            "dedupe_key": dedupe_key,
            "summary": summary,
            **details,
        },
        audience_roles=["ADMIN"],
    )
    logger.info("Raised %s (dedupe_key=%s, event %s)", rule, dedupe_key, event_id)
    return True


def _sector_wages(db: Session) -> dict[str, float]:
    """Median monthly wage per course sector."""
    rows = db.execute(
        select(EmploymentRecord.monthly_wage, Course.sector)
        .join(Trainee, EmploymentRecord.trainee_id == Trainee.id)
        .join(Course, Trainee.course_id == Course.id)
        .where(EmploymentRecord.monthly_wage.is_not(None))
    ).all()
    wages_by_sector: dict[str, list[float]] = defaultdict(list)
    for wage, sector in rows:
        if wage and wage > 0:
            wages_by_sector[sector].append(float(wage))
    return {
        sector: statistics.median(wages) for sector, wages in wages_by_sector.items() if wages
    }


def _sector_for_trainee(db: Session, trainee_id: UUID) -> str | None:
    trainee = db.get(Trainee, trainee_id)
    if trainee is None:
        return None
    course = db.get(Course, trainee.course_id)
    return course.sector if course else None


async def check_employment_record(db: Session, record: EmploymentRecord) -> list[str]:
    """Run the wage and start-date rules for one employment record."""
    raised: list[str] = []
    today = date.today()
    trainee = db.get(Trainee, record.trainee_id)

    # Wage outlier rule.
    if record.monthly_wage and record.monthly_wage > 0:
        sector = _sector_for_trainee(db, record.trainee_id)
        median = _sector_wages(db).get(sector or "", 0.0)
        if median > 0 and (
            record.monthly_wage < WAGE_LOW_FACTOR * median
            or record.monthly_wage > WAGE_HIGH_FACTOR * median
        ):
            key = f"{RULE_WAGE_OUTLIER}:{record.id}"
            if await _publish_flag(
                db,
                rule=RULE_WAGE_OUTLIER,
                severity="medium",
                dedupe_key=key,
                summary=(
                    f"Monthly wage {record.monthly_wage:,.0f} is far from the "
                    f"{sector} median ({median:,.0f})."
                ),
                details={
                    "employment_record_id": str(record.id),
                    "trainee_id": str(record.trainee_id),
                    "sector": sector,
                    "monthly_wage": float(record.monthly_wage),
                    "sector_median": median,
                },
            ):
                raised.append(RULE_WAGE_OUTLIER)

    # Impossible start date rule.
    problems: list[str] = []
    if record.started_on:
        if record.started_on > today:
            problems.append("start date is in the future")
        if trainee is not None and record.started_on < trainee.enrolled_on:
            problems.append("start date is before enrolment")
        if (
            trainee is not None
            and trainee.certified_on is not None
            and record.started_on < trainee.certified_on - timedelta(days=START_DATE_GRACE_DAYS)
        ):
            problems.append(
                f"start date precedes certification by more than {START_DATE_GRACE_DAYS} days"
            )
    if problems:
        key = f"{RULE_IMPOSSIBLE_START_DATE}:{record.id}"
        certified_on = trainee.certified_on if trainee else None
        if await _publish_flag(
            db,
            rule=RULE_IMPOSSIBLE_START_DATE,
            severity="high",
            dedupe_key=key,
            summary=f"Impossible start date: {'; '.join(problems)}.",
            details={
                "employment_record_id": str(record.id),
                "trainee_id": str(record.trainee_id),
                "started_on": record.started_on.isoformat() if record.started_on else None,
                "certified_on": certified_on.isoformat() if certified_on else None,
                "enrolled_on": trainee.enrolled_on.isoformat() if trainee else None,
                "problems": problems,
            },
        ):
            raised.append(RULE_IMPOSSIBLE_START_DATE)

    return raised


async def check_employer_confirmation_volume(db: Session, employer_id: UUID) -> list[str]:
    """Raise a flag when one employer confirms many placements."""
    confirmed_count = len(
        db.execute(
            select(Verification.id)
            .join(EmploymentRecord, Verification.employment_record_id == EmploymentRecord.id)
            .where(
                EmploymentRecord.employer_id == employer_id,
                Verification.employer_signal == VerificationSignal.CONFIRMED,
            )
        ).scalars().all()
    )
    raised: list[str] = []
    if confirmed_count >= EMPLOYER_CONFIRMATION_THRESHOLD:
        key = f"{RULE_EMPLOYER_CONFIRMATION_SPIKE}:{employer_id}:{confirmed_count}"
        if await _publish_flag(
            db,
            rule=RULE_EMPLOYER_CONFIRMATION_SPIKE,
            severity="medium",
            dedupe_key=key,
            summary=(
                f"Employer has {confirmed_count} confirmed placements "
                f"(threshold {EMPLOYER_CONFIRMATION_THRESHOLD}) — verify hiring pattern."
            ),
            details={
                "employer_id": str(employer_id),
                "confirmed_count": confirmed_count,
                "threshold": EMPLOYER_CONFIRMATION_THRESHOLD,
            },
        ):
            raised.append(RULE_EMPLOYER_CONFIRMATION_SPIKE)
    return raised


async def scan_all(db: Session) -> list[dict]:
    """Full scan across every employment record plus employer volumes."""
    raised: list[dict] = []
    records = db.execute(select(EmploymentRecord)).scalars().all()
    for record in records:
        for rule in await check_employment_record(db, record):
            raised.append({"rule": rule, "employment_record_id": str(record.id)})
    employer_ids = db.execute(
        select(EmploymentRecord.employer_id)
        .where(EmploymentRecord.employer_id.is_not(None))
        .distinct()
    ).scalars().all()
    for employer_id in employer_ids:
        for rule in await check_employer_confirmation_volume(db, employer_id):
            raised.append({"rule": rule, "employer_id": str(employer_id)})
    logger.info("Anomaly scan raised %s flag(s)", len(raised))
    return raised
