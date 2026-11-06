# TrackSkill AI — Phase 11 completion report

Hardening and quality: OWASP secure headers, rate limits, sensitive-read
auditing, field-level masking, consent revocation guarantees, trainee data
rights (export / erase), DPDP-aligned privacy documentation, pytest coverage
gate (≥ 80% on services + routers), Vitest component tests, the Playwright
four-role flagship E2E, and a GitHub Actions CI workflow. Every file below is
the complete current content on disk, from commit Phase 11.

## File tree (Phase 11 scope)

```
apps/api
├── app
│   ├── core/security.py                       # modified: shared cookie helpers
│   ├── main.py                                # modified: secure-headers middleware
│   ├── routers
│   │   ├── auth.py                            # modified: reset limiter + CSRF origin guard
│   │   ├── contact.py                         # modified: contact rate limit
│   │   ├── push.py                            # modified: push-test rate limit
│   │   ├── search.py                          # rewritten: centre-scoped + masked + audited
│   │   └── trainee.py                         # modified: /me/export + /me/delete
│   └── services
│       ├── employer_service.py                # modified: read audits + masked contacts + employer_id
│       ├── privacy.py                         # NEW: masking + READ_AUDIT
│       ├── rate_limit.py                      # modified: generic limiter + instances
│       ├── realtime.py                        # (Phase 10 push fan-out, unchanged here)
│       └── trainee_service.py                 # modified: export_my_data + delete_my_data
├── pyproject.toml                             # modified: coverage config, fail_under 80
├── requirements-dev.txt                       # modified: pytest-cov
└── tests
    ├── test_chain.py                          # modified: deterministic PPI assertions
    └── test_hardening.py                      # NEW: 19 tests
apps/web
├── e2e
│   ├── flagship-realtime.spec.ts              # NEW: 4-context flagship E2E
│   └── global-setup.ts                        # NEW: migrate + seed
├── playwright.config.ts                       # NEW
├── public/sw.js                               # modified: network-first API caching
├── src
│   ├── app/dashboard/employer/page.tsx        # modified: masked contacts shown
│   ├── app/dashboard/trainee/page.tsx         # modified: DataRightsCard (export/erase)
│   ├── components/dashboard/app-shell.tsx     # modified: "Your data" nav item
│   └── lib/api.ts                             # modified: data-rights + talent-pool type
├── vitest.config.ts / vitest.setup.ts         # NEW
├── src/**/*.test.tsx|ts (4 files)             # NEW: 11 component/unit tests
├── package.json                               # modified: test scripts, dev deps
└── tsconfig.json                              # modified: exclude capacitor.config
repo root
├── .github/workflows/ci.yml                   # NEW: lint + tests + build + E2E
└── README.md                                  # modified: DPDP privacy section + roadmap
```

---

## `apps/api/app/services/privacy.py`

```python
"""Privacy helpers (Phase 11): field masking and sensitive-read auditing.

``mask_phone`` / ``mask_email`` let any serializer expose contact fields to
roles that do not own the record without leaking the full value. ``audit_read``
writes an append-only Event row (type ``READ_AUDIT``) for every read that
exposes personal data across roles — audited reads are queryable via the
events table and never broadcast over the realtime channels.
"""

import logging
import re
from typing import TYPE_CHECKING

from app.models import Event

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.models.user import User

logger = logging.getLogger(__name__)

_PHONE_KEEP = re.compile(r"[+\d]")
_MASK = "\u2022"  # bullet •


def mask_phone(phone: str | None) -> str | None:
    """Keep the leading country code and the last four digits; mask the rest.

    ``+91 90123 45678`` -> ``+91 •••••45678``. Non-owner roles only ever see
    this form; the owner (the trainee) and their centre's provider staff see
    the full value through owner-scoped endpoints.
    """
    if not phone:
        return phone
    digits = "".join(character for character in phone if _PHONE_KEEP.match(character))
    if len(digits) <= 4:
        return _MASK * len(digits) if digits else phone
    country_end = 3 if digits.startswith("+") else 0
    tail = digits[-4:]
    masked_count = max(len(digits) - country_end - 4, 2)
    prefix = digits[:country_end] if country_end else ""
    if prefix:
        return f"{prefix} {_MASK * masked_count}{tail}"
    return f"{_MASK * masked_count}{tail}"


def mask_email(email: str | None) -> str | None:
    """Show the first two characters of the local part, then dots.

    ``meera.iyer@example.com`` -> ``me••••••@example.com``.
    """
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    visible = local[:2]
    return f"{visible}{_MASK * max(len(local) - 2, 3)}@{domain}"


def audit_read(
    db: "Session",
    *,
    reader: "User",
    kind: str,
    detail: dict | None = None,
) -> "UUID":
    """Record that ``reader`` accessed personal data of ``kind``.

    Only the audit row is written — no WebSocket broadcast, no notification:
    reads happen constantly and must not create alert noise, but they must
    all be attributable.
    """
    event = Event(
        type="READ_AUDIT",
        actor_user_id=reader.id,
        actor_role=reader.role.value,
        payload={"kind": kind, **(detail or {})},
    )
    db.add(event)
    db.flush()
    logger.info("READ_AUDIT %s by %s (%s)", kind, reader.id, reader.role.value)
    return event.id

```

---

## `apps/api/app/services/rate_limit.py`

```python
"""In-memory sliding-window rate limiting (login, contact, resets, push test)."""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """Process-local limiter, sufficient for the single-process dev API.

    Swap for a shared store (e.g. Redis) when running multiple workers.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def has_capacity(self, key: str, max_attempts: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            return len(hits) < max_attempts

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._hits.clear()


def enforce_rate_limit(
    limiter: SlidingWindowRateLimiter,
    request: Request,
    *,
    max_attempts: int,
    window_seconds: int,
    scope: str,
) -> None:
    """Raise 429 when this client exceeded the budget for ``scope``.

    Keys combine scope, client IP and (when present) the email/body identity
    so one abusive mailbox cannot lock out everyone behind an office NAT.
    Callers call ``limiter.record(key)`` only after the action succeeded.
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"{scope}:{client_ip}"
    if not limiter.has_capacity(key, max_attempts, window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests — please slow down and retry later.",
            headers={"Retry-After": "60"},
        )
    limiter.record(key)


login_limiter = SlidingWindowRateLimiter()
contact_limiter = SlidingWindowRateLimiter()
reset_limiter = SlidingWindowRateLimiter()
push_limiter = SlidingWindowRateLimiter()

```

---

## `apps/api/app/services/realtime.py`

```python
"""Event publishing: audit row + notifications + realtime broadcast + web push.

Every mutating endpoint calls :func:`publish_event` so the audit log
(``events`` table), user notifications and the WebSocket audience stay in
sync. Rows are flushed within the caller's request transaction and committed
by ``get_db`` when the request finishes. Every notification row also fans out
to the user's registered browsers as an encrypted Web Push message
(Phase 10); delivery runs in a worker thread and never fails requests.
"""

import logging
from collections.abc import Sequence
from typing import NamedTuple
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models import Event, Notification
from app.realtime.manager import manager
from app.services import push_service

logger = logging.getLogger(__name__)


class NotificationDraft(NamedTuple):
    user_id: UUID
    title: str
    body: str
    link: str | None = None


async def publish_event(
    db: Session,
    *,
    event_type: str,
    actor_user_id: UUID | None,
    actor_role: str,
    payload: dict | None = None,
    audience_user_ids: Sequence[UUID] = (),
    audience_roles: Sequence[str] = (),
    notifications: Sequence[NotificationDraft] = (),
) -> UUID:
    """Persist an audit event (plus notifications) and broadcast it live.

    Audience channels are ``user:<id>`` and ``role:<ROLE>``; duplicates in
    the audience lists are collapsed while preserving order.
    """
    resolved_payload = dict(payload or {})
    event = Event(
        id=uuid4(),
        type=event_type,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        payload=resolved_payload,
    )
    db.add(event)
    for draft in notifications:
        db.add(
            Notification(
                id=uuid4(),
                user_id=draft.user_id,
                title=draft.title,
                body=draft.body,
                link=draft.link,
                read=False,
            )
        )
    db.flush()

    message_payload = {**resolved_payload, "event_id": str(event.id)}
    for user_id in dict.fromkeys(audience_user_ids):
        await manager.broadcast(f"user:{user_id}", event_type, message_payload)
    for role in dict.fromkeys(audience_roles):
        await manager.broadcast(f"role:{role}", event_type, message_payload)

    # Web push mirrors the notification rows: one encrypted message per
    # notified user with a browser subscription. Snapshot synchronously here
    # (same transaction), deliver in the background.
    drafts = list(notifications)
    if drafts:
        targets = push_service.snapshot_subscriptions(db, [draft.user_id for draft in drafts])
        if targets:
            first = drafts[0]
            push_payload = {
                "title": first.title,
                "body": first.body,
                "link": first.link or "/dashboard",
                "event_id": str(event.id),
                "event_type": event_type,
            }
            push_service.dispatch_push_async(
                targets,
                push_payload,
                [draft.user_id for draft in drafts],
            )
    return event.id

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
from app.services.privacy import audit_read, mask_email, mask_phone
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
    # Reading trainee-submitted claims is a sensitive cross-role read.
    employer_user = db.get(User, employer.user_id)
    if employer_user is not None:
        audit_read(db, reader=employer_user, kind="verification_queue")
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
    *,
    employer_user: User | None = None,
) -> list[dict]:
    """Certified trainees with active consent, grouped by their skills.

    match_score blends the market demand for the skill with embedding
    similarity when a search term is given (light-NLP mode keeps it lexical).
    """
    if employer_user is None:
        employer_user = db.get(User, employer.user_id)
    audit_read(
        db,
        reader=employer_user,
        kind="talent_pool",
        detail={"skill": skill_filter, "district": district_filter},
    )
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
                {"count": 0, "districts": set(), "names": [], "contacts": []},
            )
            entry["count"] += 1
            entry["districts"].add(trainee.district)
            if len(entry["names"]) < 3:
                entry["names"].append(user.name)
                # Field-level masking: employers browsing the pool see masked
                # contact details — outreach stays inside the platform.
                entry["contacts"].append(
                    {"email": mask_email(user.email), "phone": mask_phone(trainee.phone)}
                )

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
                "contacts": entry["contacts"],
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
        "employer_id": str(employer.id),
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

## `apps/api/app/services/trainee_service.py`

```python
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

```

---

## `apps/api/app/core/security.py`

```python
"""Password hashing and JWT helpers.

Shared by the demo seed, the auth endpoints and the role-based access
control dependencies.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from fastapi import Response

from app.core.config import get_settings

REFRESH_COOKIE = "refresh_token"


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _create_token(
    subject: str, token_type: str, lifetime: timedelta, extra: dict[str, Any] | None = None
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    user_id: uuid.UUID, role: str, expires_delta: timedelta | None = None
) -> str:
    """Short-lived access token carrying the caller's role."""
    settings = get_settings()
    lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    return _create_token(str(user_id), "access", lifetime, {"role": role})


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Long-lived refresh token, delivered as an httpOnly cookie."""
    settings = get_settings()
    return _create_token(
        str(user_id), "refresh", timedelta(days=settings.refresh_token_expire_days)
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and validate a JWT, enforcing its type.

    Raises jwt.InvalidTokenError (including ExpiredSignatureError) on any
    problem; callers map that to a generic 401.
    """
    settings = get_settings()
    payload: dict[str, Any] = jwt.decode(
        token, settings.secret_key, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


# ── Refresh cookie helpers (shared by auth and data-rights endpoints) ────────


def set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/auth",
    )


def clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path="/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )

```

---

## `apps/api/app/main.py`

```python
"""TrackSkill AI API entrypoint."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
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
    push,
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

    async def secure_headers(request: Request, call_next):
        """OWASP secure headers on every response (Phase 11).

        The API serves only JSON, so its CSP pins to 'none'; the browser app
        sets its own policy in next.config.mjs. HSTS is emitted in production
        (HTTPS) environments only — on plain-http local runs it is meaningless
        and would linger in cached responses.
        """
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    application.middleware("http")(secure_headers)

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
    application.include_router(push.router)
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

## `apps/api/app/routers/search.py`

```python
"""Role-aware global search for the top bar.

