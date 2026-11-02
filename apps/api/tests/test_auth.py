"""Authentication and RBAC tests.

Requires a migrated + seeded database behind DATABASE_URL; all writes are
rolled back per test.
"""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models import Trainee, User

DEMO_PASSWORD = "Demo@1234"
DEMO_EMAILS = {
    "ADMIN": "admin.demo@trackskill.in",
    "PROVIDER": "provider.demo@trackskill.in",
    "TRAINEE": "trainee.demo@trackskill.in",
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


def test_all_four_demo_accounts_can_log_in(client: TestClient) -> None:
    for role, email in DEMO_EMAILS.items():
        body = _login(client, email)
        assert body["user"]["role"] == role
        assert body["user"]["email"] == email
        assert body["user"]["is_demo"] is True
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert client.cookies.get("refresh_token")  # session cookie stored


def test_login_sets_httponly_refresh_cookie(client: TestClient) -> None:
    response = client.post(
        "/auth/login", json={"email": DEMO_EMAILS["ADMIN"], "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"].lower()
    assert "refresh_token=" in set_cookie
    assert "httponly" in set_cookie
    assert "path=/auth" in set_cookie
    assert "max-age=604800" in set_cookie  # 7 days
    assert "samesite=lax" in set_cookie


def test_login_failure_is_generic(client: TestClient) -> None:
    wrong_password = client.post(
        "/auth/login", json={"email": DEMO_EMAILS["ADMIN"], "password": "definitely-wrong-1"}
    )
    unknown_email = client.post(
        "/auth/login", json={"email": "ghost@trackskill.in", "password": "whatever-here-1"}
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == "Incorrect email or password."
    assert unknown_email.json()["detail"] == "Incorrect email or password."


def test_expired_access_token_refreshes(client: TestClient) -> None:
    body = _login(client, DEMO_EMAILS["TRAINEE"])
    user_id = uuid.UUID(body["user"]["id"])

    expired = create_access_token(user_id, role="TRAINEE", expires_delta=timedelta(seconds=-30))
    denied = client.get("/auth/me", headers=_auth(expired))
    assert denied.status_code == 401

    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    new_token = refreshed.json()["access_token"]
    assert new_token != expired

    me = client.get("/auth/me", headers=_auth(new_token))
    assert me.status_code == 200
    assert me.json()["email"] == DEMO_EMAILS["TRAINEE"]


def test_refresh_without_cookie_is_rejected(client: TestClient) -> None:
    bare = TestClient(client.app)  # fresh cookie jar
    response = bare.post("/auth/refresh")
    assert response.status_code == 401


def test_every_role_is_blocked_from_other_roles_endpoints(client: TestClient) -> None:
    tokens = {role: _login(client, email)["access_token"] for role, email in DEMO_EMAILS.items()}

    # /auth/admin-area is ADMIN-only.
    assert client.get("/auth/admin-area", headers=_auth(tokens["ADMIN"])).status_code == 200
    for role in ("PROVIDER", "TRAINEE", "EMPLOYER"):
        response = client.get("/auth/admin-area", headers=_auth(tokens[role]))
        assert response.status_code == 403, role
        assert response.json()["detail"] == "You do not have access to this resource."

    # /trainees/me is TRAINEE-only.
    assert client.get("/trainees/me", headers=_auth(tokens["TRAINEE"])).status_code == 200
    for role in ("ADMIN", "PROVIDER", "EMPLOYER"):
        assert client.get("/trainees/me", headers=_auth(tokens[role])).status_code == 403, role

    # /auth/me accepts every authenticated role, and reports the caller.
    for role, token in tokens.items():
        response = client.get("/auth/me", headers=_auth(token))
        assert response.status_code == 200
        assert response.json()["role"] == role

    # Unauthenticated calls are 401, not 403.
    assert client.get("/auth/admin-area").status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_trainee_cannot_read_another_trainees_data(
    client: TestClient, db_session
) -> None:
    trainee_token = _login(client, DEMO_EMAILS["TRAINEE"])["access_token"]

    own = client.get("/trainees/me", headers=_auth(trainee_token))
    assert own.status_code == 200
    own_id = own.json()["id"]

    other_id = db_session.execute(
        select(Trainee.id)
        .join(User, Trainee.user_id == User.id)
        .where(User.email != DEMO_EMAILS["TRAINEE"])
        .limit(1)
    ).scalar_one()
    assert other_id != uuid.UUID(own_id)

    other = client.get(f"/trainees/{other_id}", headers=_auth(trainee_token))
    assert other.status_code == 404
    assert other.json()["detail"] == "Not found."

    own_by_id = client.get(f"/trainees/{own_id}", headers=_auth(trainee_token))
    assert own_by_id.status_code == 200


def test_register_flow(client: TestClient, db_session) -> None:
    payload = {
        "name": "Self Signup",
        "email": "self.trainee@trackskill.in",
        "password": "Str0ng!Passphrase",
        "role": "TRAINEE",
        "phone": "+91 9000000061",
        "district": "North District",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["role"] == "TRAINEE"
    assert body["user"]["is_demo"] is False

    me = client.get("/auth/me", headers=_auth(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "self.trainee@trackskill.in"

    # A trainee profile row is created so consent + dashboards work at once.
    from app.models import Trainee

    trainee_row = db_session.execute(
        select(Trainee).where(Trainee.user_id == uuid.UUID(body["user"]["id"]))
    ).scalar_one()
    assert trainee_row.district == "North District"
    assert trainee_row.status.value == "ENROLLED"
    assert trainee_row.centre_id is None  # no centre code supplied

    duplicate = client.post("/auth/register", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "An account with this email already exists."

    weak = client.post(
        "/auth/register",
        json={**payload, "email": "weak@trackskill.in", "password": "alllowercase1!"},
    )
    assert weak.status_code == 422

    provider_attempt = client.post(
        "/auth/register",
        json={**payload, "email": "sneaky@trackskill.in", "role": "PROVIDER"},
    )
    assert provider_attempt.status_code == 403

    admin_attempt = client.post(
        "/auth/register",
        json={**payload, "email": "sneaky-admin@trackskill.in", "role": "ADMIN"},
    )
    assert admin_attempt.status_code == 403

    employer_signup = client.post(
        "/auth/register",
        json={
            "name": "Self Employer",
            "email": "self.employer@trackskill.in",
            "password": "Str0ng!Passphrase",
            "role": "EMPLOYER",
            "company_name": "Sample Employer Co.",
        },
    )
    assert employer_signup.status_code == 201
    assert employer_signup.json()["user"]["role"] == "EMPLOYER"


def test_register_trainee_with_centre_code(client: TestClient, db_session) -> None:
    from app.models import TrainingCentre

    centre = db_session.execute(select(TrainingCentre).limit(1)).scalar_one()
    response = client.post(
        "/auth/register",
        json={
            "name": "Coded Trainee",
            "email": "coded.trainee@trackskill.in",
            "password": "Str0ng!Passphrase",
            "role": "TRAINEE",
            "phone": "+91 9000000071",
            "district": centre.district,
            "centre_code": centre.code,
        },
    )
    assert response.status_code == 201, response.text
    trainee = db_session.execute(
        select(Trainee).where(Trainee.user_id == uuid.UUID(response.json()["user"]["id"]))
    ).scalar_one()
    assert trainee.centre_id == centre.id

    # Unknown centre code -> 400 with a clear message.
    bad = client.post(
        "/auth/register",
        json={
            "name": "Bad Code Trainee",
            "email": "bad.code@trackskill.in",
            "password": "Str0ng!Passphrase",
            "role": "TRAINEE",
            "phone": "+91 9000000072",
            "district": "North District",
            "centre_code": "TC-99",
        },
    )
    assert bad.status_code == 400
    assert "centre code" in bad.json()["detail"].lower()


def test_forgot_and_reset_password_flow(client: TestClient, db_session) -> None:

    login_before = _login(client, DEMO_EMAILS["TRAINEE"])
    assert login_before["access_token"]

    forgot = client.post(
        "/auth/forgot-password", json={"email": DEMO_EMAILS["TRAINEE"]}
    )
    assert forgot.status_code == 200
    assert forgot.json()["status"] == "ok"
    reset_link = forgot.json().get("reset_link")
    assert reset_link and reset_link.startswith("/reset-password?token=")
    token = reset_link.split("token=")[1]

    new_password = "N3w!Passphrase"
    reset = client.post(
        "/auth/reset-password", json={"token": token, "new_password": new_password}
    )
    assert reset.status_code == 200, reset.text

    # Old password no longer works; new one does.
    old_login = client.post(
        "/auth/login", json={"email": DEMO_EMAILS["TRAINEE"], "password": DEMO_PASSWORD}
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/auth/login", json={"email": DEMO_EMAILS["TRAINEE"], "password": new_password}
    )
    assert new_login.status_code == 200

    # Invalid tokens are rejected.
    bad_reset = client.post(
        "/auth/reset-password",
        json={"token": "garbage-token", "new_password": new_password},
    )
    assert bad_reset.status_code == 400


def test_forgot_password_generic_for_unknown_email(client: TestClient) -> None:
    response = client.post(
        "/auth/forgot-password", json={"email": "nobody.known@trackskill.in"}
    )
    assert response.status_code == 200
    assert "reset_link" not in response.json()  # no link for unknown emails


def test_login_rate_limit(client: TestClient) -> None:
    email = "rate.limit@trackskill.in"
    for _ in range(5):
        attempt = client.post(
            "/auth/login", json={"email": email, "password": "wrong-password-1"}
        )
        assert attempt.status_code == 401
    throttled = client.post(
        "/auth/login", json={"email": email, "password": "wrong-password-1"}
    )
    assert throttled.status_code == 429
    assert throttled.json()["detail"] == "Too many attempts. Please try again later."

    # A different email (separate limiter key) is unaffected.
    seeded = client.post(
        "/auth/login", json={"email": DEMO_EMAILS["EMPLOYER"], "password": DEMO_PASSWORD}
    )
    assert seeded.status_code == 200


def test_logout_clears_refresh_cookie(client: TestClient) -> None:
    _login(client, DEMO_EMAILS["PROVIDER"])
    assert client.cookies.get("refresh_token")

    response = client.post("/auth/logout")
    assert response.status_code == 200
    assert client.cookies.get("refresh_token") is None


def test_demo_accounts_endpoint_gated_by_demo_mode(client: TestClient, monkeypatch) -> None:
    from app.core.config import get_settings

    response = client.get("/auth/demo-accounts")
    assert response.status_code == 200
    accounts = response.json()
    assert {account["role"] for account in accounts} == {
        "ADMIN",
        "PROVIDER",
        "TRAINEE",
        "EMPLOYER",
    }
    assert all(account["password"] == DEMO_PASSWORD for account in accounts)

    monkeypatch.setattr(get_settings(), "demo_mode", False)
    hidden = client.get("/auth/demo-accounts")
    assert hidden.status_code == 404
