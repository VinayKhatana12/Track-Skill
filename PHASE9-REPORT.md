# TrackSkill AI — Phase 9 completion report

Authenticated application shell + one personalised dashboard per role, with
realtime updates. Generated from commit 9538669; every file below is the
complete current content on disk (32 files, 6,519 lines).

## File tree (Phase 9 scope)

```
apps/api
├── alembic/versions/0002_core_schema.py        # modified: line-wrap only (ruff E501)
├── app
│   ├── main.py                                 # modified: notifications + search routers
│   ├── routers
│   │   ├── admin.py                            # modified: POST /admin/demo/reset
│   │   ├── employer.py                         # modified: impact + talent pool
│   │   ├── notifications.py                    # NEW: mark-read endpoints
│   │   ├── provider.py                         # modified: curriculum gaps
│   │   └── search.py                           # NEW: global search
│   ├── schemas/domain.py                       # modified: new response models
│   └── services
│       ├── admin_service.py                    # modified: reset_demo_data
│       ├── employer_service.py                 # modified: impact, talent pool
│       ├── provider_service.py                 # modified: curriculum_gaps
│       └── trainee_service.py                  # modified: employment self-report
apps/web/src
├── app
│   ├── dashboard
│   │   ├── layout.tsx                          # modified: guard + realtime invalidation
│   │   ├── admin/page.tsx                      # rewritten: Governance
│   │   ├── employer/page.tsx                   # rewritten: Verify & Hire
│   │   ├── provider/page.tsx                   # rewritten: Centre Command
│   │   └── trainee/page.tsx                    # rewritten: My Journey
│   └── globals.css                             # modified: realtime-pulse keyframe
├── components
│   ├── charts/outcomes-bar.tsx                 # NEW
│   ├── dashboard
│   │   ├── app-shell.tsx                       # NEW: DashboardShell
│   │   ├── connection-pill.tsx                 # NEW
│   │   ├── global-search.tsx                   # NEW
│   │   ├── kpi-card.tsx                        # NEW: KpiCard + PulseCard + EmptyState
│   │   ├── notifications-bell.tsx              # NEW
│   │   └── profile-menu.tsx                    # NEW
│   └── ui/skeleton.tsx                         # NEW
├── hooks
│   ├── use-pulse.ts                            # NEW
│   └── use-realtime-connection.ts              # NEW
├── lib
│   ├── api.ts                                  # modified: all typed endpoints
│   └── export.ts                               # NEW: CSV + print-PDF
└── stores/realtime-store.ts                    # NEW
```

---

## `apps/api/app/routers/notifications.py`

```python
"""Notification endpoints: list mine, mark read, mark all read."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.dependencies import require_role
from app.models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", summary="My notifications (newest first)")
def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    items = db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    ).scalars().all()
    unread = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == current_user.id, Notification.read.is_(False))
    ).scalar_one()
    return {
        "unread": unread,
        "items": [
            {
                "id": str(item.id),
                "title": item.title,
                "body": item.body,
                "link": item.link,
                "read": item.read,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
    }


@router.post("/{notification_id}/read", summary="Mark one notification read")
def mark_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    notification.read = True
    db.flush()
    return {"read": True}


@router.post("/read-all", summary="Mark all my notifications read")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.read.is_(False))
        .values(read=True)
    )
    db.flush()
    return {"updated": result.rowcount or 0}

```

---

## `apps/api/app/routers/search.py`

```python
"""Role-aware global search for the top bar."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.dependencies import require_role
from app.models import Course, Trainee, TrainingCentre, User
from app.models.enums import UserRole

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", summary="Search within your role's scope")
def search(
    q: str = Query(min_length=1, max_length=80),
    db: Session = Depends(get_db),
    current_user=Depends(require_role()),
) -> dict:
    needle = f"%{q.strip().lower()}%"
    results: list[dict] = []

    if current_user.role in (UserRole.ADMIN, UserRole.PROVIDER):
        trainees = db.execute(
            select(Trainee, User)
            .join(User, Trainee.user_id == User.id)
            .where(or_(User.name.ilike(needle), User.email.ilike(needle)))
            .limit(5)
        ).all()
        for _, user in trainees:
            results.append(
                {"type": "trainee", "label": user.name, "detail": user.email}
            )
    if current_user.role is UserRole.ADMIN:
        centres = db.execute(
            select(TrainingCentre).where(
                or_(TrainingCentre.name.ilike(needle), TrainingCentre.district.ilike(needle))
            ).limit(5)
        ).scalars().all()
        for centre in centres:
            results.append(
                {"type": "centre", "label": centre.name, "detail": centre.district}
            )
    if current_user.role is UserRole.EMPLOYER:
        courses = db.execute(
            select(Course).where(Course.title.ilike(needle)).limit(5)
        ).scalars().all()
        for course in courses:
            results.append({"type": "skill", "label": course.title, "detail": course.sector})
    if current_user.role is UserRole.TRAINEE:
        courses = db.execute(
            select(Course).where(Course.title.ilike(needle)).limit(5)
        ).scalars().all()
        for course in courses:
            results.append({"type": "course", "label": course.title, "detail": course.sector})

    return {"results": results[:10]}

```

---

## `apps/api/app/main.py`

```python
"""TrackSkill AI API entrypoint."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.realtime.ws import router as ws_router
from app.routers import (
    admin,
    auth,
    contact,
    employer,
    health,
    notifications,
    provider,
    search,
    trainee,
    trainees,
)

logging.basicConfig(
    level=get_settings().log_level.upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def tracer_tick() -> None:
    """One background tracer cycle: create, send, expire."""
    from app.core.db import SessionLocal
    from app.services import tracer_service

    with SessionLocal() as db:
        summary = await tracer_service.run_tracer_cycle(db)
        db.commit()
        if summary["created"] or summary["sent"] or summary["missed"]:
            logger.info(
                "Tracer tick: created %s, sent %s, missed %s",
                summary["created"],
                len(summary["sent"]),
                len(summary["missed"]),
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logger.info(
        "Starting %s v%s (%s)",
        settings.project_name,
        settings.project_version,
        settings.environment,
    )
    scheduler_started = False
    if settings.scheduler_enabled:
        scheduler.add_job(
            tracer_tick,
            "interval",
            seconds=settings.tracer_interval_seconds,
            id="tracer-tick",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        scheduler_started = True
        logger.info(
            "Tracer scheduler started (interval %ss, provider %s)",
            settings.tracer_interval_seconds,
            settings.tracer_provider,
        )
    yield
    if scheduler_started:
        scheduler.shutdown(wait=False)
    logger.info("Shutting down %s", settings.project_name)


def create_app() -> FastAPI:
    """Build the FastAPI application with middleware and routers attached."""
    settings = get_settings()
    application = FastAPI(
        title=settings.project_name,
        version=settings.project_version,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(contact.router)
    application.include_router(notifications.router)
    application.include_router(search.router)
    application.include_router(trainees.router)
    application.include_router(provider.router)
    application.include_router(trainee.router)
    application.include_router(employer.router)
    application.include_router(admin.router)
    application.include_router(ws_router)
    return application


app = create_app()

```

---

## `apps/api/app/routers/admin.py`

```python
"""Admin REST API: state KPIs, PPI leaderboard, allocations, audit feed."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai import anomalies, curriculum_matcher
from app.core.config import get_settings
from app.core.db import get_db
from app.dependencies import require_role
from app.models import User
from app.models.enums import UserRole
from app.schemas.domain import AllocationRequest, FlagRequest
from app.services import admin_service, tracer_service

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/tracer/run", summary="Run the tracer cycle now (demo fast-forward)")
async def run_tracer(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    """Demo control: fast-forwards demo tracers to today and delivers them.

    Available only while DEMO_MODE is enabled.
    """
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return await tracer_service.run_tracer_now(db)


@router.get("/overview", summary="State-wide KPIs and district heat data")
def overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    return admin_service.state_overview(db)


@router.get("/providers", summary="PPI leaderboard")
def providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> list[dict]:
    return admin_service.providers_leaderboard(db)


@router.get("/providers/{centre_id}", summary="Centre detail with score history")
def provider_detail(
    centre_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    return admin_service.provider_detail(db, centre_id)


@router.post("/allocations", status_code=201, summary="Record a fund allocation")
async def create_allocation(
    payload: AllocationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    return await admin_service.create_allocation(
        db,
        admin_user=current_user,
        centre_id=payload.centre_id,
        amount=float(payload.amount),
        rationale=payload.rationale,
    )


@router.post("/providers/{centre_id}/flag", summary="Flag a centre (live notification)")
async def flag_provider(
    centre_id: UUID,
    payload: FlagRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    return await admin_service.flag_provider(
        db, admin_user=current_user, centre_id=centre_id, reason=payload.reason
    )


@router.post("/demo/reset", summary="Reset demo data (DEMO_MODE only)")
async def demo_reset(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return await admin_service.reset_demo_data(db)


@router.get(
    "/curriculum-gaps",
    summary="Per-course curriculum-demand gap report (AI module)",
)
def curriculum_gaps(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> list[dict]:
    return curriculum_matcher.course_gap_report(db, limit=limit)


@router.post("/anomalies/scan", summary="Run statistical anomaly detection now")
async def run_anomaly_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    raised = await anomalies.scan_all(db)
    return {"raised": raised, "raised_count": len(raised)}


@router.get("/events", summary="Live audit feed")
def events(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> list[dict]:
    return admin_service.events_feed(db, limit=limit)

```

---

## `apps/api/app/routers/employer.py`

```python
"""Employer REST API: verification queue, hiring, talent pool."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.dependencies import require_role
from app.models import User
from app.models.enums import UserRole
from app.schemas.domain import DisputeRequest, HireTraineeRequest
from app.services import employer_service

router = APIRouter(prefix="/employer", tags=["Employer"])


@router.get("/verifications", summary="Pending employment claims")
def verifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> list[dict]:
    employer = employer_service.own_employer(db, current_user.id)
    return employer_service.pending_verifications(db, employer)


@router.post("/verifications/{verification_id}/confirm", summary="Confirm an employment claim")
async def confirm(
    verification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> dict:
    employer = employer_service.own_employer(db, current_user.id)
    return await employer_service.confirm_verification(
        db, employer=employer, verification_id=verification_id
    )


@router.post("/verifications/{verification_id}/dispute", summary="Dispute an employment claim")
async def dispute(
    verification_id: UUID,
    payload: DisputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> dict:
    employer = employer_service.own_employer(db, current_user.id)
    return await employer_service.dispute_verification(
        db, employer=employer, verification_id=verification_id, reason=payload.reason
    )


@router.post(
    "/trainees/{trainee_id}/hire",
    status_code=status.HTTP_201_CREATED,
    summary="Record hiring a certified trainee",
)
async def hire(
    trainee_id: UUID,
    payload: HireTraineeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> dict:
    employer = employer_service.own_employer(db, current_user.id)
    return await employer_service.hire_trainee(
        db,
        employer=employer,
        trainee_id=trainee_id,
        job_title=payload.job_title,
        monthly_wage=payload.monthly_wage,
        started_on=payload.started_on,
    )


@router.get("/talent-pool", summary="Certified, consented trainees by skill")
def talent_pool(
    skill: str | None = Query(default=None, description="Substring filter"),
    district: str | None = Query(default=None, description="District filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> list[dict]:
    employer = employer_service.own_employer(db, current_user.id)
    return employer_service.talent_pool(db, employer, skill, district)


@router.get("/impact", summary="Retention and verification stats for your hires")
def impact(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.EMPLOYER)),
) -> dict:
    employer = employer_service.own_employer(db, current_user.id)
    return employer_service.impact(db, employer)

```

---

## `apps/api/app/routers/provider.py`

```python
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

```

---

## `apps/api/app/schemas/domain.py`

```python
"""Request payloads for the role-scoped REST APIs."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import ConsentChannel, EmploymentStatus


class EnrolTraineeRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone: str = Field(min_length=5, max_length=20)
    course_id: UUID
    gender: str = Field(default="UNSPECIFIED", max_length=20)
    centre_id: UUID | None = None


class CertifyTraineeRequest(BaseModel):
    certified_on: date | None = None


class ConsentRequest(BaseModel):
    channel: ConsentChannel
    granted: bool


class RespondTextRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class SkillsAssessmentRequest(BaseModel):
    self_reported_skills: list[str] = Field(default_factory=list, max_length=20)
    free_text: str | None = Field(default=None, max_length=2000)


class RespondFollowUpRequest(BaseModel):
    employment_status: EmploymentStatus
    job_title: str | None = Field(default=None, max_length=255)
    monthly_wage: float | None = Field(default=None, ge=0)
    employer_id: UUID | None = None


class EmploymentSelfReportRequest(BaseModel):
    employment_status: EmploymentStatus
    job_title: str = Field(min_length=2, max_length=255)
    monthly_wage: float = Field(gt=0)
    started_on: date | None = None
    employer_id: UUID | None = None


class HireTraineeRequest(BaseModel):
    job_title: str = Field(min_length=2, max_length=255)
    monthly_wage: float = Field(gt=0)
    started_on: date | None = None


class DisputeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AllocationRequest(BaseModel):
    centre_id: UUID
    amount: Decimal = Field(gt=0)
    rationale: str = Field(min_length=3, max_length=1000)


class FlagRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

```

---

## `apps/api/app/services/admin_service.py`

```python
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

```

---

## `apps/api/app/services/employer_service.py`

```python
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

```

---

## `apps/api/app/services/provider_service.py`

```python
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

```

---

## `apps/api/app/services/trainee_service.py`

```python
"""Trainee domain services: consent, follow-up responses, journey, skills."""

import logging
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
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
    FollowUp,
    ProviderStaff,
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

```

---

## `apps/api/alembic/versions/0002_core_schema.py`

