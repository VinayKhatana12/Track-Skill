"""Public contact endpoint tests (Phase 7)."""

import uuid

from sqlalchemy import func, select

from app.models import ContactMessage, Event


def test_contact_submit_stores_message_and_publishes_event(client, db_session) -> None:
    before = db_session.execute(
        select(func.count()).select_from(ContactMessage)
    ).scalar_one()
    payload = {
        "name": "Meera Iyer",
        "email": "meera.sample@example.com",
        "organisation": "Sample District Skilling Mission",
        "role": "ADMIN",
        "message": "We would like to pilot TrackSkill AI across three districts.",
    }
    response = client.post("/contact", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "received"
    assert body["id"]

    after = db_session.execute(
        select(func.count()).select_from(ContactMessage)
    ).scalar_one()
    assert after == before + 1

    stored = db_session.get(ContactMessage, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.email == "meera.sample@example.com"
    assert stored.role == "ADMIN"
    assert stored.organisation == "Sample District Skilling Mission"

    event = db_session.execute(
        select(Event).where(Event.type == "CONTACT_RECEIVED").order_by(Event.created_at.desc())
    ).scalars().first()
    assert event is not None
    assert event.payload["contact_id"] == body["id"]


def test_contact_validation_rejects_bad_payloads(client) -> None:
    assert client.post("/contact", json={"name": "X"}).status_code == 422
    bad = {
        "name": "Meera Iyer",
        "email": "not-an-email",
        "role": "ADMIN",
        "message": "A long enough message for the validator.",
    }
    assert client.post("/contact", json=bad).status_code == 422
    bad["email"] = "meera.sample@example.com"
    bad["role"] = "MAYOR"
    assert client.post("/contact", json=bad).status_code == 422
    bad["role"] = "OTHER"
    bad["message"] = "short"
    assert client.post("/contact", json=bad).status_code == 422


def test_contact_multiple_submissions_persist(client, db_session) -> None:
    before = db_session.execute(
        select(func.count()).select_from(ContactMessage)
    ).scalar_one()
    for index in range(3):
        response = client.post(
            "/contact",
            json={
                "name": f"Sample Person {index}",
                "email": f"person{index}.sample@example.com",
                "role": "OTHER",
                "message": f"Sample enquiry number {index} with enough characters.",
            },
        )
        assert response.status_code == 201
    after = db_session.execute(
        select(func.count()).select_from(ContactMessage)
    ).scalar_one()
    assert after == before + 3
