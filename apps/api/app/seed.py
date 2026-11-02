"""Seed entrypoint for TrackSkill AI demo data.

Idempotent by construction: every entity gets a deterministic UUID
(uuid5 of a fixed namespace plus a stable key) and rows whose id already
exists are skipped, so running the seed any number of times never
duplicates data.

Prerequisite: the schema must exist first (`alembic upgrade head`).

Run with:
    python -m app.seed        # or `make seed` when the stack is up

All names, districts and employers are fictional.
"""

from __future__ import annotations

import logging
import math
import random
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import (
    CONSENT_PURPOSE,
    CONSENT_VERSION,
    MILESTONE_OFFSET_DAYS,
    WORKING_STATUSES,
)
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import (
    Consent,
    Course,
    Employer,
    EmploymentRecord,
    Event,
    FollowUp,
    FundAllocation,
    MarketDemand,
    Notification,
    ProviderScore,
    ProviderStaff,
    Trainee,
    TrainingCentre,
    User,
    Verification,
)
from app.models.enums import (
    ConsentChannel,
    EmploymentStatus,
    FollowUpMilestone,
    FollowUpState,
    TraineeStatus,
    UserRole,
    VerificationSignal,
)

logger = logging.getLogger(__name__)

# ── Seed configuration ────────────────────────────────────────────────────────

SEED_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://trackskill-ai.demo/seed")
RNG_SEED = 20260401
STATE_NAME = "Demo State"

# Headline demo accounts (password comes from settings.demo_password).
DEMO_ADMIN_EMAIL = "admin.demo@trackskill.in"
DEMO_PROVIDER_EMAIL = "provider.demo@trackskill.in"
DEMO_TRAINEE_EMAIL = "trainee.demo@trackskill.in"
DEMO_EMPLOYER_EMAIL = "employer.demo@trackskill.in"
# The demo trainee is certified this many days ago, so their 3-month
# follow-up lands within days ("milestones due").
DEMO_TRAINEE_CERTIFIED_DAYS_AGO = 85
TRAINEE_COUNT = 300
EMPLOYER_COUNT = 12
MARKET_MONTHS = 12
SCORE_PERIODS = 3

DISTRICTS = [
    "North District",
    "Riverside District",
    "Harbour District",
    "Greenfield District",
    "Hillcrest District",
    "Lakeview District",
    "Meadow District",
    "Central District",
]

# (skill, popularity weight 0..1) per sector — the demand signal universe.
SECTOR_SKILLS: dict[str, list[tuple[str, float]]] = {
    "Information Technology": [
        ("Web Development", 0.9),
        ("Data Entry", 0.55),
        ("Cloud Support", 0.7),
    ],
    "Healthcare": [("Patient Care", 0.85), ("Phlebotomy", 0.6), ("Medical Billing", 0.5)],
    "Construction": [("Masonry", 0.5), ("Bar Bending", 0.45), ("Surveying", 0.4)],
    "Retail": [("Sales Operations", 0.75), ("Inventory Management", 0.6)],
    "Textiles": [("Stitching", 0.65), ("Quality Inspection", 0.45)],
    "Green Energy": [("Solar Installation", 0.8), ("Electrical Wiring", 0.7)],
}
SECTORS = list(SECTOR_SKILLS)