```python
"""Core domain schema for TrackSkill AI: 15 tables, native enums, indexes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql

from app.models.base import NAMING_CONVENTION

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Native PostgreSQL enum types, created explicitly so that tables sharing a
# type (consent_channel) never attempt duplicate CREATE TYPE statements.
USER_ROLE = postgresql.ENUM(
    "PROVIDER", "TRAINEE", "EMPLOYER", "ADMIN", name="user_role", create_type=False
)
CONSENT_CHANNEL = postgresql.ENUM(
    "WHATSAPP", "IVR", "SMS", name="consent_channel", create_type=False
)
TRAINEE_STATUS = postgresql.ENUM(
    "ENROLLED", "CERTIFIED", "DROPPED", name="trainee_status", create_type=False
)
EMPLOYMENT_STATUS = postgresql.ENUM(
    "EMPLOYED",
    "SELF_EMPLOYED",
    "UNEMPLOYED",
    "FURTHER_STUDY",
    name="employment_status",
    create_type=False,
)
FOLLOWUP_MILESTONE = postgresql.ENUM(
    "M3", "M6", "M12", name="followup_milestone", create_type=False
)
FOLLOWUP_STATE = postgresql.ENUM(
    "SCHEDULED", "SENT", "RESPONDED", "MISSED", name="followup_state", create_type=False
)
VERIFICATION_SIGNAL = postgresql.ENUM(
    "PENDING", "CONFIRMED", "DISPUTED", name="verification_signal", create_type=False
)

ENUM_TYPES = (
    USER_ROLE,
    CONSENT_CHANNEL,
    TRAINEE_STATUS,
    EMPLOYMENT_STATUS,
    FOLLOWUP_MILESTONE,
    FOLLOWUP_STATE,
    VERIFICATION_SIGNAL,
)

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.func.now()

# The metadata mirrors app/models exactly (same naming convention, columns,
# constraints and indexes) so future autogenerated migrations stay in sync.
metadata = MetaData(naming_convention=NAMING_CONVENTION)

users = sa.Table(
    "users",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("name", String(255), nullable=False),
    sa.Column("email", String(255), nullable=False, unique=True),
    sa.Column("password_hash", String(255), nullable=False),
    sa.Column("role", USER_ROLE, nullable=False),
    sa.Column("is_demo", Boolean, nullable=False),
    sa.Column("is_active", Boolean, nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)
Index("ix_users_role", users.c.role)

training_centres = sa.Table(
    "training_centres",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("name", String(255), nullable=False),
    sa.Column("district", String(120), nullable=False),
    sa.Column("state", String(120), nullable=False),
    sa.Column("sector_focus", String(120), nullable=False),
    sa.Column("funding_status", String(60), nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)
Index("ix_training_centres_district", training_centres.c.district)

provider_staff = sa.Table(
    "provider_staff",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("user_id", UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column(
        "centre_id", UUID, ForeignKey("training_centres.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    UniqueConstraint("user_id", "centre_id"),
)
Index("ix_provider_staff_centre_id", provider_staff.c.centre_id)

courses = sa.Table(
    "courses",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "centre_id", UUID, ForeignKey("training_centres.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("title", String(255), nullable=False),
    sa.Column("sector", String(120), nullable=False),
    sa.Column("nsqf_level", Integer, nullable=False),
    sa.Column("duration_weeks", Integer, nullable=False),
    sa.Column("skills", postgresql.ARRAY(Text), nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    CheckConstraint("nsqf_level >= 1 AND nsqf_level <= 10", name="nsqf_level_range"),
)
Index("ix_courses_centre_id", courses.c.centre_id)
Index("ix_courses_sector", courses.c.sector)

trainees = sa.Table(
    "trainees",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "user_id", UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    ),
    sa.Column(
        "centre_id", UUID, ForeignKey("training_centres.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("course_id", UUID, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
    sa.Column("phone", String(20), nullable=False),
    sa.Column("district", String(120), nullable=False),
    sa.Column("gender", String(20), nullable=False),
    sa.Column("enrolled_on", Date, nullable=False),
    sa.Column("certified_on", Date, nullable=True),
    sa.Column("status", TRAINEE_STATUS, nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)
Index("ix_trainees_centre_id", trainees.c.centre_id)
Index("ix_trainees_course_id", trainees.c.course_id)
Index("ix_trainees_district", trainees.c.district)
Index("ix_trainees_status", trainees.c.status)

consents = sa.Table(
    "consents",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("trainee_id", UUID, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False),
    sa.Column("channel", CONSENT_CHANNEL, nullable=False),
    sa.Column("granted", Boolean, nullable=False),
    sa.Column("granted_at", DateTime(timezone=True), nullable=False),
    sa.Column("revoked_at", DateTime(timezone=True), nullable=True),
    sa.Column("purpose_text", Text, nullable=False),
    sa.Column("version", String(20), nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    UniqueConstraint("trainee_id", "channel", "version"),
)
Index("ix_consents_trainee_id", consents.c.trainee_id)

employers = sa.Table(
    "employers",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "user_id", UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    ),
    sa.Column("company_name", String(255), nullable=False),
    sa.Column("sector", String(120), nullable=False),
    sa.Column("district", String(120), nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)
Index("ix_employers_sector", employers.c.sector)

employment_records = sa.Table(
    "employment_records",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("trainee_id", UUID, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False),
    sa.Column(
        "employer_id", UUID, ForeignKey("employers.id", ondelete="SET NULL"), nullable=True
    ),
    sa.Column("status", EMPLOYMENT_STATUS, nullable=False),
    sa.Column("job_title", String(255), nullable=True),
    sa.Column("monthly_wage", Numeric(12, 2), nullable=True),
    sa.Column("started_on", Date, nullable=True),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)
Index("ix_employment_records_trainee_id", employment_records.c.trainee_id)
Index("ix_employment_records_employer_id", employment_records.c.employer_id)
Index("ix_employment_records_status", employment_records.c.status)

followups = sa.Table(
    "followups",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("trainee_id", UUID, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False),
    sa.Column("milestone", FOLLOWUP_MILESTONE, nullable=False),
    sa.Column("due_on", Date, nullable=False),
    sa.Column("channel", CONSENT_CHANNEL, nullable=False),
    sa.Column("state", FOLLOWUP_STATE, nullable=False),
    sa.Column("responded_at", DateTime(timezone=True), nullable=True),
    sa.Column("response_json", postgresql.JSONB, nullable=True),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    UniqueConstraint("trainee_id", "milestone"),
)
Index("ix_followups_trainee_id", followups.c.trainee_id)
Index("ix_followups_state", followups.c.state)

verifications = sa.Table(
    "verifications",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "employment_record_id",
        UUID,
        ForeignKey("employment_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    sa.Column("trainee_signal", VERIFICATION_SIGNAL, nullable=False),
    sa.Column("employer_signal", VERIFICATION_SIGNAL, nullable=False),
    sa.Column(
        "verified",
        Boolean,
        Computed(
            "(trainee_signal = 'CONFIRMED'::verification_signal) "
            "AND (employer_signal = 'CONFIRMED'::verification_signal)",
            persisted=True,
        ),
        nullable=False,
    ),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)

market_demand = sa.Table(
    "market_demand",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("sector", String(120), nullable=False),
    sa.Column("skill", String(120), nullable=False),
    sa.Column("district", String(120), nullable=False),
    sa.Column("demand_score", Float, nullable=False),
    sa.Column("month", Date, nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    UniqueConstraint("sector", "skill", "district", "month"),
)
Index("ix_market_demand_skill", market_demand.c.skill)
Index("ix_market_demand_district_month", market_demand.c.district, market_demand.c.month)

provider_scores = sa.Table(
    "provider_scores",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "centre_id", UUID, ForeignKey("training_centres.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("period", Date, nullable=False),
    sa.Column("placement_rate", Float, nullable=False),
    sa.Column("retention_3m", Float, nullable=False),
    sa.Column("retention_6m", Float, nullable=False),
    sa.Column("retention_12m", Float, nullable=False),
    sa.Column("wage_growth", Float, nullable=False),
    sa.Column("verification_rate", Float, nullable=False),
    sa.Column("ppi_score", Float, nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    UniqueConstraint("centre_id", "period"),
)
Index("ix_provider_scores_centre_id", provider_scores.c.centre_id)

fund_allocations = sa.Table(
    "fund_allocations",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column(
        "centre_id", UUID, ForeignKey("training_centres.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("amount", Numeric(14, 2), nullable=False),
    sa.Column("rationale", Text, nullable=False),
    sa.Column("decided_by", UUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    sa.Column("decided_at", DateTime(timezone=True), nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)
Index("ix_fund_allocations_centre_id", fund_allocations.c.centre_id)

events = sa.Table(
    "events",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("type", String(100), nullable=False),
    sa.Column("actor_user_id", UUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    sa.Column("actor_role", String(32), nullable=False),
    sa.Column("payload", postgresql.JSONB, nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)
Index("ix_events_type", events.c.type)
Index("ix_events_actor_user_id", events.c.actor_user_id)

notifications = sa.Table(
    "notifications",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("user_id", UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("title", String(255), nullable=False),
    sa.Column("body", Text, nullable=False),
    sa.Column("link", String(500), nullable=True),
    sa.Column("read", Boolean, nullable=False),
    sa.Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)
Index("ix_notifications_user_id", notifications.c.user_id)
Index("ix_notifications_read", notifications.c.read)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)

    # op.create_table() only accepts a column list, so the full Table DDL
    # (constraints and indexes included) is emitted directly through the
    # migration connection.
    for table in metadata.sorted_tables:
        table.create(bind, checkfirst=False)


def downgrade() -> None:
    for table in reversed(metadata.sorted_tables):
        op.drop_table(table.name)

    bind = op.get_bind()
    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(bind, checkfirst=True)

```

---

## `apps/web/src/stores/realtime-store.ts`

```typescript
"use client";

import { create } from "zustand";

export interface RealtimeEvent {
  type: string;
  payload: Record<string, unknown>;
  at: number;
}

interface RealtimeState {
  connected: boolean;
  lastEvent: RealtimeEvent | null;
  setConnected: (connected: boolean) => void;
  record: (type: string, payload?: Record<string, unknown>) => void;
}

/** Tracks the live WebSocket connection and the most recent domain event so
 * cards can pulse when the data they show changes. */
export const useRealtimeStore = create<RealtimeState>((set) => ({
  connected: false,
  lastEvent: null,
  setConnected: (connected) => set({ connected }),
  record: (type, payload) => set({ lastEvent: { type, payload: payload ?? {}, at: Date.now() } }),
}));

```

---

## `apps/web/src/hooks/use-pulse.ts`

```typescript
"use client";

import { useEffect, useState } from "react";

import { useRealtimeStore } from "@/stores/realtime-store";

/** True for ~2 seconds after any of the given event types arrives over the
 * realtime socket. Wrap a card and apply a visible pulse class. */
export function usePulse(...types: string[]): boolean {
  const lastEvent = useRealtimeStore((state) => state.lastEvent);
  const [pulsing, setPulsing] = useState(false);
  const typesKey = types.join("|");

  useEffect(() => {
    if (!lastEvent || !typesKey.split("|").includes(lastEvent.type)) {
      return;
    }
    setPulsing(true);
    const timer = setTimeout(() => setPulsing(false), 2000);
    return () => clearTimeout(timer);
  }, [lastEvent, typesKey]);

  return pulsing;
}

```

---

## `apps/web/src/hooks/use-realtime-connection.ts`

```typescript
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { API_URL, ensureFreshToken, getAccessToken } from "@/lib/api";
import { useRealtimeStore } from "@/stores/realtime-store";

/** Opens the authenticated realtime socket, feeds every domain event into
 * the pulse store and invalidates React Query caches so all dashboards
 * refresh without a page reload. */
export function useRealtimeConnection(active: boolean) {
  const queryClient = useQueryClient();
  const setConnected = useRealtimeStore((state) => state.setConnected);
  const record = useRealtimeStore((state) => state.record);
  const queryClientRef = useRef(queryClient);
  queryClientRef.current = queryClient;

  useEffect(() => {
    if (!active) {
      return;
    }
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;

    const connect = () => {
      const token = getAccessToken();
      const wsUrl = `${API_URL.replace(/^http/, "ws")}/ws${
        token ? `?token=${encodeURIComponent(token)}` : ""
      }`;
      socket = new WebSocket(wsUrl);

      socket.onopen = () => setConnected(true);

      socket.onmessage = (message) => {
        try {
          const data = JSON.parse(message.data) as {
            event?: string;
            payload?: Record<string, unknown>;
          };
          if (data.event && data.event !== "pong" && data.event !== "connection.established") {
            record(data.event, data.payload);
            void queryClientRef.current.invalidateQueries();
          }
        } catch {
          // non-JSON frame — ignore
        }
      };

      socket.onclose = (closeEvent) => {
        setConnected(false);
        if (disposed) {
          return;
        }
        const wasAuthFailure = closeEvent.code === 4401;
        const delay = wasAuthFailure ? 300 : 3000;
        retryTimer = window.setTimeout(async () => {
          if (wasAuthFailure) {
            await ensureFreshToken();
          }
          connect();
        }, delay);
      };
    };

    void (async () => {
      await ensureFreshToken();
      if (!disposed) {
        connect();
      }
    })();

    return () => {
      disposed = true;
      if (retryTimer) {
        window.clearTimeout(retryTimer);
      }
      socket?.close();
      setConnected(false);
    };
  }, [active, setConnected, record]);
}

```

---

## `apps/web/src/components/dashboard/app-shell.tsx`

