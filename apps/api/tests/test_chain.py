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