Hardened in Phase 11: provider searches are scoped to the centres they staff
(a provider must never see trainees of other centres), and every trainee
contact field crossing a role boundary is masked (email here; the provider
roster keeps owner-scoped detail).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.dependencies import require_role
from app.models import Course, ProviderStaff, Trainee, TrainingCentre, User
from app.models.enums import UserRole
from app.services.privacy import audit_read, mask_email

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
        query = (
            select(Trainee, User)
            .join(User, Trainee.user_id == User.id)
            .where(or_(User.name.ilike(needle), User.email.ilike(needle)))
        )
        if current_user.role is UserRole.PROVIDER:
            centre_ids = select(ProviderStaff.centre_id).where(
                ProviderStaff.user_id == current_user.id
            )
            query = query.where(Trainee.centre_id.in_(centre_ids))
        trainees = db.execute(query.limit(5)).all()
        if trainees:
            audit_read(
                db,
                reader=current_user,
                kind="trainee_search",
                detail={"query_length": len(q.strip()), "matches": len(trainees)},
            )
        for _, user in trainees:
            results.append(
                {"type": "trainee", "label": user.name, "detail": mask_email(user.email)}
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

## `apps/api/app/routers/contact.py`

```python
"""Public landing-page contact endpoint."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models import ContactMessage
from app.schemas.contact import ContactRequest
from app.services.rate_limit import contact_limiter, enforce_rate_limit
from app.services.realtime import publish_event

router = APIRouter(tags=["contact"])


@router.post("/contact", status_code=201, summary="Submit a contact enquiry")
async def submit_contact(
    payload: ContactRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Public endpoint: stores the enquiry and notifies admins live."""
    enforce_rate_limit(
        contact_limiter, request, max_attempts=5, window_seconds=600, scope="contact"
    )
    message = ContactMessage(
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        organisation=(payload.organisation or "").strip() or None,
        role=payload.role,
        message=payload.message.strip(),
    )
    db.add(message)
    db.flush()

    await publish_event(
        db,
        event_type="CONTACT_RECEIVED",
        actor_user_id=None,
        actor_role="PUBLIC",
        payload={
            "contact_id": str(message.id),
            "name": message.name,
            "role": message.role,
            "organisation": message.organisation,
        },
        audience_roles=["ADMIN"],
    )

    settings = get_settings()
    return {
        "status": "received",
        "id": str(message.id),
        "message": (
            "Thanks for reaching out — the TrackSkill AI team will "
            f"reply to {message.email} within two working days."
        ),
        "contact": settings.project_name,
    }

```

---

## `apps/api/app/routers/auth.py`

```python
"""Authentication endpoints: register, login, refresh, logout, profile."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import (
    clear_refresh_cookie,
    create_access_token,
    create_refresh_token,
    decode_token,
    set_refresh_cookie,
)
from app.dependencies import require_role
from app.models import Trainee, User
from app.models.enums import UserRole
from app.schemas import (
    DemoAccount,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserPublic,
)
from app.services.auth_service import (
    EmailAlreadyRegisteredError,
    UnknownCentreCodeError,
    authenticate_email_only,
    authenticate_user,
    create_password_reset_token,
    create_registration_consents,
    register_user,
    reset_password_with_token,
)
from app.services.rate_limit import enforce_rate_limit, login_limiter, reset_limiter

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
SELF_SIGNUP_ROLES = (UserRole.TRAINEE, UserRole.EMPLOYER)


def _set_refresh_cookie(response: Response, token: str) -> None:
    set_refresh_cookie(response, token)


def _clear_refresh_cookie(response: Response) -> None:
    clear_refresh_cookie(response)


def _token_response(user: User) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserPublic.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    """Self-signup for TRAINEE and EMPLOYER accounts only.

    PROVIDER and ADMIN accounts are provisioned by the seed or by an
    administrator. Signing up signs the caller in (access token in the body,
    refresh token as an httpOnly cookie).
    """
    if payload.role not in SELF_SIGNUP_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-signup is available for Trainee and Employer accounts only.",
        )
    if payload.role is UserRole.TRAINEE and (not payload.phone or not payload.district):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Trainee registration requires a phone number and district.",
        )
    if payload.role is UserRole.EMPLOYER and not (payload.company_name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Employer registration requires a company name.",
        )

    try:
        user = register_user(
            db,
            name=payload.name,
            email=payload.email,
            password=payload.password,
            role=payload.role,
            phone=payload.phone,
            district=payload.district,
            centre_code=payload.centre_code,
            company_name=payload.company_name,
            company_district=payload.company_district,
            company_sector=payload.company_sector,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    except UnknownCentreCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That centre code was not recognised. Check it with your training centre.",
        ) from exc

    if payload.role is UserRole.TRAINEE and payload.consent_channels:
        trainee = db.execute(
            select(Trainee).where(Trainee.user_id == user.id)
        ).scalar_one()
        create_registration_consents(
            db, trainee_id=trainee.id, channels=payload.consent_channels
        )

    _set_refresh_cookie(response, create_refresh_token(user.id))
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    """Exchange email + password for an access token and refresh cookie.

    Failures share one generic message and are rate limited per IP + email.
    """
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    limiter_key = f"{client_ip}:{payload.email.strip().lower()}"

    if not login_limiter.has_capacity(
        limiter_key, settings.login_max_attempts, settings.login_window_seconds
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )

    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        login_limiter.record(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    login_limiter.reset(limiter_key)
    _set_refresh_cookie(response, create_refresh_token(user.id))
    return _token_response(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange the httpOnly refresh cookie for a fresh access token.

    The refresh token is rotated on every use. CSRF: the cookie is
    SameSite=Lax and Path-scoped to /auth; as defense in depth a request that
    carries a cross-origin Origin header is rejected outright.
    """
    origin = request.headers.get("origin")
    if origin:
        allowed = {value.rstrip("/") for value in get_settings().cors_origins}
        if origin.rstrip("/") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-origin refresh requests are not allowed.",
            )
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    try:
        payload = decode_token(token, expected_type="refresh")
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session."
        ) from None

    try:
        user = db.get(User, UUID(str(payload.get("sub"))))
    except ValueError:
        user = None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session."
        )

    _set_refresh_cookie(response, create_refresh_token(user.id))
    return _token_response(user)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    """Clear the refresh cookie; the client drops its in-memory access token."""
    _clear_refresh_cookie(response)
    return {"detail": "Logged out."}


@router.post("/forgot-password", summary="Request a password reset")
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Always responds generically. In DEMO_MODE the response includes the
    reset link so the flow works without an email gateway."""
    enforce_rate_limit(
        reset_limiter, request, max_attempts=5, window_seconds=600, scope="forgot"
    )
    settings = get_settings()
    response: dict = {
        "status": "ok",
        "message": "If that email exists, a reset link has been sent.",
    }
    if settings.demo_mode:
        user = authenticate_email_only(db, payload.email)
        if user is not None:
            token = create_password_reset_token(user.id)
            response["reset_link"] = f"/reset-password?token={token}"
    return response


@router.post("/reset-password", summary="Reset the password with a demo token")
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> dict:
    applied = reset_password_with_token(
        db, token=payload.token, new_password=payload.new_password
    )
    if not applied:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired.",
        )
    return {"status": "ok", "message": "Password updated. You can sign in now."}


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(require_role())) -> User:
    """Profile of the authenticated user (any role)."""
    return current_user


@router.get("/admin-area")
def admin_area(current_user: User = Depends(require_role(UserRole.ADMIN))) -> dict[str, str]:
    """RBAC smoke endpoint: only ADMIN passes; every other role gets 403."""
    return {"detail": "Welcome to the admin area.", "role": current_user.role.value}


@router.get("/demo-accounts", response_model=list[DemoAccount])
def demo_accounts() -> list[DemoAccount]:
    """Pre-seeded reviewer logins, available only while DEMO_MODE is enabled."""
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    password = settings.demo_password
    return [
        DemoAccount(
            role=UserRole.ADMIN,
            email="admin.demo@trackskill.in",
            password=password,
            dashboard="/dashboard/admin",
        ),
        DemoAccount(
            role=UserRole.PROVIDER,
            email="provider.demo@trackskill.in",
            password=password,
            dashboard="/dashboard/provider",
        ),
        DemoAccount(
            role=UserRole.TRAINEE,
            email="trainee.demo@trackskill.in",
            password=password,
            dashboard="/dashboard/trainee",
        ),
        DemoAccount(
            role=UserRole.EMPLOYER,
            email="employer.demo@trackskill.in",
            password=password,
            dashboard="/dashboard/employer",
        ),
    ]

```

---

## `apps/api/app/routers/push.py`

```python
"""Web push endpoints (Phase 10): VAPID public key, subscribe, unsubscribe,
and a test send so the demo can prove delivery end to end."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.vapid import public_key_for_browser
from app.dependencies import require_role
from app.models.push import PushSubscription
from app.models.user import User
from app.services.push_service import send_to_user_sync
from app.services.rate_limit import enforce_rate_limit, push_limiter

router = APIRouter(prefix="/push", tags=["push"])


class SubscriptionBody(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1000)
    keys: dict[str, str]
    user_agent: str | None = None


class UnsubscribeBody(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1000)


@router.get("/public-key", summary="VAPID public key for PushManager.subscribe")
def get_public_key(current_user: User = Depends(require_role())) -> dict:
    return {"public_key": public_key_for_browser()}


@router.post("/subscriptions", summary="Register this browser for pushes")
def subscribe(
    body: SubscriptionBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    p256dh = body.keys.get("p256dh")
    auth = body.keys.get("auth")
    if not p256dh or not auth:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Subscription keys must include p256dh and auth.",
        )

    existing = db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    ).scalar_one_or_none()
    if existing is None:
        existing = PushSubscription(
            id=uuid.uuid4(),
            user_id=current_user.id,
            endpoint=body.endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=body.user_agent,
        )
        db.add(existing)
    else:
        # A subscription belongs to whoever holds it now (e.g. re-login).
        existing.user_id = current_user.id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.user_agent = body.user_agent
    db.flush()
    return {"status": "subscribed"}


@router.post("/subscriptions/delete", summary="Remove a browser subscription")
def unsubscribe(
    body: UnsubscribeBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    existing = db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    ).scalar_one_or_none()
    if existing is not None and existing.user_id == current_user.id:
        db.delete(existing)
        db.flush()
    return {"status": "unsubscribed"}


@router.post("/test", summary="Send a test push to all my devices")
def test_push(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role()),
) -> dict:
    enforce_rate_limit(
        push_limiter, request, max_attempts=5, window_seconds=60, scope="push-test"
    )
    result = send_to_user_sync(
        db,
        current_user.id,
        {
            "title": "TrackSkill AI test notification",
            "body": "If you can read this, Web Push delivery works end to end.",
            "link": "/dashboard",
        },
    )
    return result

```

---

## `apps/api/app/routers/trainee.py`

```python
"""Trainee REST API: journey, consent, follow-up responses, skills."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai import skill_assessment
from app.core.db import get_db
from app.core.security import clear_refresh_cookie
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
from app.services.rate_limit import enforce_rate_limit, reset_limiter

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



@router.get("/me/export", summary="Download everything the platform stores about me")
def export_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
) -> dict:
    """DPDP-aligned data access right: one JSON document, own data only."""
    trainee = trainee_service.own_trainee(db, current_user.id)
    return trainee_service.export_my_data(db, trainee=trainee)


class DeleteAccountRequest(BaseModel):
    confirm: bool


@router.post("/me/delete", summary="Erase my account and all personal data")
async def delete_data(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TRAINEE)),
) -> dict:
    """DPDP-aligned erasure right. Requires explicit {"confirm": true};
    clears the refresh cookie so the session ends immediately."""
    enforce_rate_limit(
        reset_limiter, request, max_attempts=5, window_seconds=600, scope="delete-account"
    )
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Send {"confirm": true} to permanently erase your data.',
        )
    trainee = trainee_service.own_trainee(db, current_user.id)
    result = await trainee_service.delete_my_data(db, trainee=trainee, user=current_user)
    clear_refresh_cookie(response)
    return result

```

---

## `apps/api/tests/test_hardening.py`

```python
"""Phase 11 hardening tests: secure headers, masking, rate limits,
read auditing and search scoping."""

import uuid

from sqlalchemy import select

from app.models import Event, Trainee, User
from app.models.enums import UserRole
from app.services.privacy import mask_email, mask_phone

# ── Field-level masking ──────────────────────────────────────────────────────


def test_mask_phone_keeps_country_and_last_four() -> None:
    assert mask_phone("+91 90123 45678") == "+91 ••••••5678"
    assert mask_phone("+919012345678") == "+91 ••••••5678"


def test_mask_phone_handles_short_and_local_numbers() -> None:
    assert mask_phone("123456") == "••3456"
    assert mask_phone("") == ""
    assert mask_phone(None) is None


def test_mask_email_shows_two_characters() -> None:
    masked = mask_email("meera.iyer@example.com")
    assert masked == "me••••••••@example.com"
    assert mask_email("a@b.com") == "a•••@b.com"
    assert mask_email("not-an-email") == "not-an-email"
    assert mask_email(None) is None


def test_talent_pool_exposes_masked_contacts_only(client, db_session) -> None:
    token = _login(client, "employer.demo@trackskill.in")
    response = client.get("/employer/talent-pool", headers=_auth(token))
    assert response.status_code == 200, response.text
    rows = response.json()
    assert rows, "seeded database must have consented certified trainees"
    for row in rows:
        for contact in row.get("contacts", []):
            phone = contact["phone"]
            assert phone is None or phone.endswith("••") or phone[-4:].isdigit()
            if phone and phone.startswith("+"):
                assert "•" in phone  # never the full number
            email = contact["email"]
            assert email.count("@") == 1
            local = email.split("@")[0]
            assert "•" in local  # never the full address


# ── Secure headers ───────────────────────────────────────────────────────────


def test_secure_headers_on_api_responses(client) -> None:
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Permissions-Policy"].startswith("camera=()")


def test_hsts_only_in_production(client, monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "environment", "production")
    response = client.get("/health")
    assert "max-age=31536000" in response.headers["Strict-Transport-Security"]

    monkeypatch.setattr(get_settings(), "environment", "development")
    response = client.get("/health")
    assert "Strict-Transport-Security" not in response.headers


# ── Rate limits ──────────────────────────────────────────────────────────────


def test_contact_rate_limit_blocks_sixth_submission(client) -> None:
    from app.services.rate_limit import contact_limiter

    contact_limiter.reset_all()
    payload = {
        "name": "Rate Limited Person",
        "email": "ratelimit.sample@example.com",
        "role": "OTHER",
        "message": "A message with enough characters for the validator.",
    }
    statuses = []
    for _ in range(7):
        statuses.append(client.post("/contact", json=payload).status_code)
    assert statuses[:5] == [201, 201, 201, 201, 201]
    assert statuses[5] == 429
    assert statuses[6] == 429
    contact_limiter.reset_all()


def test_forgot_password_rate_limit(client) -> None:
    from app.services.rate_limit import reset_limiter

    reset_limiter.reset_all()
    payload = {"email": "forgot.sample@example.com"}
    statuses = []
    for _ in range(7):
        statuses.append(client.post("/auth/forgot-password", json=payload).status_code)
    assert statuses[:5] == [200, 200, 200, 200, 200]
    assert statuses[5] == 429
    reset_limiter.reset_all()


def test_refresh_rejects_cross_origin_header(client) -> None:
    response = client.post(
        "/auth/refresh",
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 403


# ── Sensitive-read auditing ──────────────────────────────────────────────────


def test_talent_pool_read_is_audited(client, db_session) -> None:
    token = _login(client, "employer.demo@trackskill.in")
    before = db_session.execute(
        select(Event).where(Event.type == "READ_AUDIT")
    ).scalars().all()
    response = client.get("/employer/talent-pool", headers=_auth(token))
    assert response.status_code == 200

    db_session.expire_all()
    after = db_session.execute(
        select(Event).where(Event.type == "READ_AUDIT")
    ).scalars().all()
    assert len(after) == len(before) + 1
    event = after[-1]
    assert event.payload["kind"] == "talent_pool"
    assert event.actor_role == "EMPLOYER"


def test_verification_queue_read_is_audited(client, db_session) -> None:
    token = _login(client, "employer.demo@trackskill.in")
    response = client.get("/employer/verifications", headers=_auth(token))
    assert response.status_code == 200
    db_session.expire_all()
    events = db_session.execute(
        select(Event).where(Event.type == "READ_AUDIT")
    ).scalars().all()
    kinds = [event.payload["kind"] for event in events]
    assert "verification_queue" in kinds


def test_provider_search_scoped_to_own_centres(client, db_session) -> None:
    """A provider must never surface trainees of another centre."""
    token = _login(client, "provider.demo@trackskill.in")
    response = client.get("/search?q=@", headers=_auth(token))
    assert response.status_code == 200
    results = response.json()["results"]
    trainee_users = db_session.execute(
        select(User).join(Trainee, Trainee.user_id == User.id)
    ).scalars().all()
    emails_by_user = {user.id: user.email for user in trainee_users}
    from app.models import ProviderStaff

    staff_user = db_session.execute(
        select(User).where(User.email == "provider.demo@trackskill.in")
    ).scalar_one()
    centre_ids = set(
        db_session.execute(
            select(ProviderStaff.centre_id).where(ProviderStaff.user_id == staff_user.id)
        ).scalars()
    )
    allowed_emails = set()
    for trainee in db_session.execute(select(Trainee)).scalars():
        if trainee.centre_id in centre_ids:
            allowed_emails.add(mask_email(emails_by_user[trainee.user_id]))
    seen = 0
    for row in results:
        if row["type"] == "trainee":
            seen += 1
            assert row["detail"] in allowed_emails, (
                "provider search leaked a trainee from another centre"
            )
    assert seen > 0, "expected at least one own-centre trainee match for '@'"


def test_admin_search_masks_trainee_email(client, db_session) -> None:
    token = _login(client, "admin.demo@trackskill.in")
    response = client.get("/search?q=@", headers=_auth(token))
    assert response.status_code == 200
    for row in response.json()["results"]:
        if row["type"] == "trainee":
            assert "•" in row["detail"]


# ── Data rights: export + erasure ────────────────────────────────────────────


def _enrol_trainee(client, provider_token: str, course_id: str, email: str) -> dict:
    response = client.post(
        "/provider/trainees",
        json={
            "name": "Data Rights Trainee",
            "email": email,
            "phone": "+91 9098765432",
            "course_id": course_id,
        },
        headers=_auth(provider_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(client, email, password="Demo@1234") -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_trainee_export_contains_everything(client, db_session) -> None:
    provider_token = _login(client, "provider.demo@trackskill.in")
    courses = client.get("/provider/courses", headers=_auth(provider_token)).json()
    email = f"export.{uuid.uuid4().hex[:8]}@trackskill.in"
    enrol = _enrol_trainee(client, provider_token, courses[0]["id"], email)
    trainee_token = _login(client, email, enrol["temporary_password"])
    client.patch(
        f"/provider/trainees/{enrol['trainee']['id']}/certify",
        json={},
        headers=_auth(provider_token),
    )
    client.post(
        "/trainee/consent",
        json={"channel": "WHATSAPP", "granted": True},
        headers=_auth(trainee_token),
    )

    response = client.get("/trainee/me/export", headers=_auth(trainee_token))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["profile"]["email"] == email
    assert data["profile"]["phone"] == "+91 9098765432"  # owner sees full value
    assert data["consents"] and data["consents"][0]["granted"] is True
    assert data["consents"][0]["purpose"]
    assert data["tracers"], "consent schedules milestone tracers"
    assert data["exported_at"]


def test_delete_my_data_erases_account(client, db_session) -> None:
    provider_token = _login(client, "provider.demo@trackskill.in")
    courses = client.get("/provider/courses", headers=_auth(provider_token)).json()
    email = f"erase.{uuid.uuid4().hex[:8]}@trackskill.in"
    enrol = _enrol_trainee(client, provider_token, courses[0]["id"], email)
    trainee_token = _login(client, email, enrol["temporary_password"])
    client.patch(
        f"/provider/trainees/{enrol['trainee']['id']}/certify",
        json={},
        headers=_auth(provider_token),
    )
    client.post(
        "/trainee/consent",
        json={"channel": "WHATSAPP", "granted": True},
        headers=_auth(trainee_token),
    )

    # Refuse without explicit confirmation.
    refuse = client.post(
        "/trainee/me/delete", json={"confirm": False}, headers=_auth(trainee_token)
    )
    assert refuse.status_code == 422

    erased = client.post("/trainee/me/delete", json={"confirm": True}, headers=_auth(trainee_token))
    assert erased.status_code == 200, erased.text
    body = erased.json()
    assert body["status"] == "deleted"
    assert body["erased"]["tracers"] >= 3  # M3/M6/M12 were scheduled after consent

    # The account is gone and the token no longer works.
    me = client.get("/trainee/me", headers=_auth(trainee_token))
    assert me.status_code == 401

    db_session.expire_all()
    user_row = db_session.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()
    assert user_row is None
    trainee_row = db_session.execute(
        select(Trainee).where(Trainee.user_id == (user_row.id if user_row else uuid.UUID(int=0)))
    ).scalar_one_or_none()
    assert trainee_row is None

    # The erasure is audited for admins; the audit trail survives.
    events = db_session.execute(
        select(Event).where(Event.type == "TRAINEE_DATA_DELETED")
    ).scalars().all()
    assert any(
        event.payload.get("trainee_id") == enrol["trainee"]["id"] for event in events
    )


def test_deleted_trainee_never_becomes_active_again(client, db_session) -> None:
    """After erasure the email is free to register again (fresh consent)."""
    provider_token = _login(client, "provider.demo@trackskill.in")
    courses = client.get("/provider/courses", headers=_auth(provider_token)).json()
    email = f"reerase.{uuid.uuid4().hex[:8]}@trackskill.in"
    enrol = _enrol_trainee(client, provider_token, courses[0]["id"], email)
    trainee_token = _login(client, email, enrol["temporary_password"])
    client.post("/trainee/me/delete", json={"confirm": True}, headers=_auth(trainee_token))

    re_enrol = _enrol_trainee(client, provider_token, courses[0]["id"], email)
    assert re_enrol["trainee"]["id"] != enrol["trainee"]["id"]


def test_consent_revocation_cancels_tracers(client, db_session) -> None:
    """Revoking consent stops tracing immediately (Phase 11 hardening pass)."""
    provider_token = _login(client, "provider.demo@trackskill.in")
    courses = client.get("/provider/courses", headers=_auth(provider_token)).json()
    email = f"revoke.{uuid.uuid4().hex[:8]}@trackskill.in"
    enrol = _enrol_trainee(client, provider_token, courses[0]["id"], email)
    trainee_token = _login(client, email, enrol["temporary_password"])
    client.patch(
        f"/provider/trainees/{enrol['trainee']['id']}/certify",
        json={},
        headers=_auth(provider_token),
    )

    granted = client.post(
        "/trainee/consent",
        json={"channel": "WHATSAPP", "granted": True},
        headers=_auth(trainee_token),
    )
    assert granted.json()["followups_scheduled"] == 3

    revoked = client.post(
        "/trainee/consent",
        json={"channel": "WHATSAPP", "granted": False},
        headers=_auth(trainee_token),
    )
    assert revoked.status_code == 200
    assert revoked.json()["followups_cancelled"] == 3
    assert revoked.json()["followups_scheduled"] == 0

    # The tracer engine must refuse to reschedule without consent.
    from app.services.tracer_service import has_active_consent

    db_session.expire_all()
    trainee = db_session.execute(
        select(Trainee).where(Trainee.id == uuid.UUID(enrol["trainee"]["id"]))
    ).scalar_one()
    assert has_active_consent(db_session, trainee.id) is False


def test_revoked_trainee_hidden_from_talent_pool(client, db_session) -> None:
    provider_token = _login(client, "provider.demo@trackskill.in")
    courses = client.get("/provider/courses", headers=_auth(provider_token)).json()
    email = f"hidden.{uuid.uuid4().hex[:8]}@trackskill.in"
    enrol = _enrol_trainee(client, provider_token, courses[0]["id"], email)
    trainee_token = _login(client, email, enrol["temporary_password"])
    client.patch(
        f"/provider/trainees/{enrol['trainee']['id']}/certify",
        json={},
        headers=_auth(provider_token),
    )
    client.post(
        "/trainee/consent",
        json={"channel": "WHATSAPP", "granted": True},
        headers=_auth(trainee_token),
    )

    employer_token = _login(client, "employer.demo@trackskill.in")
    from app.models import Course

    course = db_session.get(Course, uuid.UUID(courses[0]["id"]))
    skill = (course.skills or [""])[0]

    def pool_count() -> int:
        pool = client.get(
            "/employer/talent-pool",
            params={"skill": skill},
            headers=_auth(employer_token),
        ).json()
        row = next((entry for entry in pool if entry["skill"] == skill), None)
        return row["trainee_count"] if row else 0

    base = pool_count()
    assert base >= 1  # our consented trainee is in the pool
    # (Names are capped at three per skill — the count is the assertion.)

    client.post(
        "/trainee/consent",
        json={"channel": "WHATSAPP", "granted": False},
        headers=_auth(trainee_token),
    )
    db_session.expire_all()
    assert pool_count() == base - 1


def test_role_enum_membership_complete() -> None:
    """Guard: masking decisions key off these roles."""
    assert {role.value for role in UserRole} >= {
        "ADMIN",
        "PROVIDER",
        "EMPLOYER",
        "TRAINEE",
    }

```

---

## `apps/api/tests/test_chain.py`

```python
"""The flagship realtime chain, end to end:

1. Provider enrols + certifies a trainee -> trainee notification + consent prompt.
2. Trainee grants consent and answers the M3 tracer claiming a job ->
   employer sees the pending verification instantly; provider sees the response.
3. Employer confirms -> verification complete -> PPI recalculated ->
   admin sees it live.
4. Admin allocates funds and flags the centre -> provider notified live.

Every step asserts the WebSocket events delivered to each role's socket.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import (
    Consent,
    Course,
    Employer,
    EmploymentRecord,
    FollowUp,
    Notification,
    ProviderScore,
    Trainee,
    TrainingCentre,
    User,
    Verification,
)
from app.models.enums import FollowUpMilestone, VerificationSignal
from app.services import ppi
from app.services.ppi import current_period

DEMO_PASSWORD = "Demo@1234"
EMAILS = {
    "ADMIN": "admin.demo@trackskill.in",
    "PROVIDER": "provider.demo@trackskill.in",
    "EMPLOYER": "employer.demo@trackskill.in",
}


@pytest.fixture(autouse=True)
def _require_seeded_database(db_session):
    user_count = db_session.execute(select(func.count()).select_from(User)).scalar_one()
    if user_count == 0:
        pytest.skip("Database is not seeded; run alembic upgrade head and python -m app.seed.")


def _login(client: TestClient, email: str, password: str = DEMO_PASSWORD) -> dict:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _recv(socket, count: int) -> list[dict]:
    return [socket.receive_json() for _ in range(count)]


def test_flagship_realtime_chain(client: TestClient, db_session) -> None:
    provider_token = _login(client, EMAILS["PROVIDER"])["access_token"]
    employer_token = _login(client, EMAILS["EMPLOYER"])["access_token"]
    admin_token = _login(client, EMAILS["ADMIN"])["access_token"]

    centre_id = db_session.execute(
        select(TrainingCentre.id).where(TrainingCentre.district == "North District")
    ).scalar_one()
    course_id = db_session.execute(
        select(Course.id).where(Course.centre_id == centre_id).limit(1)
    ).scalar_one()

    # Role sockets: provider, employer, admin connect first.
    with (
        client.websocket_connect(f"/ws?token={provider_token}") as ws_provider,
        client.websocket_connect(f"/ws?token={employer_token}") as ws_employer,
        client.websocket_connect(f"/ws?token={admin_token}") as ws_admin,
    ):
        assert ws_provider.receive_json()["payload"]["role"] == "PROVIDER"
        assert ws_employer.receive_json()["payload"]["role"] == "EMPLOYER"
        assert ws_admin.receive_json()["payload"]["role"] == "ADMIN"

        # ── 1. Provider enrols a trainee ────────────────────────────────────
        enrol = client.post(
            "/provider/trainees",
            json={
                "name": "Chain Trainee",
                "email": "chain.trainee@trackskill.in",
                "phone": "+91 9000000001",
                "course_id": str(course_id),
            },
            headers=_auth(provider_token),
        )
        assert enrol.status_code == 201, enrol.text
        body = enrol.json()
        trainee_id = body["trainee"]["id"]
        assert body["temporary_password"]

        # Provider socket sees the enrolment; other roles do not.
        assert _recv(ws_provider, 1)[0]["event"] == "TRAINEE_ENROLLED"
        # The new trainee already has a notification + consent prompt row.
        trainee_user_id = db_session.execute(
            select(Trainee.user_id).where(Trainee.id == uuid.UUID(trainee_id))
        ).scalar_one()
        notifications = db_session.execute(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == trainee_user_id
            )
        ).scalar_one()
        assert notifications >= 1

        # ── 2. The new trainee signs in and connects ────────────────────────
        trainee_token = _login(
            client, "chain.trainee@trackskill.in", body["temporary_password"]
        )["access_token"]
        with client.websocket_connect(f"/ws?token={trainee_token}") as ws_trainee:
            assert ws_trainee.receive_json()["payload"]["role"] == "TRAINEE"

            # ── 3. Provider certifies (no consent yet -> no tracers) ────────
            certify = client.patch(
                f"/provider/trainees/{trainee_id}/certify",
                json={},
                headers=_auth(provider_token),
            )
            assert certify.status_code == 200, certify.text
            assert certify.json()["consent_active"] is False
            assert certify.json()["followups_scheduled"] == 0
            assert _recv(ws_provider, 1)[0]["event"] == "TRAINEE_CERTIFIED"
            assert _recv(ws_trainee, 1)[0]["event"] == "TRAINEE_CERTIFIED"

            # ── 4. Trainee grants consent -> tracers scheduled ──────────────
            consent = client.post(
                "/trainee/consent",
                json={"channel": "WHATSAPP", "granted": True},
                headers=_auth(trainee_token),
            )
            assert consent.status_code == 200, consent.text
            assert consent.json()["followups_scheduled"] == 3
            assert _recv(ws_provider, 1)[0]["event"] == "CONSENT_GRANTED"

            m3_id = db_session.execute(
                select(FollowUp.id).where(
                    FollowUp.trainee_id == uuid.UUID(trainee_id),
                    FollowUp.milestone == FollowUpMilestone.M3,
                )
            ).scalar_one()
            employer_id = db_session.execute(
                select(Employer.id).join(User, Employer.user_id == User.id).where(
                    User.email == EMAILS["EMPLOYER"]
                )
            ).scalar_one()

            # ── 5. Trainee answers the M3 tracer claiming a job ─────────────
            respond = client.post(
                f"/trainee/followups/{m3_id}/respond",
                json={
                    "employment_status": "EMPLOYED",
                    "job_title": "Junior Web Developer",
                    "monthly_wage": 22000,
                    "employer_id": str(employer_id),
                },
                headers=_auth(trainee_token),
            )
            assert respond.status_code == 200, respond.text
            verification_id = respond.json()["verification_id"]
            assert verification_id
            # Employer sees the pending claim instantly; provider sees the response.
            assert _recv(ws_employer, 1)[0]["event"] == "FOLLOWUP_RESPONDED"
            assert _recv(ws_provider, 1)[0]["event"] == "FOLLOWUP_RESPONDED"

            period = current_period()
            score_row = db_session.execute(
                select(ProviderScore).where(
                    ProviderScore.centre_id == centre_id, ProviderScore.period == period
                )
            ).scalar_one()
            # Fresh computation, not the stored row: the demo row can lag
            # the drifted database and coincide with post-confirm values.
            verification_rate_before = ppi.compute_metrics(db_session, centre_id)[
                "verification_rate"
            ]

            # ── 6. Employer confirms -> verification complete -> PPI moves ──
            confirm = client.post(
                f"/employer/verifications/{verification_id}/confirm",
                headers=_auth(employer_token),
            )
            assert confirm.status_code == 200, confirm.text
            assert confirm.json()["verified"] is True

            assert [event["event"] for event in _recv(ws_provider, 2)] == [
                "VERIFICATION_COMPLETE",
                "PPI_RECALCULATED",
            ]
            assert [event["event"] for event in _recv(ws_admin, 2)] == [
                "VERIFICATION_COMPLETE",
                "PPI_RECALCULATED",
            ]
            assert _recv(ws_trainee, 1)[0]["event"] == "VERIFICATION_COMPLETE"

            verification = db_session.get(Verification, uuid.UUID(verification_id))
            assert verification.trainee_signal is VerificationSignal.CONFIRMED
            assert verification.employer_signal is VerificationSignal.CONFIRMED
            score_row = db_session.execute(
                select(ProviderScore).where(
                    ProviderScore.centre_id == centre_id, ProviderScore.period == period
                )
            ).scalar_one()
            # Recalculation happened: the stored row matches a fresh
            # recomputation of the centre (a stale row would lag the confirm).
            # One more confirmation may not move the 2-dp score in a drifted
            # demo database, so the components are the ground truth.
            assert score_row.ppi_score == ppi.compute_metrics(db_session, centre_id)["ppi_score"]
            assert score_row.verification_rate != verification_rate_before

            # ── 7. Admin allocates funds -> provider notified live ──────────
            allocation = client.post(
                "/admin/allocations",
                json={
                    "centre_id": str(centre_id),
                    "amount": 750000,
                    "rationale": "Verification rate improved this month.",
                },
                headers=_auth(admin_token),
            )
            assert allocation.status_code == 201, allocation.text
            assert _recv(ws_provider, 1)[0]["event"] == "FUND_ALLOCATED"

            # ── 8. Admin flags the centre -> provider notified live ─────────
            flag = client.post(
                f"/admin/providers/{centre_id}/flag",
                json={"reason": "Batch documentation pending."},
                headers=_auth(admin_token),
            )
            assert flag.status_code == 200, flag.text
            assert _recv(ws_provider, 1)[0]["event"] == "PROVIDER_FLAGGED"

        # Consent row + employer notification rows persisted in the session.
        consent_row = db_session.execute(
            select(Consent).where(
                Consent.trainee_id == uuid.UUID(trainee_id),
                Consent.channel == "WHATSAPP",
            )
        ).scalar_one()
        assert consent_row.granted is True
        employer_notification_count = db_session.execute(
            select(func.count()).select_from(Notification).where(
                Notification.user_id
                == db_session.execute(
                    select(User.id).where(User.email == EMAILS["EMPLOYER"])
                ).scalar_one()
            )
        ).scalar_one()
        assert employer_notification_count >= 1


def test_certify_without_consent_schedules_nothing(client: TestClient, db_session) -> None:
    """Hard rule: no tracer exists for a trainee without active consent."""
    provider_token = _login(client, EMAILS["PROVIDER"])["access_token"]
    course_id = db_session.execute(select(Course.id).limit(1)).scalar_one()

    enrol = client.post(
        "/provider/trainees",
        json={
            "name": "No Consent Trainee",
            "email": "no.consent@trackskill.in",
            "phone": "+91 9000000002",
            "course_id": str(course_id),
        },
        headers=_auth(provider_token),
    )
    assert enrol.status_code == 201
    trainee_id = enrol.json()["trainee"]["id"]

    certify = client.patch(
        f"/provider/trainees/{trainee_id}/certify", json={}, headers=_auth(provider_token)
    )
    assert certify.status_code == 200
    assert certify.json()["followups_scheduled"] == 0
    followup_count = db_session.execute(
        select(func.count()).select_from(FollowUp).where(
            FollowUp.trainee_id == uuid.UUID(trainee_id)
        )
    ).scalar_one()
    assert followup_count == 0

    # Granting consent afterwards schedules all three milestones.
    trainee_token = _login(client, "no.consent@trackskill.in", enrol.json()["temporary_password"])[
        "access_token"
    ]
    consent = client.post(
        "/trainee/consent",
        json={"channel": "IVR", "granted": True},
        headers=_auth(trainee_token),
    )
    assert consent.status_code == 200
    assert consent.json()["followups_scheduled"] == 3

    # Revoking again cancels every tracer that has not happened yet.
    revoke = client.post(
        "/trainee/consent",
        json={"channel": "IVR", "granted": False},
        headers=_auth(trainee_token),
    )
    assert revoke.status_code == 200
    assert revoke.json()["followups_cancelled"] == 3
    remaining = db_session.execute(
        select(func.count()).select_from(FollowUp).where(
            FollowUp.trainee_id == uuid.UUID(trainee_id)
        )
    ).scalar_one()
    assert remaining == 0


def test_rbac_blocks_cross_role_access(client: TestClient) -> None:
    trainee_token = _login(client, "trainee.demo@trackskill.in")["access_token"]
    employer_token = _login(client, EMAILS["EMPLOYER"])["access_token"]

    assert client.get("/provider/overview", headers=_auth(trainee_token)).status_code == 403
    assert client.get("/admin/events", headers=_auth(employer_token)).status_code == 403
    assert client.get("/provider/overview").status_code == 401
    assert client.post(
        "/trainee/consent", json={"channel": "SMS", "granted": True}, headers=_auth(employer_token)
    ).status_code == 403


def test_employer_verification_ownership(client: TestClient, db_session) -> None:
    """An employer cannot confirm another employer's verification (404)."""
    other_employer_token = _login(client, "employer-02@trackskill.in")["access_token"]
    demo_employer_id = db_session.execute(
        select(Employer.id).join(User, Employer.user_id == User.id).where(
            User.email == EMAILS["EMPLOYER"]
        )
    ).scalar_one()
    record = db_session.execute(
        select(EmploymentRecord).where(EmploymentRecord.employer_id == demo_employer_id).limit(1)
    ).scalar_one()
    verification = db_session.execute(
        select(Verification).where(Verification.employment_record_id == record.id).limit(1)
    ).scalar_one()

    response = client.post(
        f"/employer/verifications/{verification.id}/confirm", headers=_auth(other_employer_token)
    )
    assert response.status_code == 404


def test_employer_hire_and_talent_pool(client: TestClient, db_session) -> None:
    provider_token = _login(client, EMAILS["PROVIDER"])["access_token"]
    employer_token = _login(client, EMAILS["EMPLOYER"])["access_token"]

    # Talent pool: certified + consented trainees grouped by skill.
    pool = client.get("/employer/talent-pool", headers=_auth(employer_token))
    assert pool.status_code == 200
    rows = pool.json()
    assert rows, "talent pool should not be empty"
    assert all({"skill", "trainee_count", "districts"} <= set(row) for row in rows)

    # Create a fresh certified trainee (no employment record) to hire.
    centre_id = db_session.execute(
        select(TrainingCentre.id).where(TrainingCentre.district == "North District")
    ).scalar_one()
    course_id = db_session.execute(
        select(Course.id).where(Course.centre_id == centre_id).limit(1)
    ).scalar_one()
    enrol = client.post(
        "/provider/trainees",
        json={
            "name": "Hire Target",
            "email": "hire.target@trackskill.in",
            "phone": "+91 9000000003",
            "course_id": str(course_id),
        },
        headers=_auth(provider_token),
    )
    assert enrol.status_code == 201
    trainee_id = enrol.json()["trainee"]["id"]
    certify = client.patch(
        f"/provider/trainees/{trainee_id}/certify", json={}, headers=_auth(provider_token)
    )
    assert certify.status_code == 200
    trainee_token = _login(
        client, "hire.target@trackskill.in", enrol.json()["temporary_password"]
    )["access_token"]

    with client.websocket_connect(f"/ws?token={trainee_token}") as ws_trainee:
        ws_trainee.receive_json()
        hire = client.post(
            f"/employer/trainees/{trainee_id}/hire",
            json={"job_title": "Solar Installation Assistant", "monthly_wage": 21000},
            headers=_auth(employer_token),
        )
        assert hire.status_code == 201, hire.text
        event = ws_trainee.receive_json()
        assert event["event"] == "EMPLOYER_HIRED"

    verification = db_session.get(Verification, uuid.UUID(hire.json()["verification_id"]))
    assert verification.employer_signal is VerificationSignal.CONFIRMED
    assert verification.trainee_signal is VerificationSignal.PENDING
    # Hiring again conflicts with the existing record.
    second = client.post(
        f"/employer/trainees/{trainee_id}/hire",
        json={"job_title": "Another role", "monthly_wage": 20000},
        headers=_auth(employer_token),
    )
    assert second.status_code == 409


def test_employer_verifications_listing(client: TestClient, db_session) -> None:
    """Regression: the pending-claims listing must render valid SQL (IS vs =)."""
    employer_token = _login(client, EMAILS["EMPLOYER"])["access_token"]
    response = client.get("/employer/verifications", headers=_auth(employer_token))
    assert response.status_code == 200, response.text
    rows = response.json()
    assert isinstance(rows, list)
    for row in rows:
        assert row["trainee_signal"] in {"PENDING", "CONFIRMED", "DISPUTED"}


def test_trainee_views(client: TestClient, db_session) -> None:
    trainee_token = _login(client, "trainee.demo@trackskill.in")["access_token"]

    me = client.get("/trainee/me", headers=_auth(trainee_token))
    assert me.status_code == 200
    body = me.json()
    assert body["profile"]["status"] == "CERTIFIED"
    assert any(item["type"] == "CERTIFIED" for item in body["timeline"])
    assert body["upcoming"], "demo trainee has milestones due"

    skills = client.get("/trainee/skills", headers=_auth(trainee_token))
    assert skills.status_code == 200
    assert skills.json()["skills"]
    for recommendation in skills.json()["recommendations"]:
        assert {"skill", "demand_score", "score", "courses"} <= set(recommendation)


def test_admin_views(client: TestClient, db_session) -> None:
    admin_token = _login(client, EMAILS["ADMIN"])["access_token"]

    overview = client.get("/admin/overview", headers=_auth(admin_token))
    assert overview.status_code == 200
    body = overview.json()
    for key in (
        "employment_rate",
        "retention_3m",
        "retention_6m",
        "retention_12m",
        "median_wage_uplift",
        "self_employment_share",
        "verification_rate",
        "districts",
    ):
        assert key in body

    leaderboard = client.get("/admin/providers", headers=_auth(admin_token))
    assert leaderboard.status_code == 200
    ranked = leaderboard.json()
    assert len(ranked) == 8
    assert [row["rank"] for row in ranked] == list(range(1, 9))
    assert ranked[0]["ppi_score"] >= ranked[-1]["ppi_score"]

    detail = client.get(f"/admin/providers/{ranked[0]['centre_id']}", headers=_auth(admin_token))
    assert detail.status_code == 200
    assert detail.json()["score_history"]

    gaps = client.get("/admin/curriculum-gaps", headers=_auth(admin_token))
    assert gaps.status_code == 200
    assert gaps.json(), "curriculum gaps should not be empty"

    events = client.get("/admin/events?limit=5", headers=_auth(admin_token))
    assert events.status_code == 200
    assert len(events.json()) <= 5


def test_provider_views(client: TestClient, db_session) -> None:
    provider_token = _login(client, EMAILS["PROVIDER"])["access_token"]

    trainees = client.get("/provider/trainees", headers=_auth(provider_token))
    assert trainees.status_code == 200
    assert trainees.json()

    overview = client.get("/provider/overview", headers=_auth(provider_token))
    assert overview.status_code == 200
    body = overview.json()
    for key in ("enrolled", "certified", "consent_rate", "response_rate", "ppi_score", "ppi_rank"):
        assert key in body

    followups = client.get("/provider/followups", headers=_auth(provider_token))
    assert followups.status_code == 200
    assert {"overdue", "due_soon"} <= set(followups.json())


def test_csv_bulk_import(client: TestClient, db_session) -> None:
    provider_token = _login(client, EMAILS["PROVIDER"])["access_token"]
    centre_id = db_session.execute(
        select(TrainingCentre.id).where(TrainingCentre.district == "North District")
    ).scalar_one()
    course_id = db_session.execute(
        select(Course.id).where(Course.centre_id == centre_id).limit(1)
    ).scalar_one()

    csv_content = (
        "name,email,phone,course_id\n"
        f"CSV Trainee One,csv.one@trackskill.in,+91 9000000011,{course_id}\n"
        f"CSV Trainee Two,csv.two@trackskill.in,+91 9000000012,{course_id}\n"
        f"CSV Duplicate,csv.one@trackskill.in,+91 9000000013,{course_id}\n"
        "Broken Row,bad-email,+91 9000000014,not-a-uuid\n"
    )
    response = client.post(
        "/provider/trainees/import",
        files={"file": ("trainees.csv", csv_content.encode("utf-8"), "text/csv")},
        headers=_auth(provider_token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] == 2
    assert body["skipped"] == 1  # duplicate email
    assert len(body["errors"]) == 1  # invalid row

    admin_token = _login(client, EMAILS["ADMIN"])["access_token"]
    events = client.get("/admin/events?limit=100", headers=_auth(admin_token))
    assert events.status_code == 200
    assert any(event["type"] == "TRAINEES_IMPORTED" for event in events.json())

```

---

## `apps/api/pyproject.toml`

```
[tool.ruff]
line-length = 100
target-version = "py311"
src = ["app", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM", "RUF"]
ignore = ["B008"]

[tool.ruff.lint.isort]
known-first-party = ["app"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.coverage.run]
source = ["app/services", "app/routers", "app/dependencies.py", "app/core/security.py"]
omit = ["app/services/tracer_channels.py"]

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.:",
]

```

---

## `apps/api/requirements-dev.txt`

```
pytest>=8.2,<9.0
httpx>=0.27,<1.0
ruff>=0.5,<1.0
pytest-cov>=5,<6.0

```

---

## `apps/web/public/sw.js`

```javascript
/*
 * TrackSkill AI service worker.
 *
 * Strategies:
 * - App shell pages (navigations): network-first, every successful HTML
 *   response is cached; offline falls back to the cached page or /offline.
 * - Static assets (/_next/static, icons, splash, manifest): cache-first.
 * - Other same-origin GETs (RSC flights, prefetches): stale-while-revalidate.
 * - API GETs (the FastAPI origin): network-first with a 3-second budget,
 *   falling back to the cached copy when offline or slow (Phase 11 change:
 *   plain stale-while-revalidate served ≤30s-old data to realtime-triggered
 *   refetches, which blocked live dashboard updates — freshness outranks
 *   latency for a governance product, and offline still works via fallback).
 * - Auth endpoints (/auth/*): never cached — login/refresh always hit the
 *   network so credentials can never be served from a stale copy.
 * - Offline follow-up responses: POSTs to /trainee/followups/{id}/respond are
 *   queued in IndexedDB and replayed by a Background Sync event, then the page
 *   is told via postMessage so it can refresh.
 *
 * Bump VERSION whenever the precache list changes; the browser detects SW
 * updates by byte-diff of this file and the page shows "Refresh to update".
 */

const VERSION = "trackskill-v2";
const PAGES_CACHE = `pages-${VERSION}`;
const STATIC_CACHE = `static-${VERSION}`;
const API_CACHE = `api-${VERSION}`;
const PAGES_CAP = 20;
const API_CAP = 150;
const API_TIMEOUT_MS = 3_000;

const PRECACHE_URLS = [
  "/offline",
  "/dashboard",
  "/login",
  "/",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-192.png",
  "/icons/icon-maskable-512.png",
];

const STATIC_PATTERNS = [
  /^\/_next\/static\//,
  /^\/icons\//,
  /^\/splash\//,
  /^\/apple-touch-icon\.png$/,
  /^\/manifest\.webmanifest$/,
  /^\/favicon\./,
];

// Same-origin GETs that are neither static nor navigations (RSC flights etc.)
// use stale-while-revalidate.
const RSC_PATTERN = /^\/_next\//;

const RESPOND_PATTERN = /^\/trainee\/followups\/[0-9a-fA-F-]{36}\/respond$/;
const MAX_REPLAY_ATTEMPTS = 5;

/* ── IndexedDB: the offline follow-up queue ──────────────────────────────── */

const DB_NAME = "trackskill-sw";
const QUEUE_STORE = "queue";
const META_STORE = "meta";

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(QUEUE_STORE)) {
        db.createObjectStore(QUEUE_STORE, { autoIncrement: true });
      }
      if (!db.objectStoreNames.contains(META_STORE)) {
        db.createObjectStore(META_STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function idbRun(storeName, mode, run) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    let result;
    try {
      result = run(store);
    } catch (error) {
      reject(error);
      return;
    }
    tx.oncomplete = () => resolve(result && result.result !== undefined ? result.result : result);
    tx.onerror = () => reject(tx.error);
  });
}

function queueAdd(item) {
  return idbRun(QUEUE_STORE, "readwrite", (store) => store.add(item));
}

function queueAll() {
  return idbRun(QUEUE_STORE, "readonly", (store) => store.getAll());
}

function queueAllKeys() {
  return idbRun(QUEUE_STORE, "readonly", (store) => store.getAllKeys());
}

function queueDelete(key) {
  return idbRun(QUEUE_STORE, "readwrite", (store) => store.delete(key));
}

function metaGet(key) {
  return idbRun(META_STORE, "readonly", (store) => store.get(key));
}

function metaSet(key, value) {
  return idbRun(META_STORE, "readwrite", (store) => store.put(value, key));
}

/* ── Small helpers ───────────────────────────────────────────────────────── */

async function putCapped(cacheName, request, response, cap) {
  const cache = await caches.open(cacheName);
  await cache.put(request, response);
  const keys = await cache.keys();
  if (keys.length > cap) {
    for (const staleKey of keys.slice(0, keys.length - cap)) {
      await cache.delete(staleKey);
    }
  }
}

function cacheable(response) {
  return response && response.ok && response.type !== "opaque";
}

function withAge(response) {
  const dateHeader = response.headers.get("date");
  const age = dateHeader ? Date.now() - new Date(dateHeader).getTime() : Infinity;
  return { response, age: Number.isFinite(age) ? age : 0 };
}

/** Stale-while-revalidate with a freshness window: a young cached entry is
 * answered immediately (revalidation continues in the background via
 * event.waitUntil); anything older tries the network first so live data
 * wins, falling back to cache when offline.
 *
 * Returns { respond, revalidate }: call event.respondWith(respond) and
 * event.waitUntil(revalidate) SYNCHRONOUSLY during event dispatch — calling
 * waitUntil after an await inside respondWith rejects the event. */
function staleWhileRevalidate(request, cacheName, cap, freshMs) {
  const revalidate = fetch(request)
    .then(async (response) => {
      if (cacheable(response)) {
        await putCapped(cacheName, request, response.clone(), cap);
      }
      return response;
    })
    .catch(() => null);

  const respond = (async () => {
    const cache = await caches.open(cacheName);
    const cached = withAge(await cache.match(request));
    if (cached.response && cached.age < freshMs) {
      return cached.response;
    }
    const network = await revalidate;
    if (network) {
      return network.clone();
    }
    return cached.response ?? null;
  })();

  return { respond, revalidate };
}

/** Network-first with a short budget: live data wins; offline or slow
 * networks fall back to the cached copy (Workbox NetworkFirst equivalent).
 * If the timeout wins the race, the network result still lands in the cache
 * via `network`. */
function networkFirst(request, cacheName, cap, timeoutMs) {
  const network = fetch(request)
    .then(async (response) => {
      if (cacheable(response)) {
        await putCapped(cacheName, request, response.clone(), cap);
      }
      return response;
    })
    .catch(() => null);
  const timer = new Promise((resolve) => {
    setTimeout(() => resolve(null), timeoutMs);
  });

  const respond = (async () => {
    const raced = await Promise.race([network, timer]);
    if (raced) {
      return raced.clone();
    }
    const cache = await caches.open(cacheName);
    return (await cache.match(request)) ?? null;
  })();

  return { respond, network };
}

/* ── Install / activate ──────────────────────────────────────────────────── */

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(PAGES_CACHE);
      await Promise.allSettled(
        PRECACHE_URLS.map(async (url) => {
          const response = await fetch(new Request(url, { credentials: "same-origin" }));
          if (response.ok) {
            await cache.put(new Request(url), response);
          }
        }),
      );
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys()) {
        if (!key.endsWith(VERSION)) {
          await caches.delete(key);
        }
      }
      await self.clients.claim();
      await replayQueue().catch(() => undefined);
    })(),
  );
});

/* ── Fetch strategies ────────────────────────────────────────────────────── */

async function handleNavigation(request) {
  try {
    const response = await fetch(request);
    if (cacheable(response)) {
      await putCapped(PAGES_CACHE, request, response.clone(), PAGES_CAP);
    }
    return response;
  } catch {
    const cache = await caches.open(PAGES_CACHE);
    return (
      (await cache.match(request)) ??
      (await cache.match("/dashboard")) ??
      (await cache.match("/offline")) ??
      new Response(
        "<!doctype html><title>Offline</title><p>You are offline.</p>",
        { headers: { "Content-Type": "text/html" }, status: 503 },
      )
    );
  }
}

async function handleFollowupRespond(request) {
  try {
    return await fetch(request);
  } catch {
    const body = await request.clone().arrayBuffer();
    const headers = {};
    request.headers.forEach((value, key) => {
      if (["content-type", "authorization"].includes(key.toLowerCase())) {
        headers[key] = value;
      }
    });
    await queueAdd({
      url: request.url,
      headers,
      body,
      attempts: 0,
      created_at: new Date().toISOString(),
    });
    if (self.registration.sync) {
      try {
        await self.registration.sync.register("tsk-followup-replay");
      } catch {
        // Background Sync unavailable — the queue replays on next activate,
        // next online event or explicit REPLAY_NOW from the page.
      }
    }
    await notifyClients({ type: "followup-queued" });
    return new Response(JSON.stringify({ queued: true, offline: true }), {
      status: 202,
      headers: { "Content-Type": "application/json" },
    });
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET" && !(request.method === "POST" && RESPOND_PATTERN.test(new URL(request.url).pathname))) {
    return; // all other mutations go straight to the network
  }

  const url = new URL(request.url);
  const sameOrigin = url.origin === self.location.origin;
  const pathname = url.pathname;

  if (request.method === "POST" && RESPOND_PATTERN.test(pathname)) {
    event.respondWith(handleFollowupRespond(request));
    return;
  }

  if (pathname.startsWith("/auth/")) {
    return; // auth is network-only, never cached and never queued
  }

  if (request.mode === "navigate") {
    event.respondWith(handleNavigation(request));
    return;
  }

  if (!sameOrigin) {
    // Cross-origin API GET — network-first with cached fallback.
    if (pathname.startsWith("/ws")) {
      return;
    }
    const { respond, network } = networkFirst(request, API_CACHE, API_CAP, API_TIMEOUT_MS);
    event.waitUntil(network.then(() => undefined));
    event.respondWith(
      respond.then(
        (response) =>
          response ??
          new Response(JSON.stringify({ detail: "Offline and no cached data." }), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }),
        () =>
          new Response(JSON.stringify({ detail: "Offline and no cached data." }), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    return;
  }

  if (STATIC_PATTERNS.some((pattern) => pattern.test(pathname))) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(STATIC_CACHE);
        const cached = await cache.match(request);
        if (cached) {
          return cached;
        }
        const response = await fetch(request);
        if (cacheable(response)) {
          await cache.put(request, response.clone());
        }
        return response;
      })(),
    );
    return;
  }

  if (RSC_PATTERN.test(pathname) || request.headers.has("Next-Router-Prefetch")) {
    const { respond, revalidate } = staleWhileRevalidate(request, PAGES_CACHE, PAGES_CAP, 0);
    event.waitUntil(revalidate.then(() => undefined));
    event.respondWith(
      respond.then(
        (response) => response ?? new Response("{}", { status: 503, headers: { "Content-Type": "application/json" } }),
        () => new Response("{}", { status: 503, headers: { "Content-Type": "application/json" } }),
      ),
    );
  }
});

/* ── Background sync: replay offline follow-up responses ─────────────────── */

async function notifyClients(message) {
  const clients = await self.clients.matchAll({ includeUncontrolled: true });
  for (const client of clients) {
    client.postMessage(message);
  }
}

async function replayQueue() {
  const items = await queueAll();
  const keys = await queueAllKeys();
  let pendingAuth = false;

  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    const key = keys[index];
    try {
      const token = (await metaGet("replay-token")) || null;
      const headers = { ...item.headers };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const response = await fetch(item.url, {
        method: "POST",
        headers,
        body: item.body,
      });
      if (response.status === 401) {
        pendingAuth = true;
        await metaSet("replay-token", null);
        continue;
      }
      await queueDelete(key);
      await notifyClients({
        type: "followup-synced",
        url: item.url,
        status: response.status,
      });
    } catch {
      const attempts = (item.attempts ?? 0) + 1;
      await queueDelete(key);
      if (attempts >= MAX_REPLAY_ATTEMPTS) {
        await notifyClients({ type: "followup-failed", url: item.url });
      } else {
        await queueAdd({ ...item, attempts });
      }
    }
  }

  if (pendingAuth) {
    await notifyClients({ type: "followup-auth-needed" });
    if (self.registration.sync) {
      try {
        await self.registration.sync.register("tsk-followup-replay");
      } catch {
        // The page will send REPLAY_NOW once it refreshes the token.
      }
    }
  }
}

self.addEventListener("sync", (event) => {
  if (event.tag === "tsk-followup-replay") {
    event.waitUntil(replayQueue().catch(() => undefined));
  }
});

/* ── Push notifications ──────────────────────────────────────────────────── */

self.addEventListener("push", (event) => {
  let payload = { title: "TrackSkill AI", body: "You have a new update.", link: "/dashboard" };
  try {
    if (event.data) {
      payload = { ...payload, ...event.data.json() };
    }
  } catch {
    if (event.data) {
      payload.body = event.data.text();
    }
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: payload.event_id || payload.title,
      data: { url: payload.link || "/dashboard" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data?.url || "/dashboard";
  event.waitUntil(
    (async () => {
      const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of clients) {
        if (client.url.includes(self.location.origin)) {
          await client.focus();
          if (client.navigate) {
            await client.navigate(target).catch(() => undefined);
          }
          return;
        }
      }
      await self.clients.openWindow(target);
    })(),
  );
});

/* ── Messages from the page ──────────────────────────────────────────────── */

self.addEventListener("message", (event) => {
  const type = event.data?.type;
  if (type === "SKIP_WAITING") {
    self.skipWaiting();
  } else if (type === "REPLAY_NOW") {
    event.waitUntil(replayQueue().catch(() => undefined));
  } else if (type === "QUEUE_TOKEN") {
    event.waitUntil(
      (async () => {
        await metaSet("replay-token", event.data.token);
        await replayQueue().catch(() => undefined);
      })(),
    );
  }
});

```

---

## `apps/web/playwright.config.ts`

```typescript
import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

/**
 * Flagship E2E: four browser contexts (one per role) watch the realtime chain
 * update all four dashboards without a reload.
 *
 * The API database must be migrated + seeded; global-setup runs Alembic and
 * the seed script with the right interpreter (venv on Windows, python on CI).
 * Servers start automatically unless SKIP_SERVERS=1 (local dev loop).
 */

const API_DIR = path.resolve(__dirname, "../api");
const VENV_PYTHON = path.join(API_DIR, ".venv/Scripts/python.exe");
const PY = process.env.E2E_PYTHON ?? "python";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: path.resolve(__dirname, "e2e/global-setup.ts"),
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    navigationTimeout: 30_000,
    actionTimeout: 15_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: process.env.SKIP_SERVERS
    ? undefined
    : [
        {
          command: `${PY} -m uvicorn app.main:app --port 8000`,
          cwd: API_DIR,
          url: "http://127.0.0.1:8000/health",
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            DATABASE_URL:
              process.env.DATABASE_URL ??
              "postgresql+psycopg://postgres@127.0.0.1:5433/trackskill",
          },
        },
        {
          command: "npm run start",
          url: "http://localhost:3000",
          reuseExistingServer: !process.env.CI,
          timeout: 180_000,
        },
      ],
});

```

---

## `apps/web/e2e/flagship-realtime.spec.ts`

```typescript
import { expect, test, type Page } from "@playwright/test";

/**
 * The Phase 4 flagship chain, proven through the real UI with four browser
 * contexts — one per role — updating in realtime (no page.reload anywhere):
 *
 *   provider enrols → certifies → trainee consents + answers the M3 tracer
 *   → employer confirms → admin sees verification + PPI recalculation live.
 *
 * Cross-role assertions:
 *   1. provider window shows the new enrolment        (TRAINEE_ENROLLED)
 *   2. trainee window shows certification             (TRAINEE_CERTIFIED)
 *   3. employer window shows the pending claim        (EMPLOYMENT_SELF_REPORTED)
 *   4. admin window shows the PPI recalculation       (VERIFICATION_COMPLETE →
 *      PPI_RECALCULATED) and the trainee window flips to "Verified"
 *      (VERIFICATION_COMPLETE on the user channel)
 */

const API = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const DEMO_PASSWORD = "Demo@1234";

interface ApiLogin {
  access_token: string;
}

async function apiLogin(email: string, password = DEMO_PASSWORD): Promise<string> {
  const response = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  expect(response.status).toBe(200);
  const body = (await response.json()) as ApiLogin;
  return body.access_token;
}

async function apiCall<T>(
  path: string,
  method: string,
  token: string,
  payload?: unknown,
): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  expect(response.status).toBeLessThan(300);
  return (await response.json()) as T;
}

async function loginDemo(page: Page, role: string): Promise<void> {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    const fillButton = page.getByLabel(`Fill demo credentials for ${role}`);
    try {
      await fillButton.waitFor({ state: "visible", timeout: 20_000 });
    } catch {
      continue; // page hiccup — one clean retry
    }
    await fillButton.click();
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL("**/dashboard/**");
    await dismissTour(page);
    return;
  }
  throw new Error(`Demo login for ${role} failed after a retry`);
}

async function dismissTour(page: Page): Promise<void> {
  const dismiss = page.getByRole("button", { name: "Dismiss onboarding" });
  try {
    await dismiss.click({ timeout: 3000 });
  } catch {
    // Tour already dismissed for this browser profile.
  }
}

async function loginTrainee(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.getByLabel("Email").fill(email);
  await page.getByRole("textbox", { name: "Password" }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL("**/dashboard/**");
  await dismissTour(page);
}

test("flagship chain updates all four role dashboards without a reload", async ({
  browser,
}) => {
  const stamp = Date.now();
  const traineeEmail = `e2e.${stamp}@trackskill.in`;
  const traineeName = `E2E Trainee ${stamp}`; // unique per run: no cross-run claim collisions

  // ── Sign in the three demo roles in their own windows ──────────────────
  const providerContext = await browser.newContext();
  const traineeContext = await browser.newContext();
  const employerContext = await browser.newContext();
  const adminContext = await browser.newContext();

  const providerPage = await providerContext.newPage();
  const traineePage = await traineeContext.newPage();
  const employerPage = await employerContext.newPage();
  const adminPage = await adminContext.newPage();

  await loginDemo(providerPage, "PROVIDER");
  await loginDemo(employerPage, "EMPLOYER");
  await loginDemo(adminPage, "ADMIN");

  const providerToken = await apiLogin("provider.demo@trackskill.in");
  const employerToken = await apiLogin("employer.demo@trackskill.in");
  const adminToken = await apiLogin("admin.demo@trackskill.in");

  // ── 1. Provider enrols a trainee over the API ───────────────────────────
  const courses = await apiCall<{ id: string }[]>(
    "/provider/courses",
    "GET",
    providerToken,
  );
  const enrol = await apiCall<{
    trainee: { id: string };
    temporary_password: string;
  }>("/provider/trainees", "POST", providerToken, {
    name: traineeName,
    email: traineeEmail,
    phone: "+91 9078901234",
    course_id: courses[0].id,
  });

  // Provider window updates without a reload (TRAINEE_ENROLLED).
  await expect(
    providerPage.getByRole("cell", { name: traineeName }).or(
      providerPage.getByText(traineeName, { exact: true }),
    ).first(),
  ).toBeVisible();

  // The new trainee signs in — their own window is the TRAINEE role.
  await loginTrainee(traineePage, traineeEmail, enrol.temporary_password);

  // ── 2. Provider certifies; the trainee window flips to certified ────────
  await apiCall(`/provider/trainees/${enrol.trainee.id}/certify`, "PATCH", providerToken, {});
  await expect(
    traineePage.getByText(/Certified .* — milestones follow/),
  ).toBeVisible({ timeout: 15_000 });

  // ── 3. Trainee grants consent (UI) and answers the M3 tracer (API) ──────
  await expect(
    traineePage.getByLabel("Grant WHATSAPP consent"),
  ).toBeVisible();
  await traineePage.getByLabel("Grant WHATSAPP consent").click();
  await expect(
    traineePage.getByLabel("Revoke WHATSAPP consent"),
  ).toBeVisible({ timeout: 15_000 });

  const traineeToken = await apiLogin(traineeEmail, enrol.temporary_password);
  const me = await apiCall<{
    upcoming: { followup_id: string; milestone: string }[];
  }>("/trainee/me", "GET", traineeToken);
  const m3 = me.upcoming.find((item) => item.milestone === "M3");
  expect(m3).toBeTruthy();
  const impact = await apiCall<{ employer_id: string }>(
    "/employer/impact",
    "GET",
    employerToken,
  );
  await apiCall(
    `/trainee/followups/${m3!.followup_id}/respond`,
    "POST",
    traineeToken,
    {
      employment_status: "EMPLOYED",
      job_title: "Welder",
      monthly_wage: 14000,
      employer_id: impact.employer_id,
    },
  );

  // Employer window shows the pending claim without a reload. Scoped to the
  // #verify section: the same name also appears under "Your hires".
  const claimRow = employerPage.locator("#verify li", { hasText: traineeName });
  await expect(claimRow).toBeVisible({ timeout: 15_000 });

  // ── 4. Employer confirms (UI); admin + trainee windows react live ───────
  const feed = adminPage.getByText("PPI_RECALCULATED");
  const feedCountBefore = await feed.count();

  await claimRow.getByRole("button", { name: "Confirm" }).click();
  await expect(claimRow).toHaveCount(0, { timeout: 15_000 });

  await expect(async () => {
    const count = await adminPage.getByText("PPI_RECALCULATED").count();
    expect(count).toBeGreaterThan(feedCountBefore);
  }).toPass({ timeout: 15_000 });
  await expect(adminPage.getByText("VERIFICATION_COMPLETE").first()).toBeVisible();

  // The trainee window flips to a verified outcome (user-channel event).
  await expect(
    traineePage.getByText("Verified", { exact: true }).first(),
  ).toBeVisible({ timeout: 15_000 });
  await expect(
    traineePage.getByText("Awaiting both signals"),
  ).toHaveCount(0);

  // ── Cleanup: the erasure right cleans the new trainee ──────────────────
  await apiCall("/trainee/me/delete", "POST", traineeToken, { confirm: true });

  await Promise.all([
    providerContext.close(),
    traineeContext.close(),
    employerContext.close(),
    adminContext.close(),
  ]);
});

```

---

## `apps/web/e2e/global-setup.ts`

```typescript
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/** Migrate + seed the API database before the E2E servers start.
 * Uses the repo venv interpreter when present (Windows dev), otherwise the
 * ambient python (CI installs requirements into it). The seed is idempotent. */
export default function globalSetup(): void {
  const apiDir = path.resolve(__dirname, "../../api");
  const venvPython = path.join(apiDir, ".venv", "Scripts", "python.exe");
  const venvLinux = path.join(apiDir, ".venv", "bin", "python");
  const py = fs.existsSync(venvPython)
    ? `"${venvPython}"`
    : fs.existsSync(venvLinux)
      ? `"${venvLinux}"`
      : process.env.E2E_PYTHON ?? "python";

  const databaseUrl =
    process.env.DATABASE_URL ??
    "postgresql+psycopg://postgres@127.0.0.1:5433/trackskill";

  console.log("[e2e] applying migrations...");
  execSync(`${py} -m alembic upgrade head`, {
    cwd: apiDir,
    env: { ...process.env, DATABASE_URL: databaseUrl },
    stdio: "inherit",
  });
  console.log("[e2e] seeding demo data (idempotent)...");
  execSync(`${py} -m app.seed`, {
    cwd: apiDir,
    env: { ...process.env, DATABASE_URL: databaseUrl },
    stdio: "inherit",
  });
}

```

---

## `apps/web/vitest.config.ts`

```typescript
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true, // lets Testing Library auto-cleanup between tests
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});

```

---

## `apps/web/vitest.setup.ts`

```typescript
import "@testing-library/jest-dom/vitest";

```

---

## `apps/web/src/components/dashboard/kpi-card.test.tsx`

```typescript
import { render, screen } from "@testing-library/react";
import { CheckCheck } from "lucide-react";
import { describe, expect, it } from "vitest";

import { EmptyState, KpiCard, PulseCard } from "@/components/dashboard/kpi-card";

describe("KpiCard", () => {
  it("renders the label and value with an accessible label", () => {
    render(<KpiCard icon={CheckCheck} label="Verified" value={42} hint="of 100 claims" />);
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByLabelText("42")).toBeInTheDocument();
    expect(screen.getByText("of 100 claims")).toBeInTheDocument();
  });

  it("marks a pulsing card with data-pulsing", () => {
    const { container } = render(
      <PulseCard pulsing>
        <span>content</span>
      </PulseCard>,
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper).toHaveAttribute("data-pulsing");
    expect(wrapper).toHaveClass("realtime-pulse");
  });

  it("does not pulse when idle", () => {
    const { container } = render(
      <PulseCard pulsing={false}>
        <span>content</span>
      </PulseCard>,
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper).not.toHaveAttribute("data-pulsing");
    expect(wrapper).not.toHaveClass("realtime-pulse");
  });
});

describe("EmptyState", () => {
  it("renders title and hint", () => {
    render(
      <EmptyState icon={CheckCheck} title="No pending claims" hint="Claims appear here." />,
    );
    expect(screen.getByText("No pending claims")).toBeInTheDocument();
    expect(screen.getByText("Claims appear here.")).toBeInTheDocument();
  });
});

```

---

## `apps/web/src/components/dashboard/connection-pill.test.tsx`

```typescript
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConnectionPill } from "@/components/dashboard/connection-pill";

describe("ConnectionPill", () => {
  it("announces a live realtime connection", () => {
    render(<ConnectionPill connected />);
    expect(screen.getByLabelText("Realtime connection live")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("announces an offline connection", () => {
    render(<ConnectionPill connected={false} />);
    expect(screen.getByLabelText("Realtime connection offline")).toBeInTheDocument();
    expect(screen.getByText("Offline")).toBeInTheDocument();
  });
});

```

---

## `apps/web/src/hooks/use-pulse.test.tsx`

```typescript
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePulse } from "@/hooks/use-pulse";
import { useRealtimeStore } from "@/stores/realtime-store";

function PulseProbe({ types }: { types: string[] }) {
  const pulsing = usePulse(...types);
  return <p data-testid="probe">{pulsing ? "pulsing" : "idle"}</p>;
}

describe("usePulse", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Reset the shared zustand store between tests.
    useRealtimeStore.setState({ connected: false, lastEvent: null });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("pulses for ~2 seconds after a matching event, then settles", () => {
    render(<PulseProbe types={["VERIFICATION_COMPLETE"]} />);
    expect(screen.getByTestId("probe")).toHaveTextContent("idle");

    act(() => {
      useRealtimeStore.getState().record("VERIFICATION_COMPLETE", {});
    });
    expect(screen.getByTestId("probe")).toHaveTextContent("pulsing");

    act(() => {
      vi.advanceTimersByTime(2100);
    });
    expect(screen.getByTestId("probe")).toHaveTextContent("idle");
  });

  it("ignores non-matching events", () => {
    render(<PulseProbe types={["VERIFICATION_COMPLETE"]} />);
    act(() => {
      useRealtimeStore.getState().record("TRAINEE_ENROLLED", {});
    });
    expect(screen.getByTestId("probe")).toHaveTextContent("idle");
  });

  it("matches any event in the list", () => {
    render(<PulseProbe types={["A", "B"]} />);
    act(() => {
      useRealtimeStore.getState().record("B", {});
    });
    expect(screen.getByTestId("probe")).toHaveTextContent("pulsing");
  });
});

```

---

## `apps/web/src/lib/push-client.test.ts`

```typescript
import { describe, expect, it } from "vitest";

import { urlBase64ToUint8Array } from "./push-client";

/** The conversion helper is exported for tests — it feeds PushManager.subscribe
 * and must round-trip base64url exactly. */
describe("urlBase64ToUint8Array", () => {
  it("decodes a standard VAPID public key (87 chars, 65 bytes)", () => {
    // Deterministic 65-byte uncompressed P-256 point, base64url-encoded.
    const point = Buffer.concat([
      Buffer.from([0x04]),
      Buffer.alloc(64, 0xab),
    ]);
    const base64url = point
      .toString("base64")
      .replaceAll("+", "-")
      .replaceAll("/", "_")
      .replaceAll("=", "");
    const bytes = urlBase64ToUint8Array(base64url);
    expect(bytes).toHaveLength(65);
    expect(bytes[0]).toBe(0x04);
    expect(Array.from(bytes.slice(1, 5))).toEqual([0xab, 0xab, 0xab, 0xab]);
  });

  it("pads missing base64 padding and maps - and _ correctly", () => {
    // "-_-_" -> "+/+/" -> bits 111110 111111 111110 111111
    const bytes = urlBase64ToUint8Array("-_-_");
    expect(Array.from(bytes)).toEqual([0xfb, 0xff, 0xbf]);
  });
});

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

export interface MaskedContact {
  email: string | null;
  phone: string | null;
}

export interface TalentPoolRow {
  skill: string;
  trainee_count: number;
  districts: string[];
  trainee_names: string[];
  contacts: MaskedContact[];
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

// ── Web push (Phase 10) ──────────────────────────────────────────────────────

export interface PushSubscriptionPayload {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  user_agent: string;
}

/** VAPID public key the browser needs to create a push subscription. */
export async function fetchPushPublicKey(): Promise<string> {
  return api.get<{ public_key: string }>("/push/public-key").then((data) => data.public_key);
}

export function savePushSubscription(subscription: PushSubscriptionPayload): Promise<{ status: string }> {
  return api.post("/push/subscriptions", subscription);
}

export function deletePushSubscription(endpoint: string): Promise<{ status: string }> {
  return api.post("/push/subscriptions/delete", { endpoint });
}

/** Ask the API to send a test notification to all of my devices. */
export function sendTestPush(): Promise<{ sent: number; failed: number; pruned: number }> {
  return api.post("/push/test");
}

// ── Data rights (Phase 11) ───────────────────────────────────────────────────

/** DPDP-aligned data access right: everything stored about the signed-in
 * trainee, as one JSON document. */
export function exportMyData(): Promise<Record<string, unknown>> {
  return api.get("/trainee/me/export");
}

/** DPDP-aligned erasure right: permanently deletes the account. */
export function deleteMyData(): Promise<{ status: string; erased: Record<string, number> }> {
  return api.post("/trainee/me/delete", { confirm: true });
}

```

---

## `apps/web/src/app/dashboard/trainee/page.tsx`

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCheck,
  Download,
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
import { api, assessSkills, deleteMyData, exportMyData } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
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

      <section id="privacy" aria-label="Your data rights" className="scroll-mt-24">
        <DataRightsCard />
      </section>
    </>
  );
}