```typescript
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConnectionPill } from "@/components/dashboard/connection-pill";
import { GlobalSearch } from "@/components/dashboard/global-search";
import { NotificationsBell } from "@/components/dashboard/notifications-bell";
import { ProfileMenu } from "@/components/dashboard/profile-menu";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { useRealtimeConnection } from "@/hooks/use-realtime-connection";
import { useAuthStore } from "@/stores/auth-store";
import { useRealtimeStore } from "@/stores/realtime-store";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/types/api";

const ROLE_NAV: Record<UserRole, { id: string; label: string }[]> = {
  PROVIDER: [
    { id: "overview", label: "Overview" },
    { id: "trainees", label: "Trainees" },
    { id: "followups", label: "Follow-ups" },
    { id: "insights", label: "Insights" },
  ],
  TRAINEE: [
    { id: "journey", label: "My Journey" },
    { id: "consent", label: "Consent" },
    { id: "messages", label: "Messages" },
    { id: "skills", label: "Skills" },
  ],
  EMPLOYER: [
    { id: "verify", label: "Verify" },
    { id: "hires", label: "Hires" },
    { id: "talent", label: "Talent pool" },
    { id: "impact", label: "Impact" },
  ],
  ADMIN: [
    { id: "governance", label: "Governance" },
    { id: "providers", label: "Providers" },
    { id: "gaps", label: "Gaps" },
    { id: "activity", label: "Activity" },
  ],
};

export function DashboardShell({
  children,
  role,
  headline,
  subheading,
}: {
  children: React.ReactNode;
  role: UserRole;
  headline: string;
  subheading: string;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const status = useAuthStore((state) => state.status);
  const bootstrap = useAuthStore((state) => state.bootstrap);
  const connected = useRealtimeStore((state) => state.connected);
  const [collapsed, setCollapsed] = useState(false);

  useRealtimeConnection(status === "authenticated");

  useEffect(() => {
    if (status === "idle") {
      void bootstrap();
    }
  }, [status, bootstrap]);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status !== "authenticated" || !user) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background text-muted-foreground">
        <p role="status">
          {status === "loading" ? "Loading your workspace…" : "Redirecting to sign-in…"}
        </p>
      </div>
    );
  }

  const firstName = (user.name ?? "").split(" ")[0];
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const sections = ROLE_NAV[role];

  const mobileNavigate = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="flex min-h-dvh bg-background">
      {/* Desktop sidebar */}
      <aside
        data-collapsed={collapsed || undefined}
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-border/70 bg-card transition-[width] md:flex",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <div
          className={cn(
            "flex h-16 items-center border-b border-border/60",
            collapsed ? "justify-center px-2" : "px-4",
          )}
        >
          <Link href="/" aria-label="TrackSkill AI home" className="flex items-center">
            <Logo withWordmark={!collapsed} />
          </Link>
        </div>
        <nav aria-label="Dashboard sections" className="flex-1 space-y-1 p-2">
          {sections.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              title={section.label}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                collapsed && "justify-center px-2",
              )}
            >
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-marigold-400" />
              {!collapsed && <span>{section.label}</span>}
            </a>
          ))}
        </nav>
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex w-full items-center justify-center gap-2 border-t border-border/60 py-3 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" aria-hidden />
          ) : (
            <>
              <PanelLeftClose className="h-4 w-4" aria-hidden />
              <span className="text-xs">Collapse</span>
            </>
          )}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 backdrop-blur">
          <div className="flex h-16 items-center gap-3 px-4">
            <button
              type="button"
              onClick={() => setCollapsed((value) => !value)}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              className="hidden rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground md:inline-flex"
            >
              {collapsed ? (
                <PanelLeftOpen className="h-4 w-4" aria-hidden />
              ) : (
                <PanelLeftClose className="h-4 w-4" aria-hidden />
              )}
            </button>
            <Link href="/login" aria-label="TrackSkill AI home" className="md:hidden">
              <Logo withWordmark={false} />
            </Link>

            <div className="hidden min-w-0 flex-1 sm:block">
              <GlobalSearch />
            </div>

            <div className="ml-auto flex items-center gap-2 sm:gap-3">
              <ConnectionPill connected={connected} />
              <ThemeToggle />
              <NotificationsBell />
              <ProfileMenu />
            </div>
          </div>
        </header>

        {/* Page header */}
        <div className="border-b border-border/70 bg-muted/30 px-4 py-6 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <p className="text-xs font-semibold uppercase tracking-wider text-marigold-700 dark:text-marigold-300">
              {greeting}, {firstName} · {user.role}
            </p>
            <h1 className="mt-1 font-display text-2xl font-semibold tracking-tight sm:text-3xl">
              {headline}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">{subheading}</p>
          </div>
        </div>

        {/* Content */}
        <main className="flex-1 pb-24 md:pb-10">
          <div className="mx-auto max-w-6xl space-y-10 px-4 py-8 sm:px-6">{children}</div>
        </main>
      </div>

      {/* Mobile bottom tabs */}
      <nav
        aria-label="Dashboard sections"
        className="fixed bottom-0 left-0 right-0 z-40 grid grid-cols-4 border-t border-border bg-background md:hidden"
      >
        {sections.map((section) => (
          <button
            key={section.id}
            type="button"
            onClick={() => mobileNavigate(section.id)}
            className="flex flex-col items-center gap-0.5 py-2.5 text-[10px] text-muted-foreground hover:text-foreground"
          >
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-marigold-400" />
            {section.label}
          </button>
        ))}
      </nav>
    </div>
  );
}

```

---

## `apps/web/src/components/dashboard/connection-pill.tsx`

```typescript
"use client";

import { cn } from "@/lib/utils";

export function ConnectionPill({ connected }: { connected: boolean }) {
  return (
    <span
      role="status"
      aria-label={connected ? "Realtime connection live" : "Realtime connection offline"}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
        connected
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "h-2 w-2 rounded-full",
          connected ? "animate-pulse bg-emerald-500" : "bg-red-500",
        )}
      />
      {connected ? "Live" : "Offline"}
    </span>
  );
}

```

---

## `apps/web/src/components/dashboard/global-search.tsx`

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { globalSearch, type SearchResult } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
export function GlobalSearch() {
  const role = useAuthStore((state) => state.user?.role);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const search = useQuery({
    queryKey: ["global-search", query],
    queryFn: () => globalSearch(query),
    enabled: query.trim().length >= 2,
  });

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const results: SearchResult[] = query.trim().length >= 2 ? (search.data?.results ?? []) : [];

  return (
    <div className="relative w-full max-w-xs" ref={boxRef}>
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search…"
          aria-label="Global search"
          className="h-9 w-full rounded-md border border-input bg-background pl-8 pr-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>
      {open && query.trim().length >= 2 && (
        <div
          className="absolute left-0 top-10 z-50 w-full overflow-hidden rounded-lg border border-border bg-card shadow-lg"
          role="listbox"
          aria-label="Search results"
        >
          {search.isFetching ? (
            <p className="flex items-center gap-2 px-3 py-3 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> Searching…
            </p>
          ) : results.length === 0 ? (
            <p className="px-3 py-3 text-sm text-muted-foreground">No matches found.</p>
          ) : (
            <ul className="max-h-72 overflow-y-auto">
              {results.map((result, index) => (
                <li
                  key={`${result.type}-${result.label}-${index}`}
                  className="flex items-center justify-between gap-2 border-b border-border/60 px-3 py-2 text-sm last:border-0"
                >
                  <span className="truncate font-medium">{result.label}</span>
                  <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                    {result.type}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <span className="sr-only">
        Search scope: {role ?? "your role"}
      </span>
    </div>
  );
}

```

---

## `apps/web/src/components/dashboard/kpi-card.tsx`

```typescript
"use client";

import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Wraps a card and applies a visible 2-second pulse when a matching
 * realtime event arrives (Phase 9 realtime requirement). */
export function PulseCard({
  pulsing,
  children,
  className,
}: {
  pulsing: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl transition-shadow duration-700",
        pulsing && "realtime-pulse",
        className,
      )}
      data-pulsing={pulsing || undefined}
    >
      {children}
    </div>
  );
}

export function KpiCard({
  icon: Icon,
  label,
  value,
  hint,
  pulsing,
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  hint?: string;
  pulsing?: boolean;
}) {
  return (
    <PulseCard pulsing={Boolean(pulsing)} className="h-full">
      <Card className="h-full">
        <CardContent className="flex items-center justify-between gap-3 pt-6">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {label}
            </p>
            <p className="mt-1 font-display text-3xl font-semibold" aria-label={String(value)}>
              {value}
            </p>
            {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
          </div>
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-secondary text-primary">
            <Icon className="h-5 w-5" aria-hidden />
          </span>
        </CardContent>
      </Card>
    </PulseCard>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  hint,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border p-6 text-center">
      <Icon className="h-6 w-6 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

```

---

## `apps/web/src/components/dashboard/notifications-bell.tsx`

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useRealtimeStore } from "@/stores/realtime-store";

export function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const lastEvent = useRealtimeStore((state) => state.lastEvent);

  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: fetchNotifications,
    refetchInterval: 30_000,
  });

  // Any domain event may carry a notification for this user — refresh.
  useEffect(() => {
    if (lastEvent) {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }
  }, [lastEvent, queryClient]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    const onClick = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, []);

  const markAll = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const markOne = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unread = notifications.data?.unread ?? 0;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        className="relative flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <Bell className="h-5 w-5" aria-hidden />
        {unread > 0 && (
          <span
            className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground"
            aria-hidden
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          className="absolute right-0 top-10 z-50 w-80 overflow-hidden rounded-lg border border-border bg-card shadow-lg"
          role="dialog"
          aria-label="Notifications"
        >
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <p className="text-sm font-medium">Notifications</p>
            {unread > 0 && (
              <button
                type="button"
                onClick={() => markAll.mutate()}
                className="flex items-center gap-1 text-xs text-primary hover:underline"
              >
                <CheckCheck className="h-3.5 w-3.5" aria-hidden />
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {(notifications.data?.items.length ?? 0) === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">
                No notifications yet.
              </p>
            ) : (
              notifications.data!.items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => !item.read && markOne.mutate(item.id)}
                  className={cn(
                    "block w-full border-b border-border/60 px-3 py-2.5 text-left transition-colors hover:bg-accent",
                    !item.read && "bg-secondary/40",
                  )}
                >
                  <p className="flex items-center justify-between text-sm font-medium">
                    {item.title}
                    {!item.read && (
                      <span className="h-2 w-2 rounded-full bg-primary" aria-label="unread" />
                    )}
                  </p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{item.body}</p>
                  {item.created_at && (
                    <p className="mt-1 text-[10px] text-muted-foreground">
                      {new Date(item.created_at).toLocaleString("en-GB")}
                    </p>
                  )}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

```

---

## `apps/web/src/components/dashboard/profile-menu.tsx`

```typescript
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, LogOut, UserCircle2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAuthStore } from "@/stores/auth-store";

export function ProfileMenu() {
  const user = useAuthStore((state) => state.user);
  const signOut = useAuthStore((state) => state.signOut);
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const handleSignOut = async () => {
    await signOut();
    queryClient.clear();
    setOpen(false);
  };

  return (
    <div className="relative" ref={boxRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
      >
        <UserCircle2 className="h-6 w-6 text-muted-foreground" aria-hidden />
        <span className="hidden font-medium sm:inline">{user?.name ?? "Account"}</span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Profile menu"
          className="absolute right-0 top-11 z-50 w-56 overflow-hidden rounded-lg border border-border bg-card shadow-lg"
        >
          <div className="border-b border-border/60 px-3 py-2.5">
            <p className="text-sm font-medium">{user?.name}</p>
            <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
            <p className="mt-1 inline-flex rounded-full bg-secondary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-secondary-foreground">
              {user?.role}
            </p>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => void handleSignOut()}
            className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm hover:bg-accent"
          >
            <LogOut className="h-4 w-4" aria-hidden />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

```

---

## `apps/web/src/components/ui/skeleton.tsx`

```typescript
import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} aria-hidden />;
}

```

---

## `apps/web/src/components/charts/outcomes-bar.tsx`

```typescript
"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** Outcomes-by-milestone bar chart with accessible colours and tooltips. */
export function OutcomesBar({
  data,
}: {
  data: { milestone: string; rate: number }[];
}) {
  const percent = (value: number) => `${Math.round(value * 100)}%`;
  return (
    <div
      className="h-64 w-full"
      role="img"
      aria-label={`Retention by milestone: ${data
        .map((item) => `${item.milestone} ${percent(item.rate)}`)
        .join(", ")}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis
            dataKey="milestone"
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
            stroke="hsl(var(--border))"
          />
          <YAxis
            tickFormatter={percent}
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
            stroke="hsl(var(--border))"
            domain={[0, 1]}
          />
          <Tooltip
            formatter={(value: number | string) => percent(Number(value))}
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8,
              color: "hsl(var(--card-foreground))",
            }}
          />
          <Bar
            dataKey="rate"
            name="Still in work"
            fill="#2f8f8c"
            radius={[6, 6, 0, 0]}
            maxBarSize={56}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

```

---

## `apps/web/src/lib/export.ts`

```typescript
"use client";

/** Exports table rows as a downloadable CSV file (client-side, no deps). */
export function downloadCsv(
  filename: string,
  rows: readonly Record<string, unknown>[],
): void {
  if (rows.length === 0) {
    return;
  }
  const headers = Object.keys(rows[0]);
  const escape = (value: unknown) =>
    `"${String(value ?? "").replace(/"/g, '""')}"`;
  const csv = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => escape(row[header])).join(",")),
  ].join("\r\n");

  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** Opens the browser print dialog for the element with the given id.
 * The user can "Save as PDF" — the print stylesheet isolates the section. */
export function printSection(elementId: string): void {
  const target = document.getElementById(elementId);
  if (!target) {
    return;
  }
  document.body.classList.add("printing-section");
  target.classList.add("print-target");
  window.print();
  window.setTimeout(() => {
    document.body.classList.remove("printing-section");
    target.classList.remove("print-target");
  }, 400);
}

```

---

## `apps/web/src/lib/api.ts`

```typescript
/**
 * Typed fetch client for the TrackSkill AI API.
 *
 * - The short-lived access token lives in memory only and is attached as a
 *   Bearer header.
 * - The long-lived refresh token is an httpOnly cookie managed by the API;
 *   on a 401 the client runs a single-flight refresh and retries once.
 * - Base URLs come from the environment:
 *     NEXT_PUBLIC_API_URL  e.g. http://localhost:8000
 *     NEXT_PUBLIC_WS_URL   e.g. ws://localhost:8000/ws
 */

import type {
  AuthTokens,
  DemoAccount,
  TraineeMessage,
  TraineeProfile,
  TracerRunSummary,
  UserPublic,
  UserRole,
} from "@/types/api";

const RAW_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const RAW_WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "";

export const API_URL = RAW_API_URL.replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(status: number, message: string, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export interface RequestOptions {
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Ensures the in-memory access token is fresh (single-flight refresh). */
export async function ensureFreshToken(): Promise<boolean> {
  return refreshAccessToken();
}

const authExpiredListeners = new Set<() => void>();

/** Register a callback fired when the session cannot be restored. */
export function onAuthExpired(listener: () => void): () => void {
  authExpiredListeners.add(listener);
  return () => {
    authExpiredListeners.delete(listener);
  };
}

// Endpoints whose own 401 responses must never trigger a refresh round-trip.
const AUTH_PATHS = ["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout"];

let refreshInFlight: Promise<boolean> | null = null;

async function requestRefresh(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      cache: "no-store",
    });
    if (!response.ok) {
      return false;
    }
    const data = (await response.json()) as { access_token: string };
    accessToken = data.access_token;
    return true;
  } catch {
    return false;
  }
}

function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = requestRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

interface InternalOptions extends RequestOptions {
  method?: string;
  body?: unknown;
  isRetry?: boolean;
}

async function request<T>(path: string, options: InternalOptions = {}): Promise<T> {
  const { method = "GET", body, headers, signal, isRetry = false } = options;

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "include",
    cache: "no-store",
    signal,
  });

  if (
    response.status === 401 &&
    !isRetry &&
    !AUTH_PATHS.some((authPath) => path.startsWith(authPath))
  ) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return request<T>(path, { ...options, isRetry: true });
    }
    accessToken = null;
    authExpiredListeners.forEach((listener) => listener());
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    let details: unknown = null;
    try {
      const problem = await response.json();
      details = problem;
      if (typeof problem?.detail === "string") {
        message = problem.detail;
      }
    } catch {
      // The response had no JSON body; keep the generic message.
    }
    throw new ApiError(response.status, message, details);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, options: RequestOptions = {}) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options: RequestOptions = {}) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options: RequestOptions = {}) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options: RequestOptions = {}) =>
    request<T>(path, { ...options, method: "DELETE" }),
};

