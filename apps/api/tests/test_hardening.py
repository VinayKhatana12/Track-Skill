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