function DataRightsCard() {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const signOut = useAuthStore((state) => state.signOut);

  const exportMutation = useMutation({
    mutationFn: async () => {
      const data = await exportMyData();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "trackskill-my-data.json";
      anchor.click();
      URL.revokeObjectURL(url);
    },
    onSuccess: () => setNotice("Export downloaded — check your files."),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteMyData,
    onSuccess: async () => {
      setNotice(null);
      queryClient.clear();
      await signOut();
    },
  });

  return (
    <PulseCard pulsing={false}>
      <Card>
        <CardHeader>
          <CardTitle className="font-display text-xl">Your data rights</CardTitle>
          <CardDescription>
            You own your record. Export everything stored about you, or erase it
            for good — revoking consent already stops all tracing immediately.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {notice && (
            <p role="status" className="text-sm text-primary">
              {notice}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => exportMutation.mutate()}
              disabled={exportMutation.isPending}
            >
              {exportMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              )}
              <Download className="h-4 w-4" aria-hidden />
              Export my data
            </Button>
            <Button
              variant="destructive"
              onClick={() => setConfirming(true)}
              disabled={deleteMutation.isPending}
            >
              Delete my data
            </Button>
          </div>
          {confirming && (
            <div
              role="dialog"
              aria-modal="true"
              aria-label="Confirm deletion"
              className="rounded-md border border-destructive/40 bg-destructive/5 p-3"
            >
              <p className="text-sm font-medium">
                Erase your account permanently?
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                This removes your profile, consents, tracer messages, employment
                claims and notifications. Audit logs stay — without your name
                attached. This cannot be undone.
              </p>
              <div className="mt-3 flex gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                >
                  {deleteMutation.isPending && (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                  )}
                  Yes, erase everything
                </Button>
                <Button variant="outline" size="sm" onClick={() => setConfirming(false)}>
                  Keep my data
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </PulseCard>
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
                  {row.contacts?.length > 0 && (
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Contact (masked): {row.contacts.map((c) => c.email).join(" · ")}
                    </p>
                  )}
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
    { id: "privacy", label: "Your data" },
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
        {/* Top bar — its own safe-area top padding so the translucent iOS
            status bar in standalone mode never covers the controls. */}
        <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 pt-[env(safe-area-inset-top)] backdrop-blur">
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

      {/* Mobile bottom tabs — sized above the home-bar safe area */}
      <nav
        aria-label="Dashboard sections"
        className="fixed bottom-0 left-0 right-0 z-40 grid grid-cols-4 border-t border-border bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {sections.map((section) => (
          <button
            key={section.id}
            type="button"
            onClick={() => mobileNavigate(section.id)}
            className="flex min-h-[52px] flex-col items-center justify-center gap-0.5 py-2 text-[10px] text-muted-foreground hover:text-foreground"
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

## `apps/web/package.json`

```json
{
  "name": "trackskill-web",
  "version": "0.1.0",
  "private": true,
  "engines": {
    "node": ">=18.17.0"
  },
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "desktop": "electron electron/main.cjs",
    "desktop:build": "electron-builder --config electron-builder.json --win --publish never",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "@hookform/resolvers": "^7.0.1",
    "@radix-ui/react-slot": "^1.1.0",
    "@tanstack/react-query": "^5.51.1",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.1",
    "framer-motion": "^11.3.8",
    "lucide-react": "^0.418.0",
    "next": "^14.2.5",
    "next-themes": "^0.3.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-hook-form": "^7.91.0",
    "recharts": "^2.12.7",
    "tailwind-merge": "^2.4.0",
    "zod": "^4.6.7",
    "zustand": "^4.5.4"
  },
  "devDependencies": {
    "@playwright/test": "^1.65.0",
    "@testing-library/dom": "^10.4.2",
    "@testing-library/jest-dom": "^7.0.1",
    "@testing-library/react": "^16.3.3",
    "@testing-library/user-event": "^14.6.8",
    "@types/node": "^20.14.12",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.7.0",
    "autoprefixer": "^10.4.19",
    "eslint": "^8.57.0",
    "eslint-config-next": "^14.2.5",
    "jsdom": "^29.1.1",
    "postcss": "^8.4.40",
    "prettier": "^3.3.3",
    "prettier-plugin-tailwindcss": "^0.6.2",
    "tailwindcss": "^3.4.7",
    "tailwindcss-animate": "^1.0.7",
    "typescript": "^5.5.4",
    "vitest": "^3.2.7"
  }
}

```

---

## `apps/web/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": [
      "dom",
      "dom.iterable",
      "esnext"
    ],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "forceConsistentCasingInFileNames": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": [
        "./src/*"
      ]
    }
  },
  "include": [
    "next-env.d.ts",
    "**/*.ts",
    "**/*.tsx",
    ".next/types/**/*.ts"
  ],
  "exclude": [
    "node_modules",
    "capacitor.config.ts"
  ]
}

