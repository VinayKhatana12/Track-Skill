"""Web push endpoints and delivery plumbing (Phase 10)."""

import re
import uuid

from pywebpush import WebPushException
from sqlalchemy import func, select

from app.models import PushSubscription, User
from app.models.enums import UserRole
from app.services import push_service
from app.services.auth_service import hash_password

SUBSCRIPTION = {
    "endpoint": "https://push.example.com/send/abc123",
    "keys": {"p256dh": "BPersonKey123", "auth": "AuthKey123"},
    "user_agent": "pytest-browser",
}


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password="Demo@1234") -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_public_key_is_valid_p256(client) -> None:
    token = _login(client, "admin.demo@trackskill.in")
    response = client.get("/push/public-key", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    public_key = response.json()["public_key"]
    # base64url of the 65-byte uncompressed P-256 point is 87 characters.
    assert len(public_key) == 87
    assert re.fullmatch(r"[A-Za-z0-9_-]{87}", public_key)


def test_subscribe_replaces_and_unsubscribe_removes(client, db_session) -> None:
    token = _login(client, "trainee.demo@trackskill.in")

    first = client.post("/push/subscriptions", json=SUBSCRIPTION, headers=_auth_headers(token))
    assert first.status_code == 200, first.text
    rows = db_session.execute(
        select(func.count()).select_from(PushSubscription)
    ).scalars().all()
    assert rows == [1]

    # Same browser re-subscribes (e.g. after re-login): one row, updated owner.
    second = client.post("/push/subscriptions", json=SUBSCRIPTION, headers=_auth_headers(token))
    assert second.status_code == 200
    assert (
        db_session.execute(select(func.count()).select_from(PushSubscription)).scalar_one() == 1
    )

    removed = client.post(
        "/push/subscriptions/delete",
        json={"endpoint": SUBSCRIPTION["endpoint"]},
        headers=_auth_headers(token),
    )
    assert removed.status_code == 200
    assert (
        db_session.execute(select(func.count()).select_from(PushSubscription)).scalar_one() == 0
    )


def test_subscription_requires_keys(client) -> None:
    token = _login(client, "trainee.demo@trackskill.in")
    bad = {"endpoint": "https://push.example.com/x", "keys": {"p256dh": "only"}}
    response = client.post("/push/subscriptions", json=bad, headers=_auth_headers(token))
    assert response.status_code == 422


def test_push_endpoints_require_authentication(client) -> None:
    assert client.get("/push/public-key").status_code == 401
    assert client.post("/push/subscriptions", json=SUBSCRIPTION).status_code == 401
    assert client.post("/push/test").status_code == 401


def test_test_push_sends_and_reports(client, db_session, monkeypatch) -> None:
    token = _login(client, "admin.demo@trackskill.in")
    client.post("/push/subscriptions", json=SUBSCRIPTION, headers=_auth_headers(token))

    sent_payloads: list[dict] = []
    monkeypatch.setattr(
        push_service, "_send_one", lambda target, payload: sent_payloads.append(payload)
    )
    response = client.post("/push/test", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    assert response.json() == {"sent": 1, "failed": 0, "pruned": 0}
    assert sent_payloads[0]["title"] == "TrackSkill AI test notification"
    assert sent_payloads[0]["link"] == "/dashboard"


def test_gone_subscription_is_pruned(client, db_session, monkeypatch) -> None:
    token = _login(client, "admin.demo@trackskill.in")
    client.post("/push/subscriptions", json=SUBSCRIPTION, headers=_auth_headers(token))

    def raise_gone(target, payload):
        raise WebPushException("gone", response=type("R", (), {"status_code": 410})())

    monkeypatch.setattr(push_service, "_send_one", raise_gone)
    response = client.post("/push/test", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json() == {"sent": 0, "failed": 0, "pruned": 1}
    assert (
        db_session.execute(select(func.count()).select_from(PushSubscription)).scalar_one() == 0
    )


def test_publish_event_fans_out_push_for_notifications(client, db_session, monkeypatch) -> None:
    """Certifying a subscribed trainee queues one encrypted push for them."""
    dispatched: list[tuple[list, dict, list]] = []
    monkeypatch.setattr(
        push_service,
        "dispatch_push_async",
        lambda targets, payload, user_ids: dispatched.append((targets, payload, user_ids)),
    )

    provider_token = _login(client, "provider.demo@trackskill.in")
    courses = client.get("/provider/courses", headers=_auth_headers(provider_token)).json()

    enrol = client.post(
        "/provider/trainees",
        json={
            "name": "Push Chain Trainee",
            "email": f"push.{uuid.uuid4().hex[:8]}@trackskill.in",
            "phone": "+91 9000000199",
            "course_id": courses[0]["id"],
        },
        headers=_auth_headers(provider_token),
    )
    assert enrol.status_code == 201, enrol.text
    trainee_token = _login(
        client, enrol.json()["trainee"]["email"], enrol.json()["temporary_password"]
    )
    subscribed = client.post(
        "/push/subscriptions", json=SUBSCRIPTION, headers=_auth_headers(trainee_token)
    )
    assert subscribed.status_code == 200

    certify = client.patch(
        f"/provider/trainees/{enrol.json()['trainee']['id']}/certify",
        json={},
        headers=_auth_headers(provider_token),
    )
    assert certify.status_code == 200, certify.text

    assert len(dispatched) == 1
    targets, payload, user_ids = dispatched[0]
    assert len(targets) == 1
    assert targets[0][0] == SUBSCRIPTION["endpoint"]
    assert payload["event_type"] == "TRAINEE_CERTIFIED"
    assert payload["title"] == "Congratulations — you are certified!"
    assert payload["link"] == "/dashboard/trainee"
    assert len(user_ids) == 1


def test_snapshot_subscriptions_filters_by_user(db_session, monkeypatch) -> None:
    provider_user = db_session.execute(
        select(User).where(User.email == "provider.demo@trackskill.in")
    ).scalar_one()
    other = User(
        id=uuid.uuid4(),
        name="Push Only User",
        email=f"pushonly.{uuid.uuid4().hex[:8]}@trackskill.in",
        password_hash=hash_password("Demo@1234"),
        role=UserRole.TRAINEE,
        is_active=True,
    )
    db_session.add(other)
    db_session.flush()

    db_session.add(
        PushSubscription(
            id=uuid.uuid4(),
            user_id=other.id,
            endpoint="https://push.example.com/one",
            p256dh="K1",
            auth="A1",
        )
    )
    db_session.flush()

    targets = push_service.snapshot_subscriptions(db_session, [other.id])
    assert targets == [("https://push.example.com/one", "K1", "A1")]
    assert push_service.snapshot_subscriptions(db_session, [provider_user.id]) == []
    assert push_service.snapshot_subscriptions(db_session, []) == []