# (title, NSQF level, duration in weeks, taught skills) per sector.
COURSE_CATALOGUE: dict[str, list[tuple[str, int, int, list[str]]]] = {
    "Information Technology": [
        ("Web Development Associate", 4, 24, ["HTML", "CSS", "JavaScript", "Git"]),
        ("Front-End Development", 4, 20, ["React", "JavaScript", "Responsive Design"]),
        ("Data Entry and Office Productivity", 3, 12, ["Typing", "Spreadsheets", "Data Entry"]),
        ("Cloud Support Assistant", 4, 16, ["Linux", "Networking", "Cloud Support"]),
    ],
    "Healthcare": [
        ("Nursing Assistant", 4, 26, ["Patient Care", "Vital Monitoring", "First Aid"]),
        ("Phlebotomy Technician", 4, 18, ["Phlebotomy", "Lab Safety", "Specimen Handling"]),
        (
            "Medical Billing Assistant",
            3,
            14,
            ["Medical Billing", "Medical Coding", "Records Management"],
        ),
    ],
    "Construction": [
        ("Masonry and Tile Work", 3, 16, ["Masonry", "Tiling", "Site Safety"]),
        (
            "Bar Bending and Steel Fixing",
            3,
            14,
            ["Bar Bending", "Reinforcement", "Blueprint Reading"],
        ),
        ("Land Surveying Assistant", 4, 20, ["Surveying", "Total Station", "Leveling"]),
    ],
    "Retail": [
        ("Retail Sales Associate", 3, 12, ["Sales Operations", "POS Operations", "Merchandising"]),
        (
            "Warehouse and Inventory Assistant",
            3,
            14,
            ["Inventory Management", "Barcode Systems", "Packing"],
        ),
        (
            "Customer Support Associate",
            3,
            10,
            ["Customer Service", "Complaint Handling", "CRM Software"],
        ),
    ],
    "Textiles": [
        (
            "Garment Stitching Operator",
            3,
            16,
            ["Stitching", "Machine Operation", "Fabric Handling"],
        ),
        (
            "Quality Inspection Assistant",
            3,
            12,
            ["Quality Inspection", "Defect Analysis", "Reporting"],
        ),
        (
            "Fabric Printing Assistant",
            3,
            12,
            ["Textile Printing", "Colour Matching", "Machine Operation"],
        ),
    ],
    "Green Energy": [
        (
            "Solar Panel Installation Technician",
            4,
            18,
            ["Solar Installation", "Electrical Wiring", "Roof Safety"],
        ),
        (
            "Home Energy Audit Assistant",
            3,
            12,
            ["Energy Auditing", "Electrical Wiring", "Reporting"],
        ),
        (
            "Battery Storage Systems Assistant",
            4,
            14,
            ["Battery Systems", "Electrical Wiring", "Safety Compliance"],
        ),
    ],
}

SECTOR_WAGES: dict[str, tuple[int, int]] = {
    "Information Technology": (16000, 34000),
    "Healthcare": (13000, 26000),
    "Construction": (12000, 24000),
    "Retail": (10000, 20000),
    "Textiles": (10000, 18000),
    "Green Energy": (14000, 28000),
}

EMPLOYER_COMPANIES: list[tuple[str, str]] = [
    ("Riverside InfoTech Services", "Information Technology"),
    ("Central Data Services", "Information Technology"),
    ("HarbourCare Health Network", "Healthcare"),
    ("Lakeview Diagnostics", "Healthcare"),
    ("GreenBuild Construction Co.", "Construction"),
    ("Hillcrest Infra Works", "Construction"),
    ("MetroMart Retail", "Retail"),
    ("Northline Mart", "Retail"),
    ("StitchWell Textiles", "Textiles"),
    ("Meadow Apparel Works", "Textiles"),
    ("SolarisGreen Energy", "Green Energy"),
    ("Hillcrest Solar Solutions", "Green Energy"),
]

FIRST_NAMES = [
    "Aarav", "Aditi", "Amit", "Ananya", "Bhavana", "Dev", "Diya", "Farhan", "Gauri",
    "Ishaan", "Kavya", "Kiran", "Manav", "Meera", "Nikhil", "Nisha", "Pranav", "Priya",
    "Rahul", "Riya", "Sanjay", "Sneha", "Tanvi", "Vikram",
]
LAST_NAMES = [
    "Sharma", "Patel", "Mehta", "Iyer", "Nair", "Reddy", "Rao", "Joshi", "Kulkarni",
    "Das", "Bose", "Chauhan", "Verma", "Mishra", "Kapoor", "Bhatt", "Pillai", "Menon",
    "Sinha", "Gupta", "Naik", "Deshpande", "Kaur", "Sethi",
]

RESPONSE_NOTES = [
    "Confirmed current employment.",
    "Shared wage details over the tracer.",
    "Requested a callback next week.",
    "Reported a change of job.",
    "Enrolled in further study.",
]

CONSENT_CHANCES: dict[ConsentChannel, float] = {
    ConsentChannel.WHATSAPP: 0.85,
    ConsentChannel.IVR: 0.60,
    ConsentChannel.SMS: 0.35,
}
RESPONSE_RATE_BY_MILESTONE = {
    FollowUpMilestone.M3: 0.78,
    FollowUpMilestone.M6: 0.72,
    FollowUpMilestone.M12: 0.66,
}
WORKING_RATE_BY_MILESTONE = {
    FollowUpMilestone.M3: 0.72,
    FollowUpMilestone.M6: 0.66,
    FollowUpMilestone.M12: 0.60,
}

INGEST_ORDER: list[tuple[str, type]] = [
    ("users", User),
    ("training_centres", TrainingCentre),
    ("provider_staff", ProviderStaff),
    ("courses", Course),
    ("employers", Employer),
    ("trainees", Trainee),
    ("consents", Consent),
    ("employment_records", EmploymentRecord),
    ("verifications", Verification),
    ("followups", FollowUp),
    ("market_demand", MarketDemand),
    ("provider_scores", ProviderScore),
    ("fund_allocations", FundAllocation),
    ("events", Event),
    ("notifications", Notification),
]