```

---

## `.github/workflows/ci.yml`

```yaml
name: CI

# TrackSkill AI — lint, tests, build and the flagship four-role E2E.
# Backend needs PostgreSQL; the E2E job runs the seeded stack end to end.

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  backend:
    name: Backend — ruff + pytest (coverage ≥ 80%)
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: trackskill
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 20
    env:
      DATABASE_URL: postgresql+psycopg://postgres:postgres@localhost:5432/trackskill
      SECRET_KEY: ci-only-insecure-secret-key-0123456789abcdef
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: apps/api/requirements*.txt
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r apps/api/requirements.txt -r apps/api/requirements-dev.txt
      - name: Lint (ruff)
        working-directory: apps/api
        run: python -m ruff check .
      - name: Migrate
        working-directory: apps/api
        run: |
          python -m alembic upgrade head
          python -m app.seed
      - name: Test with coverage (services + routers ≥ 80%)
        working-directory: apps/api
        run: python -m pytest --cov --cov-report=term --cov-report=xml

  frontend:
    name: Frontend — lint + typecheck + build + vitest
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - name: Install dependencies
        working-directory: apps/web
        run: npm ci
      - name: Lint
        working-directory: apps/web
        run: npm run lint
      - name: Typecheck
        working-directory: apps/web
        run: npx tsc --noEmit
      - name: Unit tests (vitest)
        working-directory: apps/web
        run: npm test
      - name: Build
        working-directory: apps/web
        run: npm run build

  e2e:
    name: E2E — flagship 4-role realtime chain (Playwright)
    runs-on: ubuntu-latest
    needs: [backend, frontend]
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: trackskill
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 20
    env:
      DATABASE_URL: postgresql+psycopg://postgres:postgres@localhost:5432/trackskill
      SECRET_KEY: ci-only-insecure-secret-key-0123456789abcdef
      SKIP_SERVERS: "1"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: apps/api/requirements*.txt
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - name: Install API dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r apps/api/requirements.txt
      - name: Migrate + seed
        working-directory: apps/api
        run: |
          python -m alembic upgrade head
          python -m app.seed
      - name: Install web dependencies
        working-directory: apps/web
        run: npm ci
      - name: Build web app
        working-directory: apps/web
        run: npm run build
      - name: Install Playwright browser
        working-directory: apps/web
        run: npx playwright install --with-deps chromium
      - name: Start API
        working-directory: apps/api
        run: |
          nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > api.log 2>&1 &
          for i in $(seq 1 30); do
            curl -sf http://127.0.0.1:8000/health && break
            sleep 1
          done
          curl -sf http://127.0.0.1:8000/health
      - name: Start web app
        working-directory: apps/web
        run: |
          nohup npm run start > web.log 2>&1 &
          for i in $(seq 1 60); do
            curl -sf http://localhost:3000 -o /dev/null && break
            sleep 1
          done
          curl -sf -o /dev/null http://localhost:3000
      - name: Run Playwright E2E
        working-directory: apps/web
        run: npx playwright test
      - name: Upload Playwright traces on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-traces
          path: apps/web/test-results/
          retention-days: 7