export function getApiUrl(): string {
  return API_URL;
}

/**
 * Build the WebSocket URL for a channel.
 *
 * NEXT_PUBLIC_WS_URL may be the full endpoint (ws://host/ws) or just the
 * origin (ws://host) — in the latter case /ws is appended. When unset, the
 * URL is derived from the API base URL.
 */
export function getWsUrl(channel = "global"): string {
  let base = RAW_WS_URL.trim();
  if (!base) {
    base = `${API_URL.replace(/^http/, "ws")}/ws`;
  }
  base = base.replace(/\/+$/, "");
  if (!/\/ws$/.test(base)) {
    base = `${base}/ws`;
  }
  return `${base}?channel=${encodeURIComponent(channel)}`;
}

// ── Auth endpoints ───────────────────────────────────────────────────────────

export interface SignUpInput {
  name: string;
  email: string;
  password: string;
  role: UserRole;
  phone?: string;
  district?: string;
  centre_code?: string;
  company_name?: string;
  company_district?: string;
  consent_channels?: string[];
}

export async function login(email: string, password: string): Promise<AuthTokens> {
  return api.post<AuthTokens>("/auth/login", { email, password });
}

export async function requestPasswordReset(
  email: string,
): Promise<{ status: string; message: string; reset_link?: string }> {
  return api.post("/auth/forgot-password", { email });
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<{ status: string; message: string }> {
  return api.post("/auth/reset-password", { token, new_password: newPassword });
}

export async function register(input: SignUpInput): Promise<AuthTokens> {
  return api.post<AuthTokens>("/auth/register", input);
}

export async function fetchMe(): Promise<UserPublic> {
  return api.get<UserPublic>("/auth/me");
}

export async function logout(): Promise<void> {
  await api.post<{ detail: string }>("/auth/logout");
}

export async function fetchDemoAccounts(): Promise<DemoAccount[] | null> {
  try {
    return await api.get<DemoAccount[]>("/auth/demo-accounts");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function fetchMyTraineeProfile(): Promise<TraineeProfile> {
  return api.get<TraineeProfile>("/trainees/me");
}

// ── Contact endpoint ─────────────────────────────────────────────────────────

export interface ContactPayload {
  name: string;
  email: string;
  organisation?: string;
  role: "PROVIDER" | "TRAINEE" | "EMPLOYER" | "ADMIN" | "OTHER";
  message: string;
}

export async function submitContact(
  payload: ContactPayload,
): Promise<{ status: string; id: string; message: string }> {
  return api.post("/contact", payload);
}

// ── Tracer endpoints ─────────────────────────────────────────────────────────

export async function fetchTraineeMessages(): Promise<TraineeMessage[]> {
  return api.get<TraineeMessage[]>("/trainee/messages");
}

export interface TracerReplyPayload {
  employment_status: "EMPLOYED" | "SELF_EMPLOYED" | "UNEMPLOYED" | "FURTHER_STUDY";
  job_title?: string;
  monthly_wage?: number;
}

export async function respondFollowupText(
  followupId: string,
  message: string,
): Promise<{ needs_review: boolean; confidence: number; parsed: Record<string, unknown> }> {
  return api.post(`/trainee/followups/${followupId}/respond/text`, { message });
}

export async function respondFollowupStructured(
  followupId: string,
  payload: TracerReplyPayload,
): Promise<{ followup_id: string; state: string }> {
  return api.post(`/trainee/followups/${followupId}/respond`, payload);
}

export async function runTracerNow(): Promise<TracerRunSummary> {
  return api.post<TracerRunSummary>("/admin/tracer/run");
}

// ── Admin endpoints ──────────────────────────────────────────────────────────

export async function fetchAdminOverview(): Promise<AdminOverview> {
  return api.get("/admin/overview");
}

export async function fetchAdminProviders(): Promise<LeaderboardRow[]> {
  return api.get("/admin/providers");
}

export async function fetchAdminProviderDetail(
  centreId: string,
): Promise<AdminProviderDetail> {
  return api.get(`/admin/providers/${centreId}`);
}

export async function fetchGapReports(): Promise<GapReportRow[]> {
  return api.get("/admin/curriculum-gaps");
}

export async function fetchEvents(limit: number): Promise<EventItem[]> {
  return api.get(`/admin/events?limit=${limit}`);
}

export async function submitAllocation(payload: {
  centre_id: string;
  amount: number;
  rationale: string;
}): Promise<{ allocation_id: string; amount: number; rationale: string }> {
  return api.post("/admin/allocations", payload);
}

export async function resetDemoData(): Promise<{ status: string; users: number }> {
  return api.post("/admin/demo/reset");
}

export async function runAnomalyScan(): Promise<{
  raised: { rule: string }[];
  raised_count: number;
}> {
  return api.post("/admin/anomalies/scan");
}

// ── Admin types ──────────────────────────────────────────────────────────────

export interface AdminOverview {
  trainees: number;
  certified: number;
  placed: number;
  employment_rate: number;
  retention_3m: number;
  retention_6m: number;
  retention_12m: number;
  median_wage_uplift: number;
  self_employment_share: number;
  verification_rate: number;
  demo_mode?: boolean;
  districts: {
    district: string;
    trainees: number;
    certified: number;
    working: number;
    employment_rate: number;
  }[];
}

export interface LeaderboardRow {
  centre_id: string;
  centre_name: string;
  district: string;
  rank: number;
  ppi_score: number;
  placement_rate: number;
  verification_rate: number;
  response_rate: number;
}

export interface AdminProviderDetail {
  centre: { id: string; name: string; district: string };
  enrolled: number;
  certified: number;
  placement_rate: number;
  verification_rate: number;
  ppi_score: number;
  score_history: {
    period: string;
    ppi_score: number;
    placement_rate: number;
    verification_rate: number;
  }[];
  allocations: { id: string; amount: number; rationale: string; decided_at: string | null }[];
}

export interface GapReportRow {
  course_id: string;
  title: string;
  sector: string;
  centre_name: string;
  district: string;
  course_skills: string[];
  coverage: number;
  gap_score: number;
  missing_in_demand_skills: { skill: string; demand_score: number }[];
  suggested_modules: string[];
}

export interface EventItem {
  id: string;
  type: string;
  actor_user_id: string | null;
  actor_role: string;
  payload: Record<string, unknown>;
  created_at: string | null;
}


// ── Notifications ────────────────────────────────────────────────────────────

export interface NotificationItem {
  id: string;
  title: string;
  body: string;
  link: string | null;
  read: boolean;
  created_at: string | null;
}

export async function fetchNotifications(): Promise<{
  unread: number;
  items: NotificationItem[];
}> {
  return api.get("/notifications");
}

export async function markNotificationRead(id: string): Promise<void> {
  await api.post(`/notifications/${id}/read`);
}

export async function markAllNotificationsRead(): Promise<void> {
  await api.post("/notifications/read-all");
}

// ── Search ───────────────────────────────────────────────────────────────────

export interface SearchResult {
  type: string;
  label: string;
  detail: string | null;
}

export async function globalSearch(q: string): Promise<{ results: SearchResult[] }> {
  return api.get(`/search?q=${encodeURIComponent(q)}`);
}

// ── Trainee employment + assessment ─────────────────────────────────────────

export interface EmploymentSelfReport {
  employment_status: "EMPLOYED" | "SELF_EMPLOYED" | "UNEMPLOYED" | "FURTHER_STUDY";
  job_title: string;
  monthly_wage: number;
  started_on?: string;
  employer_id?: string;
}

export async function reportEmployment(payload: EmploymentSelfReport): Promise<{
  employment_record_id: string;
  verification_id: string;
  verified: boolean;
}> {
  return api.post("/trainee/employment", payload);
}

export async function assessSkills(payload: {
  self_reported_skills?: string[];
  free_text?: string;
}): Promise<{
  profile: { skill: string; sector: string; confidence: number }[];
  role_matches: { title: string; sector: string; score: number; explanation: string }[];
  mode: string;
}> {
  return api.post("/trainee/skills/assessment", payload);
}

// ── Provider extras ──────────────────────────────────────────────────────────

export interface ProviderCourse {
  id: string;
  title: string;
  sector: string;
}

export async function fetchProviderCourses(): Promise<ProviderCourse[]> {
  return api.get("/provider/courses");
}

export interface ProviderOverview {
  centre: { id: string; name: string; district: string };
  enrolled: number;
  certified: number;
  dropped: number;
  placements: number;
  consent_rate: number;
  response_rate: number;
  placement_rate: number;
  retention_3m: number;
  retention_6m: number;
  retention_12m: number;
  ppi_score: number;
  ppi_rank: number;
  total_centres: number;
}

export interface ProviderTraineeRow {
  id: string;
  name: string;
  email: string;
  course_id: string;
  course_title: string | null;
  status: string;
  enrolled_on: string;
  certified_on: string | null;
  consent_active: boolean;
}

export interface ProviderFollowupItem {
  followup_id: string;
  trainee_id: string;
  trainee_name: string;
  milestone: string;
  due_on: string;
  channel: string;
  state?: string;
  raw_text?: string;
  parsed?: Record<string, unknown>;
}

export interface ProviderFollowups {
  overdue: ProviderFollowupItem[];
  due_soon: ProviderFollowupItem[];
  manual_review: ProviderFollowupItem[];
}

export async function fetchProviderOverview(): Promise<ProviderOverview> {
  return api.get("/provider/overview");
}

export async function fetchProviderTrainees(): Promise<ProviderTraineeRow[]> {
  return api.get("/provider/trainees");
}

export async function fetchProviderFollowups(): Promise<ProviderFollowups> {
  return api.get("/provider/followups");
}

export async function certifyTrainee(traineeId: string): Promise<{
  trainee_id: string;
  certified_on: string;
  consent_active: boolean;
  followups_scheduled: number;
}> {
  return api.patch(`/provider/trainees/${traineeId}/certify`, {});
}

export async function enrolTrainee(payload: {
  name: string;
  email: string;
  phone: string;
  course_id: string;
  centre_id?: string;
}): Promise<{ trainee: { id: string }; temporary_password: string }> {
  return api.post("/provider/trainees", payload);
}

export async function fetchProviderGapAlerts(): Promise<
  { course_id: string; title: string; gap_score: number; missing_in_demand_skills: { skill: string; demand_score: number }[]; suggested_modules: string[] }[]
> {
  return api.get("/provider/curriculum-gaps");
}

// ── Employer extras ──────────────────────────────────────────────────────────

export interface EmployerImpact {
  hires: number;
  verified_hires: number;
  working: number;
  retention_3m: number;
  retention_6m: number;
  retention_12m: number;
  avg_monthly_wage: number;
}

export async function fetchEmployerImpact(): Promise<EmployerImpact> {
  return api.get("/employer/impact");
}

export async function fetchVerifications(
  status?: "pending" | "confirmed" | "disputed",
): Promise<VerificationRow[]> {
  const params = status ? `?status=${status}` : "";
  return api.get(`/employer/verifications${params}`);
}

export async function markConfirmed(
  verificationId: string,
): Promise<{ verification_id: string; verified: boolean }> {
  return api.post(`/employer/verifications/${verificationId}/confirm`);
}

export async function markDisputed(
  verificationId: string,
  reason: string,
): Promise<{ verification_id: string; employer_signal: string }> {
  return api.post(`/employer/verifications/${verificationId}/dispute`, { reason });
}

export interface VerificationRow {
  verification_id: string;
  trainee_name: string;
  employment_status: string;
  job_title: string | null;
  monthly_wage: number | null;
  trainee_signal: string;
}

export interface TalentPoolRow {
  skill: string;
  trainee_count: number;
  districts: string[];
  trainee_names: string[];
  match_score: number;
}

export async function fetchTalentPool(
  skill?: string,
  district?: string,
): Promise<TalentPoolRow[]> {
  const params = new URLSearchParams();
  if (skill) params.set("skill", skill);
  if (district) params.set("district", district);
  return api.get(`/employer/talent-pool?${params.toString()}`);
}

// ── Admin extras ─────────────────────────────────────────────────────────────

export interface GapReportRow {
  course_id: string;
  title: string;
  sector: string;
  centre_name: string;
  district: string;
  course_skills: string[];
  coverage: number;
  gap_score: number;
  missing_in_demand_skills: { skill: string; demand_score: number }[];
  suggested_modules: string[];
}

```

---

## `apps/web/src/app/dashboard/layout.tsx`

```typescript
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useRealtimeConnection } from "@/hooks/use-realtime-connection";
import { useAuthStore } from "@/stores/auth-store";
import { useRealtimeStore } from "@/stores/realtime-store";

/** Authenticated shell wrapper: guards unauthenticated visitors, opens the
 * realtime socket and invalidates React Query caches when domain events
 * arrive. The visual chrome (sidebar, top bar, tabs) is rendered per role
 * page via DashboardShell. */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((state) => state.user);
  const status = useAuthStore((state) => state.status);
  const bootstrap = useAuthStore((state) => state.bootstrap);

  useRealtimeConnection(status === "authenticated");

  useEffect(() => {
    if (status === "idle") {
      void bootstrap();
    }
  }, [status, bootstrap]);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  // Any domain event may change data anywhere — invalidate all queries.
  useEffect(() => {
    const unsubscribe = useRealtimeStore.subscribe((state) => {
      if (state.lastEvent) {
        void queryClient.invalidateQueries();
      }
    });
    return unsubscribe;
  }, [queryClient]);

  if (status !== "authenticated" || !user) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background text-muted-foreground">
        <p role="status">
          {status === "loading" ? "Loading your workspace…" : "Redirecting to sign-in…"}
        </p>
      </div>
    );
  }

  return <>{children}</>;
}