# ── Small helpers ─────────────────────────────────────────────────────────────


def sid(kind: str, key: str) -> uuid.UUID:
    """Deterministic UUID for a seed entity, so re-runs never duplicate."""
    return uuid.uuid5(SEED_NAMESPACE, f"{kind}/{key}")


def slug(text: str) -> str:
    return text.lower().replace(" ", "-")


def utc(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, time(hour, 0), tzinfo=UTC)


def month_starts(count: int) -> list[date]:
    """The last `count` month starts, oldest first."""
    today = date.today()
    year, month = today.year, today.month
    starts: list[date] = []
    for _ in range(count):
        starts.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(starts))


class SeedIngestor:
    """Inserts only rows whose deterministic id is not present yet."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.summary: list[tuple[str, int, int]] = []

    def ingest(self, label: str, model: type, entities: list) -> None:
        if entities:
            existing = set(self.session.execute(select(model.id)).scalars())
            fresh = [entity for entity in entities if entity.id not in existing]
            self.session.add_all(fresh)
            self.summary.append((label, len(fresh), len(entities) - len(fresh)))
        else:
            self.summary.append((label, 0, 0))

    def print_summary(self) -> None:
        print("\nSeed summary (idempotent — existing rows are skipped)")
        for label, inserted, kept in self.summary:
            print(f"  {label:<20} inserted {inserted:>5}   already present {kept:>5}")


# ── Entity builders ───────────────────────────────────────────────────────────


def _followup_response(
    rng: random.Random, sector: str, milestone: FollowUpMilestone, channel: ConsentChannel
) -> dict:
    """A simulated tracer response (the WhatsApp/IVR simulated payload)."""
    working = rng.random() < WORKING_RATE_BY_MILESTONE[milestone]
    if working:
        employment = (
            EmploymentStatus.EMPLOYED if rng.random() < 0.8 else EmploymentStatus.SELF_EMPLOYED
        )
        low, high = SECTOR_WAGES[sector]
        wage: int | None = int(round(rng.uniform(low, high) / 100) * 100)
    else:
        employment = (
            EmploymentStatus.UNEMPLOYED if rng.random() < 0.7 else EmploymentStatus.FURTHER_STUDY
        )
        wage = None
    return {
        "employment": employment.value,
        "wage": wage,
        "channel": channel.value.lower(),
        "notes": rng.choice(RESPONSE_NOTES),
    }


def build_seed_data(rng: random.Random, password_hash: str) -> dict[str, list]:
    today = date.today()
    demo_trainee_user: User | None = None
    demo_employer_user: User | None = None

    # Users: admin, provider staff, employers, trainees ------------------------
    admin = User(
        id=sid("user", "admin"),
        name="Mission Admin",
        email=DEMO_ADMIN_EMAIL,
        password_hash=password_hash,
        role=UserRole.ADMIN,
        is_demo=True,
        is_active=True,
    )

    centres: list[TrainingCentre] = []
    for index, district in enumerate(DISTRICTS):
        centres.append(
            TrainingCentre(
                id=sid("centre", slug(district)),
                code=f"TC-{index + 1:02d}",
                name=f"{district} Skill Centre",
                district=district,
                state=STATE_NAME,
                sector_focus=SECTORS[index % len(SECTORS)],
                funding_status=rng.choice(
                    ["FULLY_FUNDED", "PARTIALLY_FUNDED", "FULLY_FUNDED", "UNFUNDED"]
                ),
            )
        )

    staff_users: list[User] = []
    staff_links: list[ProviderStaff] = []
    for staff_number, centre in enumerate([c for c in centres for _ in (1, 2)], start=1):
        email = (
            DEMO_PROVIDER_EMAIL
            if staff_number == 1
            else f"provider-{staff_number:02d}@trackskill.in"
        )
        user = User(
            id=sid("user", f"staff-{staff_number:02d}"),
            name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            email=email,
            password_hash=password_hash,
            role=UserRole.PROVIDER,
            is_demo=True,
            is_active=True,
        )
        staff_users.append(user)
        staff_links.append(
            ProviderStaff(
                id=sid("staff-link", f"{staff_number:02d}"),
                user_id=user.id,
                centre_id=centre.id,
            )
        )
    demo_provider_user = staff_users[0]

    employer_users: list[User] = []
    employers: list[Employer] = []
    employers_by_sector: dict[str, list[Employer]] = defaultdict(list)
    for index, (company, sector) in enumerate(EMPLOYER_COMPANIES, start=1):
        email = (
            DEMO_EMPLOYER_EMAIL
            if index == 1
            else f"employer-{index:02d}@trackskill.in"
        )
        user = User(
            id=sid("user", f"employer-{index:02d}"),
            name=f"{company} Recruiter",
            email=email,
            password_hash=password_hash,
            role=UserRole.EMPLOYER,
            is_demo=True,
            is_active=True,
        )
        employer_users.append(user)
        employer = Employer(
            id=sid("employer", slug(company)),
            user_id=user.id,
            company_name=company,
            sector=sector,
            district=DISTRICTS[index % len(DISTRICTS)],
        )
        employers.append(employer)
        employers_by_sector[sector].append(employer)
    demo_employer_user = employer_users[0]

    courses: list[Course] = []
    courses_by_centre: dict[uuid.UUID, list[Course]] = defaultdict(list)
    for centre in centres:
        catalogue = COURSE_CATALOGUE[centre.sector_focus]
        picked = rng.sample(catalogue, k=min(3 if rng.random() < 0.75 else 4, len(catalogue)))
        for title, nsqf, weeks, skills in picked:
            course = Course(
                id=sid("course", f"{slug(centre.district)}/{slug(title)}"),
                centre_id=centre.id,
                title=title,
                sector=centre.sector_focus,
                nsqf_level=nsqf,
                duration_weeks=weeks,
                skills=list(skills),
            )
            courses.append(course)
            courses_by_centre[centre.id].append(course)

    trainee_users: list[User] = []
    trainees: list[Trainee] = []
    consents: list[Consent] = []
    employment_records: list[EmploymentRecord] = []
    verifications: list[Verification] = []
    followups: list[FollowUp] = []

    base_count, remainder = divmod(TRAINEE_COUNT, len(centres))
    per_centre = [base_count + (1 if i < remainder else 0) for i in range(len(centres))]

    for centre, count in zip(centres, per_centre, strict=True):
        for _ in range(count):
            trainee_no = len(trainees) + 1
            key = f"{trainee_no:03d}"
            is_demo_trainee = trainee_no == 1
            email = DEMO_TRAINEE_EMAIL if is_demo_trainee else f"trainee-{key}@trackskill.in"
            user = User(
                id=sid("user", f"trainee-{key}"),
                name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                email=email,
                password_hash=password_hash,
                role=UserRole.TRAINEE,
                is_demo=True,
                is_active=True,
            )
            trainee_users.append(user)
            if is_demo_trainee:
                demo_trainee_user = user

            if is_demo_trainee:
                course = courses_by_centre[centre.id][0]
            else:
                course = rng.choice(courses_by_centre[centre.id])

            if is_demo_trainee:
                # Certified 85 days ago: employed, verified, and the 3-month
                # follow-up lands within days ("milestones due").
                enrolled_on = today - timedelta(
                    days=course.duration_weeks * 7 + DEMO_TRAINEE_CERTIFIED_DAYS_AGO
                )
                status = TraineeStatus.CERTIFIED
                certified_on = enrolled_on + timedelta(weeks=course.duration_weeks)
            else:
                enrolled_on = today - timedelta(days=rng.randint(45, 540))
                certificate_date = enrolled_on + timedelta(weeks=course.duration_weeks)
                draw = rng.random()
                if draw < 0.10:
                    status, certified_on = TraineeStatus.DROPPED, None
                elif certificate_date <= today and draw < 0.85:
                    status, certified_on = TraineeStatus.CERTIFIED, certificate_date
                else:
                    status, certified_on = TraineeStatus.ENROLLED, None

            gender_draw = rng.random()
            gender = "FEMALE" if gender_draw < 0.45 else "MALE" if gender_draw < 0.95 else "OTHER"

            trainee = Trainee(
                id=sid("trainee", key),
                user_id=user.id,
                centre_id=centre.id,
                course_id=course.id,
                phone=f"+91 9{rng.randint(100000000, 999999999)}",
                district=centre.district,
                gender=gender,
                enrolled_on=enrolled_on,
                certified_on=certified_on,
                status=status,
            )
            trainees.append(trainee)

            # Consent ledger — tracing is only allowed on active channels.
            if is_demo_trainee:
                consent_plan: dict[ConsentChannel, bool] = {
                    ConsentChannel.WHATSAPP: True,
                    ConsentChannel.IVR: True,
                    ConsentChannel.SMS: False,
                }
            else:
                consent_plan = {
                    channel: rng.random() < chance for channel, chance in CONSENT_CHANCES.items()
                }
            active_channels: list[ConsentChannel] = []
            for channel, granted in consent_plan.items():
                granted_at = utc(enrolled_on + timedelta(days=3))
                revoked_at = None
                if granted and not is_demo_trainee and rng.random() < 0.08:
                    revoked_at = granted_at + timedelta(days=rng.randint(5, 60))
                if granted and revoked_at is None:
                    active_channels.append(channel)
                consents.append(
                    Consent(
                        id=sid("consent", f"{key}/{channel.value}"),
                        trainee_id=trainee.id,
                        channel=channel,
                        granted=granted,
                        granted_at=granted_at,
                        revoked_at=revoked_at,
                        purpose_text=CONSENT_PURPOSE,
                        version=CONSENT_VERSION,
                    )
                )

            if status is TraineeStatus.CERTIFIED and certified_on is not None:
                # Employment outcome.
                if is_demo_trainee:
                    employment_status = EmploymentStatus.EMPLOYED
                else:
                    draw = rng.random()
                    if draw < 0.55:
                        employment_status = EmploymentStatus.EMPLOYED
                    elif draw < 0.70:
                        employment_status = EmploymentStatus.SELF_EMPLOYED
                    elif draw < 0.88:
                        employment_status = EmploymentStatus.UNEMPLOYED
                    else:
                        employment_status = EmploymentStatus.FURTHER_STUDY

                employer_id = None
                job_title = None
                monthly_wage = None
                started_on = None
                if employment_status in WORKING_STATUSES:
                    job_title = course.title
                    if is_demo_trainee:
                        monthly_wage = 24000
                        started_on = certified_on + timedelta(days=20)
                        employer_id = employers[0].id
                    else:
                        low, high = SECTOR_WAGES[course.sector]
                        monthly_wage = int(round(rng.uniform(low, high) / 100) * 100)
                        started_on = certified_on + timedelta(days=rng.randint(10, 90))
                        started_on = min(started_on, today - timedelta(days=1))
                        started_on = max(started_on, certified_on)
                        if employment_status is EmploymentStatus.EMPLOYED:
                            options = employers_by_sector.get(course.sector) or employers
                            employer_id = rng.choice(options).id

                record = EmploymentRecord(
                    id=sid("employment", key),
                    trainee_id=trainee.id,
                    employer_id=employer_id,
                    status=employment_status,
                    job_title=job_title,
                    monthly_wage=monthly_wage,
                    started_on=started_on,
                )
                employment_records.append(record)

                # Dual-signal verification (verified column is DB-computed).
                if is_demo_trainee:
                    trainee_signal = VerificationSignal.CONFIRMED
                    employer_signal = VerificationSignal.CONFIRMED
                else:
                    if employment_status is EmploymentStatus.EMPLOYED:
                        trainee_confirm, employer_confirm = 0.90, 0.85
                    elif employment_status is EmploymentStatus.SELF_EMPLOYED:
                        trainee_confirm, employer_confirm = 0.85, 0.50
                    else:
                        trainee_confirm, employer_confirm = 0.80, 0.00

                    trainee_signal = (
                        VerificationSignal.CONFIRMED
                        if rng.random() < trainee_confirm
                        else (
                            VerificationSignal.DISPUTED
                            if rng.random() < 0.35
                            else VerificationSignal.PENDING
                        )
                    )
                    employer_signal = (
                        VerificationSignal.CONFIRMED
                        if rng.random() < employer_confirm
                        else VerificationSignal.PENDING
                    )
                verifications.append(
                    Verification(
                        id=sid("verification", key),
                        employment_record_id=record.id,
                        trainee_signal=trainee_signal,
                        employer_signal=employer_signal,
                    )
                )

                # Follow-up history across the 3/6/12-month milestones.
                if active_channels:
                    channel = active_channels[0] if is_demo_trainee else rng.choice(active_channels)
                    for milestone, offset in MILESTONE_OFFSET_DAYS.items():
                        due_on = certified_on + timedelta(days=offset)
                        if is_demo_trainee:
                            # Milestones due: M3 lands within days (SENT), the
                            # later milestones stay scheduled.
                            state = (
                                FollowUpState.SENT
                                if (due_on - today).days <= 10
                                else FollowUpState.SCHEDULED
                            )
                            responded_at = None
                            response = None
                        elif due_on > today:
                            state = (
                                FollowUpState.SENT
                                if (due_on - today).days <= 10
                                else FollowUpState.SCHEDULED
                            )
                            responded_at = None
                            response = None
                        elif rng.random() < RESPONSE_RATE_BY_MILESTONE[milestone]:
                            state = FollowUpState.RESPONDED
                            responded_at = utc(due_on + timedelta(days=rng.randint(0, 5)), 12)
                            response = _followup_response(rng, course.sector, milestone, channel)
                        else:
                            state = FollowUpState.MISSED
                            responded_at = None
                            response = None
                        followups.append(
                            FollowUp(
                                id=sid("followup", f"{key}/{milestone.value}"),
                                trainee_id=trainee.id,
                                milestone=milestone,
                                due_on=due_on,
                                channel=channel,
                                state=state,
                                responded_at=responded_at,
                                response_json=response,
                            )
                        )

    # The demo employer account is linked to several trainees' employment
    # records (same sector), so the verification queue has content.
    course_by_id = {course.id: course for course in courses}
    trainee_by_id = {trainee.id: trainee for trainee in trainees}
    demo_employer = employers[0]
    linked_records = 0
    for record in employment_records:
        if linked_records >= 4:
            break
        if record.trainee_id == trainees[0].id:
            continue  # the demo trainee already works for the demo employer
        if record.status is not EmploymentStatus.EMPLOYED or record.employer_id is None:
            continue
        if course_by_id[trainee_by_id[record.trainee_id].course_id].sector != demo_employer.sector:
            continue
        record.employer_id = demo_employer.id
        linked_records += 1

    market_demand = _market_demand(rng)
    provider_scores = _provider_scores(
        centres, trainees, employment_records, followups, verifications
    )
    fund_allocations = _fund_allocations(centres, provider_scores, admin.id)
    events = _events(
        admin=admin,
        provider=demo_provider_user,
        employer=demo_employer_user,
        trainee=demo_trainee_user,
        latest_period=month_starts(SCORE_PERIODS)[-1],
    )
    notifications = _notifications(
        admin=admin,
        provider=demo_provider_user,
        employer=demo_employer_user,
        trainee=demo_trainee_user,
    )

    return {
        "users": [admin, *staff_users, *employer_users, *trainee_users],
        "training_centres": centres,
        "provider_staff": staff_links,
        "courses": courses,
        "employers": employers,
        "trainees": trainees,
        "consents": consents,
        "employment_records": employment_records,
        "verifications": verifications,
        "followups": followups,
        "market_demand": market_demand,
        "provider_scores": provider_scores,
        "fund_allocations": fund_allocations,
        "events": events,
        "notifications": notifications,
    }


def _market_demand(rng: random.Random) -> list[MarketDemand]:
    """12 months of demand scores per (sector, skill, district)."""
    rows: list[MarketDemand] = []
    for month in month_starts(MARKET_MONTHS):
        for sector, skills in SECTOR_SKILLS.items():
            for skill, weight in skills:
                phase = (sum(ord(char) for char in skill) % 12) * (math.pi / 6)
                seasonal = 12 * math.sin(2 * math.pi * (month.month - 1) / 12 + phase)
                for district in DISTRICTS:
                    score = 25 + 55 * weight + seasonal + rng.uniform(-6, 6)
                    rows.append(
                        MarketDemand(
                            id=sid(
                                "market", f"{sector}/{skill}/{district}/{month.isoformat()}"
                            ),
                            sector=sector,
                            skill=skill,
                            district=district,
                            demand_score=round(min(100.0, max(5.0, score)), 1),
                            month=month,
                        )
                    )
    return rows


def _provider_scores(
    centres: list[TrainingCentre],
    trainees: list[Trainee],
    employment_records: list[EmploymentRecord],
    followups: list[FollowUp],
    verifications: list[Verification],
) -> list[ProviderScore]:
    """Compute PPI components per centre for the last few monthly periods.

    All rates are fractions 0..1; ppi_score is 0..100 with weights:
    placement 35% · average retention 25% · verification 20% · wage growth 20%.
    """
    trainees_by_centre: dict[uuid.UUID, list[Trainee]] = defaultdict(list)
    for trainee in trainees:
        trainees_by_centre[trainee.centre_id].append(trainee)

    record_by_trainee = {record.trainee_id: record for record in employment_records}
    followups_by_trainee: dict[uuid.UUID, list[FollowUp]] = defaultdict(list)
    for followup in followups:
        followups_by_trainee[followup.trainee_id].append(followup)
    signals_by_record = {
        verification.employment_record_id: (
            verification.trainee_signal,
            verification.employer_signal,
        )
        for verification in verifications
    }

    def wages_for(trainee_id: uuid.UUID, milestone: FollowUpMilestone) -> float | None:
        for followup in followups_by_trainee.get(trainee_id, []):
            if (
                followup.milestone is milestone
                and followup.state is FollowUpState.RESPONDED
                and followup.response_json
                and followup.response_json.get("wage") is not None
            ):
                return float(followup.response_json["wage"])
        return None

    def responded(trainee_id: uuid.UUID, milestone: FollowUpMilestone) -> list[FollowUp]:
        return [
            followup
            for followup in followups_by_trainee.get(trainee_id, [])
            if followup.milestone is milestone and followup.state is FollowUpState.RESPONDED
        ]

    def is_working(followup: FollowUp) -> bool:
        return bool(followup.response_json) and followup.response_json.get("employment") in {
            status.value for status in WORKING_STATUSES
        }

    scores: list[ProviderScore] = []
    for period in month_starts(SCORE_PERIODS):
        for centre in centres:
            certified = [
                trainee
                for trainee in trainees_by_centre[centre.id]
                if trainee.status is TraineeStatus.CERTIFIED
                and trainee.certified_on is not None
                and trainee.certified_on < period
            ]
            placement = retention_3m = retention_6m = retention_12m = 0.0
            wage_growth = verification_rate = 0.0
            if certified:
                certified_ids = {trainee.id for trainee in certified}
                records = [
                    record_by_trainee[trainee_id]
                    for trainee_id in certified_ids
                    if trainee_id in record_by_trainee
                ]
                placement = sum(record.status in WORKING_STATUSES for record in records) / len(
                    certified_ids
                )

                retentions = []
                for milestone in (
                    FollowUpMilestone.M3,
                    FollowUpMilestone.M6,
                    FollowUpMilestone.M12,
                ):
                    responses = [
                        followup
                        for trainee_id in certified_ids
                        for followup in responded(trainee_id, milestone)
                        if followup.due_on < period
                    ]
                    rate = (
                        sum(is_working(followup) for followup in responses) / len(responses)
                        if responses
                        else 0.0
                    )
                    retentions.append(rate)
                retention_3m, retention_6m, retention_12m = retentions

                growths = []
                for trainee_id in certified_ids:
                    wage_3 = wages_for(trainee_id, FollowUpMilestone.M3)
                    wage_12 = wages_for(trainee_id, FollowUpMilestone.M12)
                    if wage_3 and wage_12:
                        growths.append(min(max((wage_12 - wage_3) / wage_3, -0.5), 1.5))
                wage_growth = sum(growths) / len(growths) if growths else 0.0

                if records:
                    verification_rate = sum(
                        signals_by_record.get(record.id, (None, None))
                        == (VerificationSignal.CONFIRMED, VerificationSignal.CONFIRMED)
                        for record in records
                    ) / len(records)

            ppi = 100 * (
                0.35 * placement
                + 0.25 * ((retention_3m + retention_6m + retention_12m) / 3)
                + 0.20 * verification_rate
                + 0.20 * min(max(wage_growth, 0.0) / 0.5, 1.0)
            )
            scores.append(
                ProviderScore(
                    id=sid("provider_score", f"{slug(centre.district)}/{period.isoformat()}"),
                    centre_id=centre.id,
                    period=period,
                    placement_rate=round(placement, 4),
                    retention_3m=round(retention_3m, 4),
                    retention_6m=round(retention_6m, 4),
                    retention_12m=round(retention_12m, 4),
                    wage_growth=round(wage_growth, 4),
                    verification_rate=round(verification_rate, 4),
                    ppi_score=round(ppi, 2),
                )
            )
    return scores


def _fund_allocations(
    centres: list[TrainingCentre], scores: list[ProviderScore], admin_id: uuid.UUID
) -> list[FundAllocation]:
    latest_period = month_starts(SCORE_PERIODS)[-1]
    score_by_centre = {
        score.centre_id: score for score in scores if score.period == latest_period
    }
    allocations: list[FundAllocation] = []
    for centre in centres:
        score = score_by_centre[centre.id]
        amount = int(round((400_000 + 1_100_000 * score.ppi_score / 100) / 10_000) * 10_000)
        allocations.append(
            FundAllocation(
                id=sid("allocation", f"{slug(centre.district)}/{latest_period.isoformat()}"),
                centre_id=centre.id,
                amount=amount,
                rationale=(
                    f"PPI {score.ppi_score:.1f} for {latest_period:%B %Y}: allocation weighted "
                    "by placement, retention, wage growth and verification performance."
                ),
                decided_by=admin_id,
                decided_at=utc(latest_period, 11),
            )
        )
    return allocations


def _events(
    admin: User,
    provider: User | None,
    employer: User | None,
    trainee: User | None,
    latest_period: date,
) -> list[Event]:
    return [
        Event(
            id=sid("event", "consent-granted"),
            type="consent.granted",
            actor_user_id=trainee.id if trainee else None,
            actor_role="TRAINEE",
            payload={"channel": ConsentChannel.WHATSAPP.value, "version": CONSENT_VERSION},
        ),
        Event(
            id=sid("event", "employment-recorded"),
            type="employment.recorded",
            actor_user_id=provider.id if provider else None,
            actor_role="PROVIDER",
            payload={"source": "provider-portal"},
        ),
        Event(
            id=sid("event", "verification-confirmed"),
            type="verification.confirmed",
            actor_user_id=employer.id if employer else None,
            actor_role="EMPLOYER",
            payload={"method": "employer-portal"},
        ),
        Event(
            id=sid("event", "followup-responded"),
            type="followup.responded",
            actor_user_id=None,
            actor_role="SYSTEM",
            payload={"milestone": FollowUpMilestone.M3.value, "channel": "ivr"},
        ),
        Event(
            id=sid("event", "fund-allocation-decided"),
            type="fund_allocation.decided",
            actor_user_id=admin.id,
            actor_role="ADMIN",
            payload={"period": latest_period.isoformat()},
        ),
        Event(
            id=sid("event", "seed-completed"),
            type="seed.completed",
            actor_user_id=None,
            actor_role="SYSTEM",
            payload={"source": "app.seed"},
        ),
    ]


def _notifications(
    admin: User,
    provider: User | None,
    employer: User | None,
    trainee: User | None,
) -> list[Notification]:
    title = "Welcome to TrackSkill AI"
    body = (
        "Your demo workspace is ready. Explore outcome tracking, consent management "
        "and the Provider Performance Index."
    )
    notifications: list[Notification] = []
    for label, user in (
        ("admin", admin),
        ("provider", provider),
        ("employer", employer),
        ("trainee", trainee),
    ):
        if user is None:
            continue
        notifications.append(
            Notification(
                id=sid("notification", label),
                user_id=user.id,
                title=title,
                body=body,
                link="/dashboard",
                read=False,
            )
        )
    return notifications


def prune_followups_without_consent(session: Session) -> int:
    """Consent-first repair: drop follow-ups whose trainee has no active consent.

    Tracing without recorded consent is never allowed. Under normal operation
    the generator never creates such rows; this guard keeps the database
    compliant even after partial deletes or seed-data drift.
    """
    active_consent_trainees = select(Consent.trainee_id).where(
        Consent.granted.is_(True),
        Consent.revoked_at.is_(None),
    )
    result = session.execute(
        delete(FollowUp).where(FollowUp.trainee_id.not_in(active_consent_trainees))
    )
    return result.rowcount or 0


# ── Runner ────────────────────────────────────────────────────────────────────


def print_counts(session: Session) -> None:
    print("\nRow counts per table")
    for _, model in INGEST_ORDER:
        count = session.execute(select(func.count()).select_from(model)).scalar_one()
        print(f"  {model.__tablename__:<22} {count:>6}")


def print_credentials() -> None:
    settings = get_settings()
    print(f"\nDemo credentials (password: {settings.demo_password})")
    print(f"  ADMIN     {DEMO_ADMIN_EMAIL}")
    print(f"  PROVIDER  {DEMO_PROVIDER_EMAIL}")
    print(f"  TRAINEE   {DEMO_TRAINEE_EMAIL}")
    print(f"  EMPLOYER  {DEMO_EMPLOYER_EMAIL}")


def run() -> None:
    settings = get_settings()
    rng = random.Random(RNG_SEED)
    password_hash = hash_password(settings.demo_password)
    data = build_seed_data(rng, password_hash)

    with SessionLocal() as session:
        try:
            with session.begin():
                ingestor = SeedIngestor(session)
                for label, model in INGEST_ORDER:
                    ingestor.ingest(label, model, data[label])
                pruned = prune_followups_without_consent(session)
                if pruned:
                    logger.info(
                        "Pruned %s follow-up(s) without active consent (consent-first repair).",
                        pruned,
                    )
        except (OperationalError, ProgrammingError) as exc:
            logger.error("Seeding failed: %s", exc)
            logger.error(
                "Has the schema been created? Run `alembic upgrade head` first "
                "and check DATABASE_URL."
            )
            raise SystemExit(1) from exc

        ingestor.print_summary()
        print_counts(session)
        print_credentials()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s")
    run()