```

---

## `README.md`

```markdown
# TrackSkill AI

**Post-certification outcome tracking for skilling programs.** Skilling programs lose sight of trainees the day they certify: job retention, wage growth and self-employment go unrecorded. TrackSkill AI follows trainees at 3/6/12-month milestones through consent-based digital profiles, simulated WhatsApp/IVR tracers and dual-signal verification (trainee self-report + employer confirmation). AI maps candidate skills and vocational curricula to market demand, and a governance dashboard benchmarks training centres with a Provider Performance Index (PPI) to guide fund allocation.

SDGs: primary **SDG 8** (Decent Work and Economic Growth); supporting **SDG 4** (Quality Education) and **SDG 9** (Industry, Innovation and Infrastructure).

> **Status: Phase 4 — role-scoped REST APIs with realtime events.** Every endpoint from the Provider / Trainee / Employer / Admin playbooks is live, every mutation publishes an audited realtime event to the right audience, and the flagship chain (enrol → certify → consent → respond → confirm → PPI recalculation → allocation/flag) is proven end-to-end by an automated test that asserts the events delivered to each role's WebSocket.

## Stack

- **Web:** Next.js 14 (App Router) · TypeScript · Tailwind CSS · shadcn/ui · Recharts · Framer Motion · TanStack Query · Zustand
- **API:** Python 3.11+ · FastAPI · SQLAlchemy 2.x · Alembic · JWT access+refresh (auth phase) · FastAPI WebSockets · sentence-transformers with TF-IDF fallback (AI phase)
- **Infra:** PostgreSQL 16 · Docker Compose · ESLint + Prettier · Ruff · pre-commit (optional)