```

---

## `apps/web/src/app/dashboard/provider/page.tsx`

```typescript
"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { useState } from "react";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { EmptyState, KpiCard, PulseCard } from "@/components/dashboard/kpi-card";
import { OutcomesBar } from "@/components/charts/outcomes-bar";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePulse } from "@/hooks/use-pulse";
import { DashboardShell } from "@/components/dashboard/app-shell";
import { api } from "@/lib/api";
import { downloadCsv } from "@/lib/export";
import {
  fetchProviderCourses,
  fetchProviderFollowups,
  fetchProviderGapAlerts,
  fetchProviderOverview,
  fetchProviderTrainees,
} from "@/lib/api";

interface TraineeRow {
  id: string;
  name: string;
  email: string;
  course_title: string | null;
  status: string;
  consent_active: boolean;
}

interface FollowupItem {
  followup_id: string;
  trainee_name: string;
  milestone: string;
  due_on: string;
  channel: string;
  raw_text?: string;
}

export default function ProviderDashboard() {
  const queryClient = useQueryClient();
  const overview = useQuery({
    queryKey: ["provider-overview"],
    queryFn: fetchProviderOverview,
  });
  const trainees = useQuery({
    queryKey: ["provider-trainees"],
    queryFn: fetchProviderTrainees,
  });
  const followups = useQuery({
    queryKey: ["provider-followups"],
    queryFn: fetchProviderFollowups,
  });
  const courses = useQuery({
    queryKey: ["provider-courses"],
    queryFn: fetchProviderCourses,
  });
  const gaps = useQuery({
    queryKey: ["provider-gaps"],
    queryFn: fetchProviderGapAlerts,
  });

  const ppiPulse = usePulse("PPI_RECALCULATED", "VERIFICATION_COMPLETE");
  const tracerPulse = usePulse("TRACER_SENT", "TRACER_MISSED", "FOLLOWUP_RESPONDED");
  const traineePulse = usePulse("TRAINEE_ENROLLED", "TRAINEES_IMPORTED");

  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [enrolOpen, setEnrolOpen] = useState(false);
  const [enrolResult, setEnrolResult] = useState<string | null>(null);
  const [certifyingId, setCertifyingId] = useState<string | null>(null);

  const certify = async (traineeId: string) => {
    setCertifyingId(traineeId);
    try {
      await api.patch(`/provider/trainees/${traineeId}/certify`, {});
      await queryClient.invalidateQueries();
    } finally {
      setCertifyingId(null);
    }
  };

  const rows = (trainees.data ?? []).filter((row) => {
    if (statusFilter !== "ALL" && row.status !== statusFilter) {
      return false;
    }
    if (search) {
      const needle = search.toLowerCase();
      if (!`${row.name} ${row.email}`.toLowerCase().includes(needle)) {
        return false;
      }
    }
    return true;
  });

  return (
    <DashboardShell
      role="PROVIDER"
      headline="Centre Command"
      subheading="Enrol, certify and trace — with your PPI always in view."
    >
      <OnboardingTour role="PROVIDER" />

      <section id="overview" aria-label="Key indicators" className="scroll-mt-24">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {overview.data ? (
            <>
              <KpiCard icon={Radar} label="Enrolled" value={overview.data.enrolled} />
              <KpiCard icon={Radar} label="Certified" value={overview.data.certified} />
              <KpiCard
                icon={Radar}
                label="Consent rate"
                value={`${Math.round(overview.data.consent_rate * 100)}%`}
              />
              <KpiCard
                icon={Radar}
                label="Response rate"
                value={`${Math.round(overview.data.response_rate * 100)}%`}
              />
              <KpiCard
                icon={Radar}
                label="Placement rate"
                value={`${Math.round(overview.data.placement_rate * 100)}%`}
              />
              <PulseCard pulsing={ppiPulse}>
                <Card className="h-full border-primary/40">
                  <CardContent className="pt-6">
                    <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      PPI · rank {overview.data.ppi_rank}/{overview.data.total_centres}
                    </p>
                    <p className="mt-1 font-display text-3xl font-semibold text-primary">
                      {overview.data.ppi_score.toFixed(1)}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      live — recalculates on verification
                    </p>
                  </CardContent>
                </Card>
              </PulseCard>
            </>
          ) : overview.isError ? (
            <p className="text-sm text-destructive">Could not load the overview.</p>
          ) : (
            Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-28" />)
          )}
        </div>
      </section>

      <section id="trainees" aria-label="Trainees" className="scroll-mt-24">
        <PulseCard pulsing={traineePulse}>
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="font-display text-xl">Trainees</CardTitle>
                <CardDescription>
                  {traineePulse
                    ? "Just updated — new activity received."
                    : "Your centre roster."}
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" onClick={() => setEnrolOpen(true)}>
                  Enrol trainee
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => downloadCsv("trainees.csv", (trainees.data ?? []) as unknown as Record<string, unknown>[])}
                  disabled={(trainees.data?.length ?? 0) === 0}
                >
                  Export CSV
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-4 flex flex-wrap gap-2">
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search name or email…"
                  aria-label="Filter trainees"
                  className="max-w-xs"
                />
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  aria-label="Filter by status"
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                >
                  {["ALL", "ENROLLED", "CERTIFIED", "DROPPED"].map((option) => (
                    <option key={option} value={option}>
                      {option === "ALL" ? "All statuses" : option}
                    </option>
                  ))}
                </select>
              </div>

              {trainees.isPending ? (
                <Skeleton className="h-48 w-full" />
              ) : rows.length === 0 ? (
                <EmptyState icon={Radar} title="No trainees match" hint="Adjust the filters." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th scope="col" className="py-2 pr-3">
                          Name
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          Course
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          Status
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          Consent
                        </th>
                        <th scope="col" className="py-2">
                          Action
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.id} className="border-b border-border/50 last:border-0">
                          <td className="py-2 pr-3 font-medium">{row.name}</td>
                          <td className="py-2 pr-3 text-muted-foreground">{row.course_title}</td>
                          <td className="py-2 pr-3">{row.status}</td>
                          <td className="py-2 pr-3">{row.consent_active ? "Granted" : "—"}</td>
                          <td className="py-2">
                            {row.status === "ENROLLED" && (
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={certifyingId === row.id}
                                onClick={() => certify(row.id)}
                              >
                                {certifyingId === row.id ? "Certifying…" : "Certify"}
                              </Button>
                            )}
                            {row.status === "CERTIFIED" && (
                              <span title="certified">✓</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </PulseCard>

        {enrolOpen && (
          <EnrolDialog
            courses={courses.data ?? []}
            onClose={() => setEnrolOpen(false)}
            onDone={(message) => {
              setEnrolResult(message);
              void queryClient.invalidateQueries();
            }}
          />
        )}
        {enrolResult && (
          <p role="status" className="rounded-md bg-secondary/60 px-3 py-2 text-sm">
            {enrolResult}
          </p>
        )}
      </section>

      <section id="followups" aria-label="Follow-up queue" className="scroll-mt-24">
        <PulseCard pulsing={tracerPulse}>
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl">Follow-up queue</CardTitle>
              <CardDescription>
                {tracerPulse
                  ? "Updated in real time."
                  : "Tracers due soon and overdue ones — consent-gated."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {followups.isPending || !followups.data ? (
                <Skeleton className="h-32 w-full" />
              ) : (
                <div className="space-y-4">
                  <QueueList title="Overdue" items={followups.data.overdue} highlight />
                  <QueueList title="Due this week" items={followups.data.due_soon} />
                  <QueueList
                    title="Manual review (low-confidence replies)"
                    items={followups.data.manual_review}
                    manual
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </PulseCard>
      </section>

      <section id="insights" aria-label="Insights" className="scroll-mt-24">
        <Card>
          <CardHeader>
            <CardTitle className="font-display text-xl">Outcomes by milestone</CardTitle>
            <CardDescription>
              Employment retention reported at each checkpoint.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {overview.data ? (
              <OutcomesBar
                data={[
                  { milestone: "3 months", rate: overview.data.retention_3m },
                  { milestone: "6 months", rate: overview.data.retention_6m },
                  { milestone: "12 months", rate: overview.data.retention_12m },
                ]}
              />
            ) : (
              <Skeleton className="h-64 w-full" />
            )}
          </CardContent>
        </Card>
      </section>

      <section aria-label="Curriculum gap alerts" className="scroll-mt-24">
        <Card>
          <CardHeader>
            <CardTitle className="font-display text-xl">Curriculum gap alerts</CardTitle>
            <CardDescription>
              Courses whose skills fall behind district demand — from the AI matcher.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {gaps.isPending || !gaps.data ? (
              <Skeleton className="h-24 w-full" />
            ) : gaps.data.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No curriculum gaps detected for your centre&apos;s courses.
              </p>
            ) : (
              <ul className="space-y-3">
                {gaps.data.slice(0, 4).map((row) => (
                  <li key={row.course_id} className="rounded-md border border-border p-3">
                    <p className="flex items-center justify-between text-sm font-medium">
                      {row.title}
                      <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
                        gap {row.gap_score.toFixed(2)}
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Missing:{" "}
                      {row.missing_in_demand_skills.map((m) => m.skill).join(", ") || "—"}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>
    </DashboardShell>
  );
}

function QueueList({
  title,
  items,
  highlight,
  manual,
}: {
  title: string;
  items: FollowupItem[];
  highlight?: boolean;
  manual?: boolean;
}) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">
        {title}
        <span className="ml-1 rounded-full bg-muted px-2 py-0.5 text-xs font-normal text-muted-foreground">
          {items.length}
        </span>
      </h3>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nothing here right now.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.followup_id}
              className={
                highlight
                  ? "rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm"
                  : "rounded-md border border-border px-3 py-2 text-sm"
              }
            >
              <span className="font-medium">{item.trainee_name}</span>
              <span className="text-muted-foreground">
                {" · "}
                {item.milestone} · due {item.due_on} · {item.channel}
              </span>
              {manual && item.raw_text && (
                <p className="mt-1 text-xs text-muted-foreground">raw: {item.raw_text}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EnrolDialog({
  courses,
  onClose,
  onDone,
}: {
  courses: { id: string; title: string }[];
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: "", email: "", phone: "", course_id: "" });
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (formEvent: React.FormEvent<HTMLFormElement>) => {
    formEvent.preventDefault();
    if (!form.course_id) {
      setError("Select a course.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.post<{ temporary_password: string }>(
        "/provider/trainees",
        form,
      );
      setTempPassword(result.temporary_password);
      onDone("Trainee enrolled.");
      void queryClient.invalidateQueries();
    } catch (enrolError) {
      setError(
        enrolError instanceof Error && enrolError.message.includes("exists")
          ? "An account with this email already exists."
          : "Could not enrol this trainee. Check the details and try again.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Enrol trainee"
    >
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="font-display text-xl">Enrol trainee</CardTitle>
          <CardDescription>
            Creates the account and profile. A one-time temporary password is shown after.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tempPassword ? (
            <div className="space-y-3">
              <p className="rounded-md border border-primary/30 bg-secondary/50 p-3 text-sm">
                Temporary password (shown once, hand it to the trainee):
                <span className="ml-1 font-mono font-semibold">{tempPassword}</span>
              </p>
              <Button onClick={onClose}>Done</Button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-3">
              <Input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Full name"
                aria-label="Full name"
                required
              />
              <Input
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                placeholder="Email"
                type="email"
                aria-label="Email"
                required
              />
              <Input
                value={form.phone}
                onChange={(event) => setForm({ ...form, phone: event.target.value })}
                placeholder="Phone"
                aria-label="Phone"
                required
              />
              <select
                value={form.course_id}
                onChange={(event) => setForm({ ...form, course_id: event.target.value })}
                aria-label="Course"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                required
              >
                <option value="">Select a course…</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.title}
                  </option>
                ))}
              </select>
              {error && (
                <p
                  role="alert"
                  className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  {error}
                </p>
              )}
              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={onClose}>
                  Cancel
                </Button>
                <Button type="submit" disabled={submitting}>
                  Enrol
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

```

---

## `apps/web/src/app/dashboard/trainee/page.tsx`

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCheck,
  GraduationCap,
  Loader2,
  MapPin,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import { useState } from "react";

import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { EmptyState, KpiCard, PulseCard } from "@/components/dashboard/kpi-card";
import { MessagesPanel } from "@/components/trainee/messages-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePulse } from "@/hooks/use-pulse";
import { DashboardShell } from "@/components/dashboard/app-shell";
import { api, assessSkills } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { UserRole } from "@/types/api";

interface MeResponse {
  profile: {
    id: string;
    name: string | null;
    district: string;
    gender: string;
    enrolled_on: string;
    certified_on: string | null;
    status: string;
    course_title: string | null;
  };
  consents: { channel: string; granted: boolean; active: boolean; version: string }[];
  employment: {
    employment_record_id: string;
    status: string;
    job_title: string | null;
    monthly_wage: number | null;
    started_on: string | null;
    trainee_signal: string | null;
    employer_signal: string | null;
    verified: boolean;
  } | null;
  timeline: { date: string; type: string; title: string; detail: string | null }[];
  upcoming: {
    followup_id: string;
    milestone: string;
    due_on: string;
    channel: string;
    state: string;
    message: string;
  }[];
}

interface AssessmentResult {
  profile: { skill: string; sector: string; confidence: number }[];
  role_matches: {
    title: string;
    sector: string;
    score: number;
    explanation: string;
  }[];
}

export default function TraineeDashboard() {
  const me = useQuery({
    queryKey: ["trainee-me"],
    queryFn: async () => {
      const { api } = await import("@/lib/api");
      return api.get<MeResponse>("/trainee/me");
    },
  });

  return (
    <DashboardShell
      role="TRAINEE"
      headline="My Journey"
      subheading="Your consent, tracers and outcomes — all in one place."
    >
      {me.isPending ? (
        <div className="space-y-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : me.isError ? (
        <EmptyState
          icon={GraduationCap}
          title="No trainee profile yet"
          hint="Profiles are created when a centre enrols you in a course."
        />
      ) : (
        <TraineeContent me={me.data} />
      )}
    </DashboardShell>
  );
}

function TraineeContent({ me }: { me: MeResponse }) {
  const verificationPulse = usePulse("VERIFICATION_COMPLETE", "EMPLOYMENT_SELF_REPORTED");
  const consentPulse = usePulse("CONSENT_GRANTED", "CONSENT_REVOKED");

  return (
    <>
      <section id="journey" aria-label="My journey" className="scroll-mt-24">
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <PulseCard pulsing={verificationPulse}>
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="font-display text-xl">Journey timeline</CardTitle>
                <CardDescription>
                  {me.profile.status === "CERTIFIED"
                    ? `Certified ${me.profile.certified_on ?? ""} — milestones follow.`
                    : `Enrolled ${me.profile.enrolled_on} — certification to come.`}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ol className="relative space-y-4 border-l border-border pl-5">
                  {me.timeline.map((item, index) => (
                    <li key={`${item.type}-${item.date}-${index}`} className="relative">
                      <span
                        aria-hidden
                        className="absolute -left-[1.55rem] top-1 h-2.5 w-2.5 rounded-full border-2 border-primary bg-background"
                      />
                      <p className="text-xs text-muted-foreground">{item.date}</p>
                      <p className="text-sm font-medium">{item.title}</p>
                      {item.detail && (
                        <p className="text-xs text-muted-foreground">{item.detail}</p>
                      )}
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </PulseCard>

          <div className="space-y-6">
            <PulseCard pulsing={verificationPulse}>
              <Card>
                <CardHeader>
                  <CardTitle className="font-display text-lg">Verification status</CardTitle>
                  <CardDescription>Dual-signal: you + your employer</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <SignalRow
                    label="Your signal"
                    signal={me.employment?.trainee_signal ?? "PENDING"}
                  />
                  <SignalRow
                    label="Employer signal"
                    signal={me.employment?.employer_signal ?? "PENDING"}
                  />
                  <div className="flex items-center justify-between text-sm font-medium">
                    <span>Verified outcome</span>
                    {me.employment?.verified ? (
                      <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                        <CheckCheck className="h-4 w-4" aria-hidden /> Verified
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Awaiting both signals</span>
                    )}
                  </div>
                </CardContent>
              </Card>
            </PulseCard>

            <KpiCard
              icon={MapPin}
              label="District"
              value={me.profile.district}
              hint={me.profile.course_title ?? undefined}
            />
          </div>
        </div>
      </section>

      <section id="consent" aria-label="Consent manager" className="scroll-mt-24">
        <ConsentManager consents={me.consents} />
      </section>

      <section id="messages" aria-label="Messages" className="scroll-mt-24">
        <MessagesPanel />
      </section>

      <section id="employment" aria-label="Employment" className="scroll-mt-24">
        <EmploymentCard me={me} />
      </section>

      <section id="skills" aria-label="AI skills" className="scroll-mt-24">
        <SkillsCard />
      </section>
    </>
  );
}

function SignalRow({ label, signal }: { label: string; signal: string }) {
  const styles =
    signal === "CONFIRMED"
      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
      : signal === "DISPUTED"
        ? "bg-destructive/10 text-destructive"
        : "bg-muted text-muted-foreground";
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles}`}>
        {signal}
      </span>
    </div>
  );
}

function ConsentManager({ consents }: { consents: MeResponse["consents"] }) {
  const consentPulse = usePulse("CONSENT_GRANTED", "CONSENT_REVOKED");
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<string | null>(null);
  const channels = ["WHATSAPP", "IVR", "SMS"];

  const toggle = useMutation({
    mutationFn: async ({ channel, granted }: { channel: string; granted: boolean }) => {
      await api.post("/trainee/consent", { channel, granted });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trainee-me"] }),
  });

  return (
    <PulseCard pulsing={consentPulse}>
      <Card>
        <CardHeader>
          <CardTitle className="font-display text-xl">Consent manager</CardTitle>
          <CardDescription>
            Version-stamped per channel. Revoking cancels undelivered tracers — no consent, no
            tracing.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {channels.map((channel) => {
            const current = consents.find((item) => item.channel === channel);
            const active = current?.active ?? false;
            return (
              <div
                key={channel}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2.5"
              >
                <div>
                  <p className="text-sm font-medium">
                    {channel.charAt(0) + channel.slice(1).toLowerCase()}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {current
                      ? active
                        ? "Active — tracers may use this channel"
                        : current.granted
                          ? "Revoked"
                          : "Declined"
                      : "No decision yet"}
                    {current ? ` · v${current.version}` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={active}
                  aria-label={`${active ? "Revoke" : "Grant"} ${channel} consent`}
                  disabled={pending === channel || toggle.isPending}
                  onClick={() => {
                    setPending(channel);
                    toggle.mutate(
                      { channel, granted: !active },
                      { onSettled: () => setPending(null) },
                    );
                  }}
                  className={cn(
                    "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
                    active ? "bg-primary" : "bg-muted-foreground/40",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
                      active ? "translate-x-5" : "translate-x-0.5",
                    )}
                  />
                </button>
              </div>
            );
          })}
          {toggle.isPending && (
            <p className="text-xs text-muted-foreground" role="status">
              <Loader2 className="mr-1 inline h-3 w-3 animate-spin" aria-hidden />
              Saving consent…
            </p>
          )}
        </CardContent>
      </Card>
    </PulseCard>
  );
}

function EmploymentCard({ me }: { me: MeResponse }) {
  const wagePulse = usePulse("EMPLOYMENT_SELF_REPORTED");
  const queryClient = useQueryClient();
  const employment = me.employment;
  const [jobTitle, setJobTitle] = useState(employment?.job_title ?? "");
  const [wage, setWage] = useState(
    employment?.monthly_wage ? String(employment.monthly_wage) : "",
  );
  const [saved, setSaved] = useState(false);

  const report = useMutation({
    mutationFn: async () => {
      const { reportEmployment } = await import("@/lib/api");
      return reportEmployment({
        employment_status: "EMPLOYED",
        job_title: jobTitle.trim(),
        monthly_wage: Number(wage),
      });
    },
    onSuccess: () => {
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["trainee-me"] });
    },
  });

  if (me.profile.status !== "CERTIFIED") {
    return null;
  }

  return (
    <PulseCard pulsing={wagePulse}>
      <Card>
        <CardHeader>
          <CardTitle className="font-display text-xl">Employment &amp; wage</CardTitle>
          <CardDescription>
            {employment
              ? `Started ${employment.started_on ?? "—"} · ${employment.status}`
              : "Add your current role and wage to start the verification chain."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <form
            onSubmit={(formEvent) => {
              formEvent.preventDefault();
              report.mutate();
            }}
            className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end"
          >
            <div className="space-y-2">
              <Input
                value={jobTitle}
                onChange={(event) => setJobTitle(event.target.value)}
                placeholder="Job title"
                aria-label="Job title"
                required
                minLength={2}
              />
              <Input
                value={wage}
                onChange={(event) => setWage(event.target.value)}
                placeholder="Monthly wage"
                aria-label="Monthly wage"
                type="number"
                min={0}
                required
              />
            </div>
            <Button type="submit" disabled={report.isPending}>
              {report.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Wallet className="h-4 w-4" aria-hidden />
              )}
              {employment ? "Update" : "Add"}
            </Button>
          </form>
          {report.isSuccess && (
            <p role="status" className="text-xs text-muted-foreground">
              Saved — your employer signal is pending confirmation.
            </p>
          )}
          {report.isError && (
            <p role="alert" className="text-xs text-destructive">
              Could not save. Please try again.
            </p>
          )}
        </CardContent>
      </Card>
    </PulseCard>
  );
}

function SkillsCard() {
  const assessment = useQuery({
    queryKey: ["trainee-assessment"],
    queryFn: () => assessSkills({}),
    staleTime: 5 * 60 * 1000,
  });

  const radarData = (assessment.data?.profile ?? []).slice(0, 8);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl">AI skill profile</CardTitle>
        <CardDescription>
          Confidence per skill (0–1) and the closest job-role matches.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {assessment.isPending ? (
          <Skeleton className="h-64 w-full" />
        ) : radarData.length === 0 ? (
          <EmptyState
            icon={GraduationCap}
            title="No skills detected yet"
            hint="Skills come from your assigned course."
          />
        ) : (
          <>
            <div
              className="h-72 w-full"
              role="img"
              aria-label="Radar chart of skill confidence"
            >
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData} outerRadius="80%">
                  <PolarGrid stroke="hsl(var(--border))" />
                  <PolarAngleAxis
                    dataKey="skill"
                    tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                  />
                  <Radar dataKey="confidence" stroke="#2f8f8c" fill="#2f8f8c" fillOpacity={0.35} />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: 8,
                      color: "hsl(var(--card-foreground))",
                    }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold">Closest job roles</h3>
              <ul className="space-y-2">
                {(assessment.data?.role_matches ?? []).slice(0, 5).map((match) => (
                  <li key={match.title} className="rounded-md border border-border p-3 text-sm">
                    <p className="flex items-center justify-between font-medium">
                      {match.title}
                      <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
                        {match.score.toFixed(2)}
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">{match.explanation}</p>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

```

---

## `apps/web/src/app/dashboard/employer/page.tsx`

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, Loader2, X } from "lucide-react";
import { useState } from "react";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { EmptyState, KpiCard, PulseCard } from "@/components/dashboard/kpi-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePulse } from "@/hooks/use-pulse";
import { DashboardShell } from "@/components/dashboard/app-shell";
import {
  fetchEmployerImpact,
  fetchTalentPool,
  fetchVerifications,
  markConfirmed,
  markDisputed,
} from "@/lib/api";

interface VerificationRow {
  verification_id: string;
  trainee_name: string;
  employment_status: string;
  job_title: string | null;
  monthly_wage: number | null;
  trainee_signal: string;
}

export default function EmployerDashboard() {
  return (
    <DashboardShell
      role="EMPLOYER"
      headline="Verify & Hire"
      subheading="Confirm the claims that name your company — verified outcomes count."
    >
      <OnboardingTour role="EMPLOYER" />
      <EmployerContent />
    </DashboardShell>
  );
}

function EmployerContent() {
  const verifications = useQuery({
    queryKey: ["employer-verifications"],
    queryFn: () => fetchVerifications(),
  });
  const impact = useQuery({ queryKey: ["employer-impact"], queryFn: fetchEmployerImpact });

  const verifyPulse = usePulse("FOLLOWUP_RESPONDED", "EMPLOYMENT_SELF_REPORTED");
  const completePulse = usePulse("VERIFICATION_COMPLETE", "VERIFICATION_DISPUTED");
  const [disputingId, setDisputingId] = useState<string | null>(null);

  const pending = verifications.data ?? [];
  const confirmed = pending.filter((row) => row.trainee_signal === "CONFIRMED");

  return (
    <>
      <section id="verify" aria-label="Verification queue" className="scroll-mt-24">
        <PulseCard pulsing={verifyPulse}>
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl">Pending verifications</CardTitle>
              <CardDescription>
                {verifyPulse
                  ? "New claims received in real time."
                  : "Trainees who reported employment at your company."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {verifications.isPending ? (
                <Skeleton className="h-32 w-full" />
              ) : pending.length === 0 ? (
                <EmptyState
                  icon={CheckCheck}
                  title="No pending claims"
                  hint="New claims appear here the moment a trainee names your company."
                />
              ) : (
                <ul className="space-y-3">
                  {pending.map((row) => (
                    <li key={row.verification_id} className="rounded-md border border-border p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="text-sm font-medium">{row.trainee_name}</p>
                          <p className="text-xs text-muted-foreground">
                            {row.job_title ?? row.employment_status}
                            {row.monthly_wage
                              ? ` · ${row.monthly_wage.toLocaleString("en-GB")} monthly`
                              : ""}
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <ConfirmButton verificationId={row.verification_id} />
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setDisputingId(row.verification_id)}
                          >
                            Dispute
                          </Button>
                        </div>
                      </div>
                      <p className="mt-2">
                        <SignalBadge signal={row.trainee_signal} />
                      </p>
                      {disputingId === row.verification_id && (
                        <DisputeDialog
                          verificationId={row.verification_id}
                          onClose={() => setDisputingId(null)}
                        />
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </PulseCard>
      </section>

      <section id="hires" aria-label="Hires" className="scroll-mt-24">
        <PulseCard pulsing={completePulse}>
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl">Your hires</CardTitle>
              <CardDescription>
                Verified: {impact.data?.verified_hires ?? 0} of {impact.data?.hires ?? 0} ·
                working: {impact.data?.working ?? 0}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {impact.isPending ? (
                <Skeleton className="h-24 w-full" />
              ) : confirmed.length === 0 ? (
                <EmptyState
                  icon={CheckCheck}
                  title="No verified hires yet"
                  hint="Confirm a pending claim to move it here."
                />
              ) : (
                <ul className="space-y-2">
                  {confirmed.map((row) => (
                    <li
                      key={row.verification_id}
                      className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
                    >
                      <span className="font-medium">{row.trainee_name}</span>
                      <span className="text-muted-foreground">{row.job_title ?? "—"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </PulseCard>
      </section>

      <section id="talent" aria-label="Talent pool" className="scroll-mt-24">
        <TalentPoolCard />
      </section>

      <section id="impact" aria-label="Impact" className="scroll-mt-24">
        <PulseCard pulsing={completePulse}>
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl">Retention of your hires</CardTitle>
              <CardDescription>Share of respondents still in work per milestone.</CardDescription>
            </CardHeader>
            <CardContent>
              {impact.isPending ? (
                <Skeleton className="h-20 w-full" />
              ) : (
                <div className="grid gap-4 sm:grid-cols-3">
                  <KpiCard
                    icon={CheckCheck}
                    label="3-month retention"
                    value={`${Math.round((impact.data?.retention_3m ?? 0) * 100)}%`}
                  />
                  <KpiCard
                    icon={CheckCheck}
                    label="6-month retention"
                    value={`${Math.round((impact.data?.retention_6m ?? 0) * 100)}%`}
                  />
                  <KpiCard
                    icon={CheckCheck}
                    label="12-month retention"
                    value={`${Math.round((impact.data?.retention_12m ?? 0) * 100)}%`}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </PulseCard>
      </section>
    </>
  );
}

function ConfirmButton({ verificationId }: { verificationId: string }) {
  const queryClient = useQueryClient();
  const confirm = useMutation({
    mutationFn: () => markConfirmed(verificationId),
    onSuccess: () => queryClient.invalidateQueries(),
  });
  return (
    <Button size="sm" onClick={() => confirm.mutate()} disabled={confirm.isPending}>
      {confirm.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      Confirm
    </Button>
  );
}

function SignalBadge({ signal }: { signal: string }) {
  const styles =
    signal === "CONFIRMED"
      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
      : "bg-muted text-muted-foreground";
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles}`}>{signal}</span>
  );
}

function DisputeDialog({
  verificationId,
  onClose,
}: {
  verificationId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const dispute = useMutation({
    mutationFn: async () => {
      const { markDisputed } = await import("@/lib/api");
      return markDisputed(verificationId, reason);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries();
      onClose();
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Dispute claim"
    >
      <Card className="w-full max-w-md">
        <CardHeader className="flex-row items-start justify-between space-y-0">
          <div>
            <CardTitle className="font-display text-lg">Dispute this claim</CardTitle>
            <CardDescription>The trainee and admins will see your reason.</CardDescription>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-muted-foreground hover:bg-accent"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </CardHeader>
        <CardContent>
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            minLength={3}
            required
            aria-label="Dispute reason"
            placeholder="Why are you disputing this claim?"
            className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => dispute.mutate()}
              disabled={dispute.isPending || reason.trim().length < 3}
            >
              {dispute.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              Submit dispute
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function TalentPoolCard() {
  const [skill, setSkill] = useState("");
  const [district, setDistrict] = useState("");
  const [submitted, setSubmitted] = useState<{ skill: string; district: string }>({
    skill: "",
    district: "",
  });

  const pool = useQuery({
    queryKey: ["talent-pool", submitted],
    queryFn: () => fetchTalentPool(submitted.skill, submitted.district),
    enabled: false,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl">Talent pool</CardTitle>
        <CardDescription>Certified trainees with active consent, grouped by skill.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          onSubmit={(formEvent) => {
            formEvent.preventDefault();
            setSubmitted({ skill, district });
          }}
          className="flex flex-wrap gap-2"
        >
          <Input
            value={skill}
            onChange={(event) => setSkill(event.target.value)}
            placeholder="Skill (optional)"
            aria-label="Skill filter"
            className="max-w-[12rem]"
          />
          <Input
            value={district}
            onChange={(event) => setDistrict(event.target.value)}
            placeholder="District (optional)"
            aria-label="District filter"
            className="max-w-[12rem]"
          />
          <Button type="submit" variant="outline" size="sm">
            Search
          </Button>
        </form>

        {pool.isFetching ? (
          <Skeleton className="h-32 w-full" />
        ) : (pool.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No consented trainees match — press Search to query the pool.
          </p>
        ) : (
          <ul className="space-y-2">
            {(pool.data ?? []).map((row) => (
              <li
                key={row.skill}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
              >
                <div>
                  <p className="font-medium">{row.skill}</p>
                  <p className="text-xs text-muted-foreground">
                    {row.districts.join(", ")} · {row.trainee_names.join(", ")}
                  </p>
                </div>
                <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-semibold text-secondary-foreground">
                  {row.trainee_count} · match {row.match_score.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

```

---

## `apps/web/src/app/dashboard/admin/page.tsx`

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  Loader2,
  MapPin,
  RadioTower,
  RotateCcw,
  TrendingUp,
} from "lucide-react";
import { useState } from "react";

import { OnboardingTour } from "@/components/auth/onboarding-tour";
import { EmptyState, KpiCard, PulseCard } from "@/components/dashboard/kpi-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { usePulse } from "@/hooks/use-pulse";
import { DashboardShell } from "@/components/dashboard/app-shell";
import {
  fetchAdminOverview,
  fetchAdminProviders,
  fetchEvents,
  resetDemoData,
  runTracerNow,
  submitAllocation,
} from "@/lib/api";
import { downloadCsv, printSection } from "@/lib/export";

interface AdminOverview {
  trainees: number;
  certified: number;
  placed: number;
  employment_rate: number;
  retention_3m: number;
  retention_6m: number;
  retention_12m: number;
  median_wage_uplift: number;
  self_employment_share: number;
  verification_rate: number;
  demo_mode?: boolean;
  districts: {
    district: string;
    trainees: number;
    certified: number;
    working: number;
    employment_rate: number;
  }[];
}

interface LeaderboardRow {
  centre_id: string;
  centre_name: string;
  district: string;
  rank: number;
  ppi_score: number;
  placement_rate: number;
  verification_rate: number;
}

export default function AdminDashboard() {
  return (
    <DashboardShell
      role="ADMIN"
      headline="Governance"
      subheading="State-wide evidence for allocations, flags and curriculum design."
    >
      <OnboardingTour role="ADMIN" />
      <AdminContent />
    </DashboardShell>
  );
}

function AdminContent() {
  const queryClient = useQueryClient();
  const overview = useQuery({ queryKey: ["admin-overview"], queryFn: fetchAdminOverview });
  const providers = useQuery({ queryKey: ["admin-providers"], queryFn: fetchAdminProviders });
  const events = useQuery({
    queryKey: ["admin-events"],
    queryFn: () => fetchEvents(100),
    refetchInterval: 20_000,
  });

  const kpiPulse = usePulse("VERIFICATION_COMPLETE", "PPI_RECALCULATED");
  const leaderPulse = usePulse("PPI_RECALCULATED");
  const feedPulse = usePulse(
    "TRACER_SENT",
    "TRACER_MISSED",
    "VERIFICATION_COMPLETE",
    "FUND_ALLOCATED",
    "FLAG_RAISED",
    "TRAINEE_ENROLLED",
  );
  const flagPulse = usePulse("FLAG_RAISED");

  const [selectedCentre, setSelectedCentre] = useState<string | null>(null);
  const [tracerResult, setTracerResult] = useState<string | null>(null);
  const [resetResult, setResetResult] = useState<string | null>(null);

  const runTracer = useMutation({
    mutationFn: runTracerNow,
    onSuccess: (result) => {
      setTracerResult(
        `Delivered ${result.sent_count} tracer(s), fast-forwarded ${result.fast_forwarded}.`,
      );
      void queryClient.invalidateQueries();
    },
    onError: () => setTracerResult("Tracer cycle failed. Please try again."),
  });

  const resetData = useMutation({
    mutationFn: resetDemoData,
    onSuccess: (result) => {
      setResetResult(`Sample data regenerated (${result.users} accounts).`);
      void queryClient.invalidateQueries();
    },
    onError: () => setResetResult("Reset failed. Please try again."),
  });

  const flagEvents = (events.data ?? []).filter(
    (event) => event.type === "FLAG_RAISED",
  );

  return (
    <>
      <section id="governance" aria-label="Governance KPIs" className="scroll-mt-24">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {overview.data ? (
            <>
              <KpiCard
                icon={TrendingUp}
                label="Employment rate"
                value={`${Math.round(overview.data.employment_rate * 100)}%`}
                hint={`of ${overview.data.certified} certified`}
              />
              <KpiCard
                icon={TrendingUp}
                label="Verified"
                value={`${Math.round(overview.data.verification_rate * 100)}%`}
                hint="dual-signal confirmed"
              />
              <KpiCard
                icon={TrendingUp}
                label="Self-employed"
                value={`${Math.round(overview.data.self_employment_share * 100)}%`}
              />
              <KpiCard
                icon={TrendingUp}
                label="Wage uplift (median)"
                value={`${Math.round(overview.data.median_wage_uplift * 100)}%`}
                hint="M3 to M12 growth"
              />
            </>
          ) : overview.isError ? (
            <p className="text-sm text-destructive">Could not load the overview.</p>
          ) : (
            Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-24" />
            ))
          )}
        </div>

        <PulseCard pulsing={kpiPulse} className="mt-6">
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="font-display text-lg">District heat map</CardTitle>
                <CardDescription>
                  Colour = employment rate. Retention R3{" "}
                  {Math.round((overview.data?.retention_3m ?? 0) * 100)}% · R6{" "}
                  {Math.round((overview.data?.retention_6m ?? 0) * 100)}% · R12{" "}
                  {Math.round((overview.data?.retention_12m ?? 0) * 100)}%
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => printSection("print-summary")}
                disabled={overview.isPending}
              >
                Export PDF (print)
              </Button>
            </CardHeader>
            <CardContent>
              {overview.data ? (
                <>
                  <div
                    className="grid grid-cols-2 gap-3 sm:grid-cols-4"
                    aria-label="District heat map"
                  >
                    {overview.data.districts.map((district) => {
                      const rate = district.employment_rate;
                      const shade =
                        rate >= 0.7
                          ? "bg-brand-600 text-white"
                          : rate >= 0.5
                            ? "bg-brand-400 text-white"
                            : rate >= 0.3
                              ? "bg-marigold-300 text-marigold-950"
                              : "bg-muted text-muted-foreground";
                      return (
                        <div
                          key={district.district}
                          title={`${district.district}: ${Math.round(rate * 100)}% employment`}
                          className={`rounded-lg p-4 text-center ${shade}`}
                        >
                          <MapPin className="mx-auto h-4 w-4 opacity-70" aria-hidden />
                          <p className="mt-1 text-xs font-medium">{district.district}</p>
                          <p className="font-display text-xl font-semibold">
                            {Math.round(rate * 100)}%
                          </p>
                          <p className="text-[10px] opacity-80">
                            {district.working}/{district.certified} placed
                          </p>
                        </div>
                      );
                    })}
                  </div>
                  <div id="print-summary" className="hidden print:block">
                    <h3>TrackSkill AI — governance summary (sample data)</h3>
                    <p>
                      Employment rate {Math.round(overview.data.employment_rate * 100)}%;
                      verification {Math.round(overview.data.verification_rate * 100)}%; median
                      wage uplift {Math.round(overview.data.median_wage_uplift * 100)}%.
                    </p>
                    <ul>
                      {overview.data.districts.map((district) => (
                        <li key={district.district}>
                          {district.district}: {district.working}/{district.certified} placed (
                          {Math.round(district.employment_rate * 100)}%)
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              ) : (
                <Skeleton className="h-40 w-full" />
              )}
            </CardContent>
          </Card>
        </PulseCard>
      </section>

      <section id="providers" aria-label="PPI leaderboard" className="scroll-mt-24">
        <PulseCard pulsing={leaderPulse}>
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="font-display text-xl">
                  Provider Performance Index
                </CardTitle>
                <CardDescription>
                  {leaderPulse ? "Recalculated in real time." : "Ranked best-first."}
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  downloadCsv(
                    "ppi-leaderboard.csv",
                    (providers.data ?? []) as unknown as Record<string, unknown>[],
                  )
                }
                disabled={(providers.data?.length ?? 0) === 0}
              >
                Export CSV
              </Button>
            </CardHeader>
            <CardContent>
              {providers.isPending ? (
                <Skeleton className="h-48 w-full" />
              ) : (providers.data?.length ?? 0) === 0 ? (
                <EmptyState icon={BarChart3} title="No centres yet" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th scope="col" className="py-2 pr-3">
                          #
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          Centre
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          PPI
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          Placement
                        </th>
                        <th scope="col" className="py-2">
                          Verification
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {(providers.data ?? []).map((row) => (
                        <tr
                          key={row.centre_id}
                          className="border-b border-border/50 last:border-0"
                        >
                          <td className="py-2 pr-3 font-semibold">{row.rank}</td>
                          <td className="py-2 pr-3">
                            <button
                              type="button"
                              onClick={() =>
                                setSelectedCentre(
                                  selectedCentre === row.centre_id ? null : row.centre_id,
                                )
                              }
                              className="text-left font-medium underline-offset-4 hover:underline"
                            >
                              {row.centre_name}
                            </button>
                            <span className="block text-xs text-muted-foreground">
                              {row.district}
                            </span>
                          </td>
                          <td className="py-2 pr-3 font-display font-semibold text-primary">
                            {row.ppi_score.toFixed(1)}
                          </td>
                          <td className="py-2 pr-3">
                            {Math.round(row.placement_rate * 100)}%
                          </td>
                          <td className="py-2">
                            {Math.round(row.verification_rate * 100)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <details className="mt-4 rounded-md border border-border p-3 text-sm">
                <summary className="cursor-pointer font-medium">
                  How is this score calculated?
                </summary>
                <p className="mt-2 leading-relaxed text-muted-foreground">
                  PPI = 100 × (0.30·placement + 0.25·retention_weighted + 0.20·wage_growth_norm +
                  0.15·verification + 0.10·response), where retention_weighted = 0.2·R3 + 0.3·R6 +
                  0.5·R12. Verified outcomes count fully; unverified ones at half weight. It
                  recalculates on every completed verification.
                </p>
              </details>
            </CardContent>
          </Card>
        </PulseCard>

        {selectedCentre && (
          <CentreDrillDown centreId={selectedCentre} onClose={() => setSelectedCentre(null)} />
        )}
      </section>

      <section id="funds" aria-label="Fund allocation" className="scroll-mt-24">
        <Card>
          <CardHeader>
            <CardTitle className="font-display text-xl">Fund allocation</CardTitle>
            <CardDescription>
              Pick a centre — the recommended amount is prefilled from its latest PPI.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {(providers.data?.length ?? 0) > 0 ? (
              <AllocationForm
                centres={(providers.data ?? []).map((row) => ({
                  id: row.centre_id,
                  name: row.centre_name,
                  ppi: row.ppi_score,
                }))}
                onDone={() => void queryClient.invalidateQueries()}
              />
            ) : (
              <Skeleton className="h-32 w-full" />
            )}
          </CardContent>
        </Card>
      </section>

      <section id="gaps" aria-label="Curriculum-demand gaps" className="scroll-mt-24">
        <GapMatrixCard />
      </section>

      <section id="activity" aria-label="Activity and anomalies" className="scroll-mt-24">
        <div className="grid gap-6 lg:grid-cols-2">
          <PulseCard pulsing={feedPulse}>
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="font-display text-xl">Live activity feed</CardTitle>
                <CardDescription>Audit trail from the events stream.</CardDescription>
              </CardHeader>
              <CardContent>
                {events.isPending ? (
                  <Skeleton className="h-48 w-full" />
                ) : (events.data?.length ?? 0) === 0 ? (
                  <EmptyState icon={RadioTower} title="No activity yet" />
                ) : (
                  <ul className="max-h-72 space-y-2 overflow-y-auto">
                    {(events.data ?? []).map((event) => (
                      <li
                        key={event.id}
                        className="flex items-start justify-between gap-2 rounded-md border border-border/60 px-3 py-2 text-xs"
                      >
                        <span className="font-mono font-semibold">{event.type}</span>
                        <span className="text-muted-foreground">
                          {event.created_at
                            ? event.created_at.slice(0, 19).replace("T", " ")
                            : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </PulseCard>

          <PulseCard pulsing={flagPulse}>
            <Card className="h-full">
              <CardHeader className="flex-row items-start justify-between space-y-0">
                <div>
                  <CardTitle className="font-display text-xl">Anomaly flags</CardTitle>
                  <CardDescription>
                    Wage outliers, date errors, confirmation spikes.
                  </CardDescription>
                </div>
                <AnomalyScanButton />
              </CardHeader>
              <CardContent>
                {flagEvents.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No anomalies flagged yet.</p>
                ) : (
                  <ul className="max-h-64 space-y-2 overflow-y-auto">
                    {flagEvents.map((event) => (
                      <li
                        key={event.id}
                        className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm"
                      >
                        <AlertTriangle
                          className="mt-0.5 h-4 w-4 shrink-0 text-destructive"
                          aria-hidden
                        />
                        <span>{String(event.payload?.summary ?? event.type)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </PulseCard>
        </div>
      </section>

      <section aria-label="Demo controls" className="scroll-mt-24">
        <Card>
          <CardHeader>
            <CardTitle className="font-display text-xl">Demo controls</CardTitle>
            <CardDescription>
              {overview.data?.demo_mode
                ? "These controls are live while DEMO_MODE is enabled."
                : "Disabled — DEMO_MODE is off."}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            <Button
              onClick={() => runTracer.mutate()}
              disabled={runTracer.isPending || !overview.data?.demo_mode}
            >
              {runTracer.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <RadioTower className="h-4 w-4" aria-hidden />
              )}
              Run tracer now
            </Button>
            <Button
              variant="outline"
              onClick={() => resetData.mutate()}
              disabled={resetData.isPending || !overview.data?.demo_mode}
            >
              {resetData.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <RotateCcw className="h-4 w-4" aria-hidden />
              )}
              Reset demo data
            </Button>
            {tracerResult && (
              <p
                role="status"
                className="w-full rounded-md bg-secondary/60 px-3 py-2 text-sm"
              >
                {tracerResult}
              </p>
            )}
            {resetResult && (
              <p
                role="status"
                className="w-full rounded-md bg-secondary/60 px-3 py-2 text-sm"
              >
                {resetResult}
              </p>
            )}
          </CardContent>
        </Card>
      </section>
    </>
  );
}

function AnomalyScanButton() {
  const queryClient = useQueryClient();
  const scan = useMutation({
    mutationFn: async () => {
      const { runAnomalyScan } = await import("@/lib/api");
      return runAnomalyScan();
    },
    onSuccess: () => queryClient.invalidateQueries(),
  });
  return (
    <Button variant="outline" size="sm" onClick={() => scan.mutate()} disabled={scan.isPending}>
      {scan.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      Scan now
    </Button>
  );
}

function AllocationForm({
  centres,
  onDone,
}: {
  centres: { id: string; name: string; ppi: number }[];
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [centreId, setCentreId] = useState(centres[0]?.id ?? "");
  const [amount, setAmount] = useState(
    centres[0] ? String(recommendedAmount(centres[0].ppi)) : "",
  );
  const [rationale, setRationale] = useState("");
  const allocate = useMutation({
    mutationFn: (payload: { centre_id: string; amount: number; rationale: string }) =>
      submitAllocation(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries();
      setRationale("");
    },
  });

  const selected = centres.find((centre) => centre.id === centreId);

  return (
    <form
      onSubmit={(formEvent) => {
        formEvent.preventDefault();
        allocate.mutate({ centre_id: centreId, amount: Number(amount), rationale });
      }}
      className="space-y-3"
    >
      <div className="space-y-2">
        <label htmlFor="alloc-centre" className="text-sm font-medium">
          Centre
        </label>
        <select
          id="alloc-centre"
          value={centreId}
          onChange={(event) => {
            setCentreId(event.target.value);
            const centre = centres.find((item) => item.id === event.target.value);
            if (centre) {
              setAmount(String(recommendedAmount(centre.ppi)));
            }
          }}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
        >
          {centres.map((centre) => (
            <option key={centre.id} value={centre.id}>
              {centre.name} (PPI {centre.ppi.toFixed(1)})
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <label htmlFor="alloc-amount" className="text-sm font-medium">
          Amount
        </label>
        <Input
          id="alloc-amount"
          type="number"
          min={1}
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
        {selected && (
          <p className="text-xs text-muted-foreground">
            Recommended from PPI {selected.ppi.toFixed(1)}:{" "}
            {recommendedAmount(selected.ppi).toLocaleString("en-GB")}
          </p>
        )}
      </div>
      <div className="space-y-2">
        <label htmlFor="alloc-rationale" className="text-sm font-medium">
          Rationale
        </label>
        <Input
          id="alloc-rationale"
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder="Why this centre receives this allocation…"
          required
          minLength={3}
        />
      </div>
      <Button type="submit" disabled={allocate.isPending}>
        {allocate.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
        Allocate funds
      </Button>
      {allocate.isSuccess && (
        <p role="status" className="text-sm text-emerald-600 dark:text-emerald-400">
          Allocation recorded — the provider has been notified.
        </p>
      )}
      {allocate.isError && (
        <p role="alert" className="text-sm text-destructive">
          Allocation failed. Please try again.
        </p>
      )}
    </form>
  );
}

function recommendedAmount(ppi: number) {
  return Math.round((400_000 + 1_100_000 * (ppi / 100)) / 10_000) * 10_000;
}

function CentreDrillDown({ centreId, onClose }: { centreId: string; onClose: () => void }) {
  const detail = useQuery({
    queryKey: ["admin-provider", centreId],
    queryFn: async () => {
      const { fetchAdminProviderDetail } = await import("@/lib/api");
      return fetchAdminProviderDetail(centreId);
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Centre drill-down"
    >
      <Card className="max-h-[80dvh] w-full max-w-2xl overflow-y-auto">
        <CardHeader className="flex-row items-start justify-between space-y-0">
          <div>
            <CardTitle className="font-display text-xl">
              {detail.data?.centre.name ?? "Centre"}
            </CardTitle>
            <CardDescription>{detail.data?.centre.district}</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {detail.isPending || !detail.data ? (
            <Skeleton className="h-48 w-full" />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <Stat label="PPI" value={detail.data.ppi_score.toFixed(1)} />
                <Stat
                  label="Placement"
                  value={`${Math.round(detail.data.placement_rate * 100)}%`}
                />
                <Stat
                  label="Verification"
                  value={`${Math.round(detail.data.verification_rate * 100)}%`}
                />
                <Stat label="Certified" value={String(detail.data.certified)} />
              </div>
              <div>
                <h4 className="mb-1 text-sm font-semibold">Score history</h4>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {detail.data.score_history.map((score) => (
                    <li key={score.period}>
                      {score.period}: PPI {score.ppi_score.toFixed(1)} · placement{" "}
                      {Math.round(score.placement_rate * 100)}%
                    </li>
                  ))}
                </ul>
              </div>
              {detail.data.allocations.length > 0 && (
                <div>
                  <h4 className="mb-1 text-sm font-semibold">Allocations</h4>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {detail.data.allocations.map((allocation) => (
                      <li key={allocation.id}>
                        {allocation.amount.toLocaleString("en-GB")} — {allocation.rationale}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-display text-lg font-semibold">{value}</p>
    </div>
  );
}

function GapMatrixCard() {
  const gaps = useQuery({
    queryKey: ["admin-gaps"],
    queryFn: async () => {
      const { fetchGapReports } = await import("@/lib/api");
      return fetchGapReports();
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-xl">Curriculum-demand gap matrix</CardTitle>
        <CardDescription>Worst gaps first — demand skills each course misses.</CardDescription>
      </CardHeader>
      <CardContent>
        {gaps.isPending ? (
          <Skeleton className="h-48 w-full" />
        ) : (gaps.data?.length ?? 0) === 0 ? (
          <EmptyState icon={BarChart3} title="No gap data" />
        ) : (
          <ul className="space-y-2">
            {(gaps.data ?? []).map((row) => (
              <li
                key={row.course_id}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm"
              >
                <div>
                  <p className="font-medium">{row.title}</p>
                  <p className="text-xs text-muted-foreground">
                    Missing:{" "}
                    {row.missing_in_demand_skills.map((m) => m.skill).join(", ") || "—"}
                  </p>
                </div>
                <span className="rounded-full bg-destructive/10 px-2.5 py-0.5 text-xs font-semibold text-destructive">
                  {row.gap_score.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

```

---

## `apps/web/src/app/globals.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* Warm paper surface with petrol-teal primary — light theme */
    --background: 40 33% 98%;
    --foreground: 200 25% 12%;
    --card: 0 0% 100%;
    --card-foreground: 200 25% 12%;
    --popover: 0 0% 100%;
    --popover-foreground: 200 25% 12%;
    --primary: 184 55% 25%;
    --primary-foreground: 40 33% 98%;
    --secondary: 178 35% 93%;
    --secondary-foreground: 184 45% 20%;
    --muted: 40 18% 92%;
    --muted-foreground: 200 12% 40%;
    --accent: 175 40% 92%;
    --accent-foreground: 184 45% 20%;
    --destructive: 0 72% 42%;
    --destructive-foreground: 0 0% 98%;
    --border: 40 15% 87%;
    --input: 40 15% 84%;
    --ring: 184 55% 30%;
    --radius: 0.75rem;
  }

  .dark {
    /* Deep petrol night with lifted teal primary — dark theme */
    --background: 195 28% 8%;
    --foreground: 40 25% 92%;
    --card: 195 24% 11%;
    --card-foreground: 40 25% 92%;
    --popover: 195 24% 11%;
    --popover-foreground: 40 25% 92%;
    --primary: 174 45% 45%;
    --primary-foreground: 195 30% 8%;
    --secondary: 190 20% 17%;
    --secondary-foreground: 40 20% 88%;
    --muted: 192 16% 16%;
    --muted-foreground: 190 12% 62%;
    --accent: 188 22% 20%;
    --accent-foreground: 40 20% 88%;
    --destructive: 0 65% 55%;
    --destructive-foreground: 0 0% 98%;
    --border: 190 16% 20%;
    --input: 190 16% 22%;
    --ring: 174 45% 45%;
  }

  * {
    @apply border-border;
  }

  html {
    scroll-behavior: smooth;
  }

  body {
    @apply bg-background text-foreground antialiased;
  }
}

@layer utilities {
  .text-balance {
    text-wrap: balance;
  }
}

@media (prefers-reduced-motion: reduce) {
  html {
    scroll-behavior: auto;
  }
}


/* Realtime pulse: a soft ring fades around cards whose data just changed. */
@keyframes realtime-pulse {
  0% {
    box-shadow: 0 0 0 3px rgba(30, 93, 95, 0.55);
  }
  100% {
    box-shadow: 0 0 0 6px rgba(30, 93, 95, 0);
  }
}

.realtime-pulse {
  animation: realtime-pulse 2s ease-out;
}

@media (prefers-reduced-motion: reduce) {
  .realtime-pulse {
    animation: none;
    outline: 2px solid rgba(30, 93, 95, 0.4);
    outline-offset: 2px;
  }
}

/* Print: isolate a section for "Export PDF (print)" */
@media print {
  body.printing-section * {
    visibility: hidden;
  }
  body.printing-section .print-target,
  body.printing-section .print-target * {
    visibility: visible;
  }
  body.printing-section .print-target {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
  }
}

```

---

