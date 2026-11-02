"""Tracer engine tests (Phase 6): adapters, creation, delivery, retries,
expiry, demo fast-forward, and the trainee Messages endpoint.

The background scheduler is disabled in tests (conftest); the engine is
exercised by calling tracer_service functions directly.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import (
    Consent,
    Course,
    FollowUp,
    Notification,
    Trainee,
    TrainingCentre,
    User,
)
from app.models.enums import ConsentChannel, FollowUpMilestone, FollowUpState
from app.services import tracer_service
from app.services.tracer_channels import (
    MetaCloudAdapter,
    SimulatedIVR,
    SimulatedWhatsApp,
    TwilioWhatsAppAdapter,
    get_adapter,
)

DEMO_PASSWORD = "Demo@1234"


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


def _enrol_and_certify(client: TestClient, db_session, email: str, name: str) -> Trainee:
    provider_token = _login(client, "provider.demo@trackskill.in")["access_token"]
    centre_id = db_session.execute(
        select(TrainingCentre.id).where(TrainingCentre.district == "North District")
    ).scalar_one()
    course_id = db_session.execute(
        select(Course.id).where(Course.centre_id == centre_id).limit(1)
    ).scalar_one()
    enrol = client.post(
        "/provider/trainees",
        json={
            "name": name,
            "email": email,
            "phone": "+91 9000000041",
            "course_id": str(course_id),
        },
        headers=_auth(provider_token),
    )
    assert enrol.status_code == 201, enrol.text
    trainee_id = enrol.json()["trainee"]["id"]
    assert (
        client.patch(
            f"/provider/trainees/{trainee_id}/certify", json={}, headers=_auth(provider_token)
        ).status_code
        == 200
    )
    # Backdate so the M3 tracer is immediately due.
    trainee = db_session.get(Trainee, uuid.UUID(trainee_id))
    trainee.certified_on = date.today() - timedelta(days=95)
    trainee.enrolled_on = trainee.certified_on - timedelta(weeks=24)
    db_session.flush()
    return trainee


# ── Adapters ─────────────────────────────────────────────────────────────────


def test_simulated_adapters_deliver_without_error() -> None:
    import asyncio

    whatsapp = get_adapter("WHATSAPP")
    ivr = get_adapter("IVR")
    assert isinstance(whatsapp, SimulatedWhatsApp)
    assert isinstance(ivr, SimulatedIVR)
    asyncio.run(
        whatsapp.send(to_user_id=uuid.uuid4(), to_phone="+91 9000000000", message="hi")
    )
    asyncio.run(ivr.send(to_user_id=uuid.uuid4(), to_phone=None, message="press 1"))


def test_stub_adapters_raise_behind_env_flags(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tracer_provider", "twilio")
    assert isinstance(get_adapter("WHATSAPP"), TwilioWhatsAppAdapter)
    with pytest.raises(NotImplementedError):
        asyncio.run(
            TwilioWhatsAppAdapter().send(
                to_user_id=uuid.uuid4(), to_phone="+91 9000000000", message="hi"
            )
        )

    monkeypatch.setattr(get_settings(), "tracer_provider", "meta")
    assert isinstance(get_adapter("WHATSAPP"), MetaCloudAdapter)
    with pytest.raises(NotImplementedError):
        asyncio.run(
            MetaCloudAdapter().send(
                to_user_id=uuid.uuid4(), to_phone="+91 9000000000", message="hi"
            )
        )


def test_unknown_provider_and_channel_are_rejected(monkeypatch) -> None:
    from app.core.config import get_settings

    with pytest.raises(ValueError):
        get_adapter("PIGEON")
    monkeypatch.setattr(get_settings(), "tracer_provider", "smoke-signal")
    with pytest.raises(ValueError):
        get_adapter("WHATSAPP")


# ── Scheduler jobs ───────────────────────────────────────────────────────────


def test_cycle_creates_due_tracers_only_with_consent(
    client: TestClient, db_session
) -> None:
    trainee = _enrol_and_certify(
        client, db_session, "tracer.consent@trackskill.in", "Tracer Consent Trainee"
    )
    # Certified 95 days ago, no consent yet: a cycle must create nothing.
    summary = asyncio.run(tracer_service.run_tracer_cycle(db_session))
    assert summary["created"] == 0
    count = db_session.execute(
        select(func.count()).select_from(FollowUp).where(FollowUp.trainee_id == trainee.id)
    ).scalar_one()
    assert count == 0

    # Grant consent at service level (auth flows are covered in test_auth).
    db_session.add(
        Consent(
            id=uuid.uuid4(),
            trainee_id=trainee.id,
            channel="WHATSAPP",
            granted=True,
            granted_at=datetime.now(UTC),
            revoked_at=None,
            purpose_text="Outcome tracking follow-ups at 3, 6 and 12 months after certification. "
            "You can withdraw consent at any time.",
            version="1.0",
        )
    )
    db_session.flush()

    summary = asyncio.run(tracer_service.run_tracer_cycle(db_session))
    assert summary["created"] == 3
    # M3 is due (certified 95 days ago) and gets sent in the same cycle.
    assert any(item["milestone"] == "M3" for item in summary["sent"])

    sent_event = db_session.execute(
        select(FollowUp).where(
            FollowUp.trainee_id == trainee.id, FollowUp.state == FollowUpState.SENT
        )
    ).scalar_one()
    assert sent_event.attempts == 1
    assert sent_event.sent_at is not None

    # Notification row for the trainee (TRACER_SENT drafts one).
    notifications = db_session.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == trainee.user_id
        )
    ).scalar_one()
    assert notifications >= 1


def test_no_response_after_expiry_becomes_missed(client: TestClient, db_session) -> None:
    trainee = _enrol_and_certify(
        client, db_session, "tracer.expiry@trackskill.in", "Tracer Expiry Trainee"
    )
    followup = FollowUp(
        id=uuid.uuid4(),
        trainee_id=trainee.id,
        milestone=FollowUpMilestone.M3,
        due_on=date.today() - timedelta(days=30),
        channel="WHATSAPP",
        state=FollowUpState.SENT,
        sent_at=datetime.now(UTC) - timedelta(days=20),
        attempts=1,
    )
    db_session.add(followup)
    db_session.flush()

    missed = asyncio.run(tracer_service.expire_overdue_followups(db_session))
    assert any(item["followup_id"] == str(followup.id) for item in missed)
    assert db_session.get(FollowUp, followup.id).state == FollowUpState.MISSED


def test_delivery_failure_retries_then_misses(
    client: TestClient, db_session, monkeypatch
) -> None:
    trainee = _enrol_and_certify(
        client, db_session, "tracer.retry@trackskill.in", "Tracer Retry Trainee"
    )
    # Consent must be active — otherwise the consent-not-active branch fires
    # before the retry logic can.
    db_session.add(
        Consent(
            id=uuid.uuid4(),
            trainee_id=trainee.id,
            channel=ConsentChannel.WHATSAPP,
            granted=True,
            granted_at=datetime.now(UTC),
            revoked_at=None,
            purpose_text="Outcome tracking follow-ups at 3, 6 and 12 months after certification. "
            "You can withdraw consent at any time.",
            version="1.0",
        )
    )
    followup = FollowUp(
        id=uuid.uuid4(),
        trainee_id=trainee.id,
        milestone=FollowUpMilestone.M3,
        due_on=date.today(),
        channel=ConsentChannel.WHATSAPP,
        state=FollowUpState.SCHEDULED,
    )
    db_session.add(followup)
    db_session.flush()

    class FailingAdapter:
        channel = "WHATSAPP"

        async def send(self, *, to_user_id, to_phone, message) -> None:
            raise RuntimeError("gateway down")

    monkeypatch.setattr(tracer_service, "get_adapter", lambda channel: FailingAdapter())

    def rewind_backoff() -> None:
        """Simulate the backoff window having elapsed since the last attempt."""
        followup.updated_at = datetime.now(UTC) - timedelta(minutes=30)
        db_session.flush()

    # Attempt 1 fails: retries stay SCHEDULED with attempts=1.
    asyncio.run(tracer_service.send_due_followups(db_session))
    assert followup.state == FollowUpState.SCHEDULED
    assert followup.attempts == 1

    # Attempts 2 and 3 fail (backoff window rewound between cycles): the
    # tracer is MISSED after max attempts.
    rewind_backoff()
    asyncio.run(tracer_service.send_due_followups(db_session))
    assert followup.attempts == 2
    rewind_backoff()
    asyncio.run(tracer_service.send_due_followups(db_session))
    assert followup.attempts == 3
    assert followup.state == FollowUpState.MISSED

    missed_event = db_session.execute(
        select(FollowUp).where(FollowUp.id == followup.id)
    ).scalar_one()
    assert missed_event.state == FollowUpState.MISSED


# ── Demo fast-forward + endpoints ────────────────────────────────────────────


def test_run_tracer_now_delivers_to_demo_trainee(client: TestClient, db_session) -> None:
    """A fresh certified+consented trainee with a past-due tracer receives it
    the moment an admin runs the tracer cycle (regardless of prior runs)."""
    provider_token = _login(client, "provider.demo@trackskill.in")["access_token"]
    centre_id = db_session.execute(
        select(TrainingCentre.id).where(TrainingCentre.district == "North District")
    ).scalar_one()
    course_id = db_session.execute(
        select(Course.id).where(Course.centre_id == centre_id).limit(1)
    ).scalar_one()

    enrol = client.post(
        "/provider/trainees",
        json={
            "name": "Run Cycle Trainee",
            "email": "runcycle.trainee@trackskill.in",
            "phone": "+91 9000000051",
            "course_id": str(course_id),
        },
        headers=_auth(provider_token),
    )
    assert enrol.status_code == 201, enrol.text
    trainee_id = enrol.json()["trainee"]["id"]
    temp_password = enrol.json()["temporary_password"]

    assert (
        client.patch(
            f"/provider/trainees/{trainee_id}/certify", json={}, headers=_auth(provider_token)
        ).status_code
        == 200
    )

    # Consent + backdate so the M3 tracer is due now (service level).
    trainee = db_session.get(Trainee, uuid.UUID(trainee_id))
    trainee.certified_on = date.today() - timedelta(days=95)
    trainee.enrolled_on = trainee.certified_on - timedelta(weeks=24)
    db_session.add(
        Consent(
            id=uuid.uuid4(),
            trainee_id=trainee.id,
            channel="WHATSAPP",
            granted=True,
            granted_at=datetime.now(UTC),
            revoked_at=None,
            purpose_text="Outcome tracking follow-ups at 3, 6 and 12 months after certification. "
            "You can withdraw consent at any time.",
            version="1.0",
        )
    )
    db_session.flush()

    admin_token = _login(client, "admin.demo@trackskill.in")["access_token"]
    response = client.post("/admin/tracer/run", headers=_auth(admin_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sent_count"] >= 1, "demo run must deliver at least one tracer"
    sent_to_trainee = [item for item in body["sent"] if item["trainee_id"] == trainee_id]
    assert sent_to_trainee, "the fresh trainee must receive their due tracer"

    # The trainee sees the delivered chat instantly in their Messages panel.
    trainee_token = _login(client, "runcycle.trainee@trackskill.in", temp_password)[
        "access_token"
    ]
    messages = client.get("/trainee/messages", headers=_auth(trainee_token))
    assert messages.status_code == 200
    delivered = next(
        item
        for item in messages.json()
        if item["followup_id"] == sent_to_trainee[0]["followup_id"]
    )
    assert delivered["state"] == "SENT"
    assert delivered["sent_at"] is not None
    assert delivered["message"]


def test_run_tracer_gated_by_demo_mode_and_role(client: TestClient, monkeypatch) -> None:
    from app.core.config import get_settings

    provider_token = _login(client, "provider.demo@trackskill.in")["access_token"]
    assert (
        client.post("/admin/tracer/run", headers=_auth(provider_token)).status_code == 403
    )
    assert client.post("/admin/tracer/run").status_code == 401

    monkeypatch.setattr(get_settings(), "demo_mode", False)
    admin_token = _login(client, "admin.demo@trackskill.in")["access_token"]
    assert client.post("/admin/tracer/run", headers=_auth(admin_token)).status_code == 404


def test_messages_endpoint_kinds_and_shape(client: TestClient, db_session) -> None:
    trainee_token = _login(client, "trainee.demo@trackskill.in")["access_token"]
    items = client.get("/trainee/messages", headers=_auth(trainee_token)).json()
    assert items
    for item in items:
        assert {"followup_id", "milestone", "channel", "kind", "message", "state"} <= set(item)
        expected_kind = "call" if item["channel"] == "IVR" else "chat"
        assert item["kind"] == expected_kind