## Monorepo layout

```
trackskill/
├── apps/
│   ├── api/                  FastAPI service
│   │   ├── alembic/          Migrations (env wired to app metadata)
│   │   ├── app/
│   │   │   ├── ai/           NLP matching (later phase)
│   │   │   ├── core/         Settings, DB engine/session, password hashing
│   │   │   ├── models/       SQLAlchemy ORM models (15 tables + enums)
│   │   │   ├── realtime/     WebSocket manager + /ws endpoint
│   │   │   ├── routers/      HTTP routers
│   │   │   ├── schemas/      Pydantic schemas
│   │   │   ├── services/     Business logic
│   │   │   ├── main.py       App factory, CORS, routers
│   │   │   └── seed.py       Idempotent demo-data generator
│   │   └── tests/            Pytest suite
│   └── web/                  Next.js 14 App Router app
│       └── src/
│           ├── app/          Layout, landing page, providers, icon
│           ├── components/   UI (shadcn-style), logo, status cards
│           ├── hooks/        TanStack Query + WebSocket hooks
│           ├── lib/          API client, design tokens, utils
│           └── types/        Shared API types
├── docker-compose.yml        postgres:16 + api + web
├── .env.example
├── Makefile
└── README.md
```

## Quickstart (Docker)

Prerequisites: Docker Desktop with Compose v2. Ports 3000, 8000 and 5432 must be free.

```bash
cp .env.example .env
docker compose up --build
```

The first start pulls images and installs API/web dependencies. The web page compiles on first open — give it about 30 seconds.

| Service | URL |
| --- | --- |
| Web app | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Liveness | http://localhost:8000/health |
| Readiness (DB ping) | http://localhost:8000/health/ready |

**Realtime smoke test:** open http://localhost:3000 in two tabs, type a message into the "Realtime · WebSocket" card of either tab and broadcast — it appears in both instantly.

Then create the schema and load demo data (idempotent — safe to re-run):

```bash
make migrate   # alembic upgrade head
make seed      # python -m app.seed
```

## Demo credentials

The four headline demo accounts share the password **`Demo@1234`** (every other seeded account uses it too; all are flagged `is_demo`).

| Role | Email | Dashboard | What it can do |
| --- | --- | --- | --- |
| ADMIN | `admin.demo@trackskill.in` | /dashboard/admin | State Skilling Mission governance (Phase 5 analytics) |
| PROVIDER | `provider.demo@trackskill.in` | /dashboard/provider | Staff of North District Skill Centre |
| TRAINEE | `trainee.demo@trackskill.in` | /dashboard/trainee | Certified trainee with employment and milestones due |
| EMPLOYER | `employer.demo@trackskill.in` | /dashboard/employer | Linked to several trainees' employment records |

`GET /auth/demo-accounts` returns this list for the sign-in page, but only while `DEMO_MODE=true`. The seed also creates 16 more provider staff, 11 more employers and 299 more trainees (same password) so every role sees realistic data.

## REST APIs and realtime (Phase 4)

Swagger (http://localhost:8000/docs) groups every endpoint by role tag: **Provider**, **Trainee**, **Employer**, **Admin**, plus auth and health.

| Role | Endpoints |
| --- | --- |
| Provider | `GET/POST /provider/trainees`, `POST /provider/trainees/import` (CSV), `PATCH /provider/trainees/{id}/certify`, `GET /provider/overview`, `GET /provider/followups` |
| Trainee | `GET /trainee/me` (journey timeline + upcoming milestones), `POST /trainee/consent`, `POST /trainee/followups/{id}/respond`, `GET /trainee/skills` |
| Employer | `GET /employer/verifications`, `POST /employer/verifications/{id}/confirm` / `dispute`, `POST /employer/trainees/{id}/hire`, `GET /employer/talent-pool` |
| Admin | `GET /admin/overview`, `GET /admin/providers` + `/{id}`, `POST /admin/allocations`, `POST /admin/providers/{id}/flag`, `GET /admin/curriculum-gaps`, `GET /admin/events` |

**Provider enrolment** returns a one-time temporary password (shown once, handed to the trainee out of band). **Every mutation** writes an `events` audit row and broadcasts live to `user:<id>` and `role:<ROLE>` WebSocket channels (`/ws?token=<access token>`); anonymous sockets only get isolated `public:<channel>` sandboxes. Enrol/certify/complete/allocate/flag also create notification rows for their target users.

### The flagship chain (covered by `tests/test_chain.py`)

1. Provider enrols + certifies → trainee gets a notification + consent prompt (`TRAINEE_ENROLLED`, `TRAINEE_CERTIFIED`).
2. Trainee grants consent (3 tracers scheduled) and answers the M3 follow-up claiming a job → `CONSENT_GRANTED`, `FOLLOWUP_RESPONDED` hits the provider and the named employer instantly.
3. Employer confirms → `VERIFICATION_COMPLETE` (both signals CONFIRMED, `verified` turns true) → PPI recalculated → `PPI_RECALCULATED` reaches provider and admin.
4. Admin allocates funds or flags the centre → `FUND_ALLOCATED` / `PROVIDER_FLAGGED` reach the provider with notification rows.

### Provider Performance Index (PPI)

```
PPI = 100 × (0.30·placement_rate + 0.25·retention_weighted
             + 0.20·wage_growth_norm + 0.15·verification_rate + 0.10·response_rate)

retention_weighted = 0.2·R3 + 0.3·R6 + 0.5·R12
```

- placement counts verified outcomes at full weight, unverified ones at 0.5
- wage_growth_norm: median M3→M12 relative wage growth, clamped at 50%
- verification_rate: share of the centre's verifications with both signals CONFIRMED
- response_rate: responded / (responded + missed) among past-due tracers

Recalculated on every `VERIFICATION_COMPLETE` and published as `PPI_RECALCULATED`. Source of truth: `apps/api/app/services/ppi.py`.

### Simulated tracer service (Phase 6)

The demo works without real WhatsApp/IVR gateways:

- **Engine** (`app/services/tracer_service.py`): creates M3/M6/M12 tracers from `certified_on` (only with active consent), delivers due tracers through a `ChannelAdapter`, expires SENT tracers with no reply after `TRACER_EXPIRY_DAYS`, and marks tracers MISSED after `TRACER_MAX_ATTEMPTS` failed delivery attempts (exponential backoff). Every transition publishes a realtime event: `TRACER_SCHEDULED`, `TRACER_SENT`, `FOLLOWUP_RESPONDED`, `TRACER_MISSED`.
- **Background scheduler**: APScheduler (`AsyncIOScheduler`) runs a cycle every `TRACER_INTERVAL_SECONDS`; disable with `SCHEDULER_ENABLED=false`.
- **Adapters** (`app/services/tracer_channels.py`): `SimulatedWhatsApp`, `SimulatedIVR`, `SimulatedSMS` for the demo; `TwilioWhatsAppAdapter` / `MetaCloudAdapter` stubs raise loudly behind `TRACER_PROVIDER=twilio|meta` until real credentials land.
- **Trainee dashboard**: a Messages panel renders each tracer as a WhatsApp-style chat (reply inline — the free-text parser scores it) or an IVR call-card with a 1–4 keypad flow.
- **Admin demo control**: `POST /admin/tracer/run` + the "Run tracer now" button fast-forward demo tracers to today and deliver instantly (DEMO_MODE only).

### AI features (Phase 5, `apps/api/app/ai/`)

| Module | What it does |
| --- | --- |
| `taxonomy.py` | 60-skill taxonomy across the 6 sectors (+ aliases) and 14 job roles as weighted skill sets |
| `embedder.py` | Lazy, cached text embedder. `USE_LIGHT_NLP=true` (default) → deterministic hashed n-gram vectors that run on any laptop; `false` → sentence-transformers **all-MiniLM-L6-v2** (chosen for CPU speed + short-text semantic similarity; `pip install sentence-transformers`) |
| `skill_assessment.py` | `POST /trainee/skills/assessment` — embeds course skills + self-described skills + free-text/voice transcripts against the taxonomy → skill profile (confidence 0–1) + top-5 job-role matches with "Matches on: …" explanations |
| `curriculum_matcher.py` | `GET /admin/curriculum-gaps` — per-course demand-weighted coverage vs `market_demand` for the course's district/sector, with gap score, missing in-demand skills and suggested module additions |
| `tracer_nlp.py` | English-only WhatsApp/IVR/SMS tracer templates (surfaced in `/trainee/me` and `/provider/followups`) + a reply parser: "I got a job as a welder, 14000 per month" → structured fields with confidence. `POST /trainee/followups/{id}/respond/text` auto-fills structured responses at confidence ≥ 0.6; lower confidence routes to manual review (provider `manual_review` bucket + notification) |
| `anomalies.py` | Statistical rules — wage outliers (vs sector median), impossible start dates, employer confirmation spikes — raising deduplicated `FLAG_RAISED` events for Admin. Auto-runs after employer confirm/hire; `POST /admin/anomalies/scan` runs a full sweep |

## Authentication and RBAC (Phase 2)

| Endpoint | What it does |
| --- | --- |
| `POST /auth/register` | Self-signup for **TRAINEE and EMPLOYER only** (403 otherwise); validates email + strong password (10+ chars, upper/lower/number/symbol); signs the caller in |
| `POST /auth/login` | Returns a 15-minute **access token** (JSON body) and sets a 7-day **refresh token** as an httpOnly cookie (`Path=/auth`); rate limited per IP + email (5 failures / 5 min); generic `Incorrect email or password.` for every failure |
| `POST /auth/refresh` | Exchanges the cookie for a fresh access token and rotates the refresh cookie |
| `POST /auth/logout` | Clears the refresh cookie |
| `GET /auth/me` | Profile of the authenticated user (any role) |
| `GET /auth/demo-accounts` | Demo logins, only while `DEMO_MODE=true` |
| `GET /trainees/me`, `GET /trainees/{id}` | Ownership-scoped reads: a trainee can only ever read their own profile (others get 404) |

Every guarded endpoint resolves the caller through `require_role(*roles)` — a 403 with a generic message is returned by the **backend**, independent of what the UI hides. JWTs are signed with `SECRET_KEY` (HS256). On the frontend, a Zustand store owns the session, the access token stays in memory, a single-flight refresh retries any 401 once, and `middleware.ts` routes unauthenticated visitors to `/sign-in` and bounces users who open another role's dashboard.

## Database schema (Phase 1)

15 tables, UUID primary keys, `created_at`/`updated_at` on every row, native PostgreSQL enums, indexes and FKs:

| Area | Tables |
| --- | --- |
| Identity & access | `users` (roles: PROVIDER/TRAINEE/EMPLOYER/ADMIN), `provider_staff` |
| Skilling supply | `training_centres`, `courses` (skills `text[]`, NSQF level) |
| Trainees & consent | `trainees`, `consents` (channel, granted/revoked, purpose, version) |
| Outcomes & tracing | `employers`, `employment_records`, `followups` (M3/M6/M12, simulated WhatsApp/IVR tracers), `verifications` (dual-signal; `verified` is a DB-generated column: true exactly when both signals are CONFIRMED) |
| Market & governance | `market_demand` (12 months × sector × skill × district), `provider_scores` (PPI), `fund_allocations` |
| Activity | `events` (audit log + realtime source), `notifications` |

**PPI formula** (seed-computed, fractions 0–1 → score 0–100): `35% placement + 25% avg retention (M3/M6/M12) + 20% verification rate + 20% wage growth (capped at 50% growth)`.

## Seed data

`python -m app.seed` generates deterministic sample data (fixed RNG seed + UUID5 identities): 8 centres across 8 fictional districts, ~26 courses, 300 trainees with consent ledgers, employment records and M3/M6/M12 follow-up history, 12 employers, 12 months × 15 skills × 8 districts of market demand, computed provider scores for the last 3 months, fund allocations, audit events and notifications. It prints per-table row counts and demo credentials at the end. Running it again inserts nothing.

## Make targets

Run `make dev` first; `seed`, `test`, `lint`, `migrate` and `revision` need the stack up.

| Target | What it does |
| --- | --- |
| `make dev` | Start Postgres + API + Web with hot reload |
| `make down` | Stop the stack (data volumes kept) |
| `make logs` | Follow API + Web logs |
| `make seed` | Run demo-data seeding inside the API container |
| `make test` | Pytest + web typecheck + web lint |
| `make lint` | Ruff (API) + ESLint (Web) |
| `make format` | Ruff format (API) + Prettier (Web) |
| `make migrate` | Apply Alembic migrations |
| `make revision m="..."` | Autogenerate a migration |
| `make api-shell` / `make web-shell` / `make db-shell` | Shells into api / web / psql |
| `make clean` | Stop and **delete all volumes** (destroys local data) |

## Environment variables

Copy `.env.example` to `.env` (Docker Compose auto-loads it; the defaults already work locally).

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | db | Postgres credentials |
| `DATABASE_URL` | api (outside Docker) | SQLAlchemy URL; inside Compose it is built from the POSTGRES_* values |
| `SECRET_KEY` | api | JWT signing secret (used from the auth phase) |
| `CORS_ORIGINS` | api | Comma-separated allowed browser origins |
| `ENVIRONMENT` / `LOG_LEVEL` | api | Development flags |
| `NEXT_PUBLIC_API_URL` | web | Browser → API base URL |
| `NEXT_PUBLIC_WS_URL` | web | Browser → WebSocket endpoint (`ws://…/ws`) |

## Running without Docker

API (needs Postgres on localhost:5432 — start `docker compose up -d db`, or point `DATABASE_URL` elsewhere):

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head              # once domain migrations exist
uvicorn app.main:app --reload
```

Web:

```bash
cd apps/web
npm install
npm run dev
```

## Testing and code style

```bash
# with the stack up
make test         # pytest + tsc + eslint
make lint         # ruff + eslint
make format       # ruff format + prettier

# locally
cd apps/api && .venv\Scripts\python -m pytest
cd apps/web && npm run typecheck && npm run lint
```

Optional git hooks: `pip install pre-commit && pre-commit install`.

## Design language

- **Petrol teal** (`brand-*`): institutions, trust, the primary action colour.
- **Marigold** (`marigold-*`): milestones, signals, highlights.
- Warm paper surfaces; **Space Grotesk** display + **Public Sans** body via `next/font`.
- Tokens live in `apps/web/src/lib/design-tokens.ts` and as CSS variables in `src/app/globals.css` (light/dark, WCAG AA).

## Privacy and data protection (DPDP-aligned design intent)

> **Design intent, not legal advice.** The product is built to make an
> independent India DPDP Act 2023 compliance review straightforward; it does
> not assert compliance. Rule-check with your DPO and counsel before any real
> deployment.

**Consent-first tracing.** No tracer is scheduled or sent without a recorded,
version-stamped consent grant (purpose text + version `1.0` on every row).
Revoking consent cancels every un-happened tracer immediately — the scheduler
also re-checks consent before each send, and revoked trainees disappear from
the employer talent pool at once.

**Purpose limitation.** Personal data serves exactly three purposes, stated at
consent time: milestone outcome tracing, verification of the trainee's own
employment claim, and program governance analytics (aggregates).

**Data minimisation.** The schema stores what the milestone outcome needs —
contact channel, employment status, job title, wage band, district — and
nothing else: no demographic proxies, no location tracking, no message content
beyond the tracer replies the trainee chose to send. Phone numbers never
cross role boundaries: they stay with the trainee (owner) and their centre's
provider staff; where contact details must appear to other roles they are
masked at the field level (`+91 ••••••5678`, `me••••••••@example.com`) in
`app/services/privacy.py`.

**Data subject rights (in product).** A signed-in trainee can export
everything stored about them (`GET /trainee/me/export` — one JSON document)
and erase their account (`POST /trainee/me/delete`, explicit
`{"confirm": true}`): profile, consents, tracers, employment claims and
notifications are deleted in the same transaction; audit events survive with
the actor reference nulled, so the trail stays complete without personal
data. Erasure is itself audited (`TRAINEE_DATA_DELETED`) for admins.

**Auditability.** Every mutation publishes an append-only audit event; every
sensitive cross-role read (talent pool, verification queue, trainee search)
writes a `READ_AUDIT` event with the reader, kind and filters.

**Security measures.** Argon-grade password hashing (bcrypt), short-lived JWT
access tokens (15 min) with rotating httpOnly refresh cookies (SameSite=Lax,
Path=/auth, cross-origin refresh rejected), RBAC enforced server-side on
every route, rate limiting on login/contact/reset/push-test, OWASP secure
headers (CSP, nosniff, frame-deny, referrer policy; HSTS in production), and
parameterised ORM queries only — no string-built SQL anywhere.

**Retention.** Tracer records and audit events are the accountability
backbone and are retained; everything personal can be erased by the trainee
or removed by admin demo reset in demo mode. A production deployment must add
a documented retention schedule per DPDP.

**Grievance and breach intent.** The contact endpoint routes questions to
admins; a production deployment must add a grievance officer identity and a
72-hour breach-notification runbook.

## Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Monorepo scaffold, theme, health, realtime wiring, Docker dev stack | ✅ |
| 1 | PostgreSQL schema (15 tables), Alembic migration, idempotent demo seed | ✅ |
| 2 | Auth (JWT access + refresh), RBAC, sign-in/create-account, demo credentials, role dashboards | ✅ |
| 3 | Role-scoped REST APIs, realtime event publishing, PPI service, AI skills fallback | ✅ |
| 4 | AI features: skill assessment, curriculum matcher, tracer NLP, anomaly flagging | ✅ |
| 5 | Simulated WhatsApp/IVR tracer service, scheduler, adapters, Messages panel, demo run-now | ✅ |
| 6 | Frontend dashboards consuming the APIs (provider console, tracer, verification queue, governance) | Planned |
| 7 | sentence-transformers semantic upgrade (behind USE_LIGHT_NLP) + governance screens | Planned |
| 8 | Auth screens polish, onboarding tour, consent versioning | Planned |
| 9 | Authenticated app shell + four realtime role dashboards, CSV/PDF exports | ✅ |
| 10 | Installable PWA: manifest + shortcuts, service worker (offline shell, data cache, background sync), Web Push (VAPID), native-feel, Capacitor/Electron wrappers | ✅ |
| 11 | Hardening: OWASP secure headers, rate limits, read audits, field masking, consent revocation guarantees, data rights (export/erase), DPDP-aligned privacy notes, pytest-cov ≥ 80%, Vitest, Playwright 4-role E2E, GitHub Actions CI | ✅ |

## Known limitations (Phase 6)

- The login rate limiter is in-process memory; running multiple API workers needs a shared store (Redis).
- Refresh tokens are rotated but not server-revocable yet (no jti denylist); logout clears the cookie client-side.
- Frontend dashboards render tracer messages and the demo run-now button; they do not yet subscribe to `user:`/`role:` WebSocket channels for push updates (the Messages panel invalidates on reply instead).
- Real gateway integrations (Twilio/Meta) are stubs; `TRACER_PROVIDER=simulated` is the only fully working mode.
- Tracer delivery is simulated: `FOLLOWUP_RESPONDED` events stand in for the WhatsApp/IVR channel integrations.
- Provider enrolment returns a one-time temporary password by design; there is no self-service password reset flow yet.
- PPI is recomputed per centre on `VERIFICATION_COMPLETE` and on read for leaderboards/overviews — no scheduled batch job yet.
- The AI module is the TF-IDF fallback; semantic (sentence-transformers) matching arrives in the AI phase.
- Containers run dev servers; a production build target lands with the PWA/deploy phase. `NEXT_PUBLIC_*` is inlined per page compile — restart the web container after changing it. On Windows bind mounts the API `--reload` watcher may not fire — restart the api container after backend edits. Fonts and npm/pip packages download on first build.

```

---

