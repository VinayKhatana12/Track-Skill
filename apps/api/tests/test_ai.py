"""AI module tests: taxonomy, embedder, skill assessment, curriculum gaps,
tracer NLP, anomaly rules, and the new endpoints.

All AI tests run in the default light-NLP mode (deterministic, no model
download); the heavy sentence-transformers backend is exercised only for
its error path.
"""

import asyncio
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ai import embedder as ai_embedder
from app.ai import skill_assessment, taxonomy, tracer_nlp
from app.ai.anomalies import (
    RULE_WAGE_OUTLIER,
    check_employer_confirmation_volume,
    check_employment_record,
)
from app.models import (
    Course,
    Employer,
    EmploymentRecord,
    Event,
    FollowUp,
    Trainee,
    TrainingCentre,
    User,
    Verification,
)
from app.models.enums import EmploymentStatus, FollowUpMilestone, VerificationSignal
from app.services.ppi import is_verified

DEMO_PASSWORD = "Demo@1234"


def _login(client: TestClient, email: str, password: str = DEMO_PASSWORD) -> dict:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _light_nlp_mode(monkeypatch):
    """Pin the deterministic light-NLP mode for the whole AI test module."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "use_light_nlp", True)
    ai_embedder.reset_embedder()
    yield
    ai_embedder.reset_embedder()


@pytest.fixture(autouse=True)
def _require_seeded_database(db_session):
    user_count = db_session.execute(select(func.count()).select_from(User)).scalar_one()
    if user_count == 0:
        pytest.skip("Database is not seeded; run alembic upgrade head and python -m app.seed.")


# ── Taxonomy ─────────────────────────────────────────────────────────────────


def test_taxonomy_has_60_skills_across_6_sectors() -> None:
    assert len(taxonomy.SKILLS) == 60
    sectors = {sector for _, sector, _ in taxonomy.SKILLS}
    assert sectors == set(taxonomy.SECTORS)
    assert len(sectors) == 6


def test_every_job_role_references_taxonomy_skills() -> None:
    known = {name for name, _, _ in taxonomy.SKILLS}
    for role in taxonomy.JOB_ROLES:
        assert set(role["skills"]) <= known, role["title"]
        assert 1.0 in role["skills"].values(), role["title"]


# ── Embedder ─────────────────────────────────────────────────────────────────


def test_embedder_is_lazy_and_cached() -> None:
    first = ai_embedder.get_embedder()
    second = ai_embedder.get_embedder()
    assert first is second  # cached singleton
    assert isinstance(first, ai_embedder.HashingEmbedder)  # light mode default


def test_light_embedder_is_deterministic_and_normalized() -> None:
    embedder = ai_embedder.get_embedder()
    vectors = embedder.encode(["Data Entry", "Data Entry", "Nursing Assistant"])
    assert vectors[0] == vectors[1]  # deterministic
    assert ai_embedder.cosine(vectors[0], vectors[1]) > 0.999
    related = ai_embedder.cosine(vectors[0], vectors[2])
    assert 0.0 <= related < 0.999  # different texts are less similar
    for vector in vectors:
        norm = sum(value * value for value in vector) ** 0.5
        assert norm == pytest.approx(1.0, abs=1e-3)


def test_heavy_backend_without_package_raises_clear_error(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "use_light_nlp", False)
    ai_embedder.reset_embedder()
    try:
        try:
            ai_embedder.get_embedder()
        except ai_embedder.EmbeddingBackendError as exc:
            assert "sentence-transformers" in str(exc)
        else:
            # The package IS installed in this environment — then the
            # backend must be the real one.
            assert ai_embedder.get_embedder().__class__.__name__ == "SentenceTransformerEmbedder"
    finally:
        ai_embedder.reset_embedder()


# ── Skill assessment ─────────────────────────────────────────────────────────


def test_skill_assessment_for_sample_trainee_returns_ranked_matches() -> None:
    result = skill_assessment.assess_skills(
        course_skills=["Typing", "Spreadsheets", "Data Entry"],
        self_reported_skills=["Data Entry", "Typing"],
        free_text="I can use spreadsheets and enter data quickly",
    )
    assert result["mode"] == "light-nlp"
    profile = result["profile"]
    assert profile, "sample trainee must produce a skill profile"
    data_entry = next(item for item in profile if item["skill"] == "Data Entry")
    assert data_entry["confidence"] >= 0.9  # exact self-report
    assert data_entry["sector"] == "Information Technology"

    matches = result["role_matches"]
    assert 1 <= len(matches) <= 5
    assert matches == sorted(matches, key=lambda item: -item["score"])
    top = matches[0]
    assert top["title"] == "Data Entry Operator"
    assert "Matches on:" in top["explanation"]
    assert "Data Entry" in top["explanation"]
    for match in matches:
        assert match["matched_skills"]


def test_skill_assessment_uses_free_text_evidence() -> None:
    result = skill_assessment.assess_skills(
        course_skills=[],
        self_reported_skills=[],
        free_text="I take care of patients and check their vitals every day",
    )
    profile_skills = {item["skill"] for item in result["profile"]}
    assert "Patient Care" in profile_skills  # verbatim mention
    patient_care = next(item for item in result["profile"] if item["skill"] == "Patient Care")
    assert patient_care["confidence"] >= 0.9


def test_skill_assessment_empty_evidence_is_safe() -> None:
    result = skill_assessment.assess_skills(course_skills=[], self_reported_skills=[])
    assert result["profile"] == []
    assert result["role_matches"] == []


def test_assessment_endpoint_for_demo_trainee(client: TestClient) -> None:
    token = _login(client, "trainee.demo@trackskill.in")["access_token"]
    response = client.post(
        "/trainee/skills/assessment",
        json={"self_reported_skills": ["Data Entry"], "free_text": None},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["profile"]
    assert {item["skill"] for item in body["profile"]} >= {"Data Entry"}
    assert 1 <= len(body["role_matches"]) <= 5

    wrong_method = client.get("/trainee/skills/assessment", headers=_auth(token))
    assert wrong_method.status_code == 405  # POST-only


# ── Curriculum-demand matcher ────────────────────────────────────────────────


def test_gap_report_covers_at_least_three_courses(client: TestClient) -> None:
    admin_token = _login(client, "admin.demo@trackskill.in")["access_token"]
    response = client.get("/admin/curriculum-gaps", headers=_auth(admin_token))
    assert response.status_code == 200, response.text
    report = response.json()
    assert len(report) >= 3, "gap report must return at least 3 courses"

    for course_report in report:
        assert {"gap_score", "missing_in_demand_skills", "suggested_modules"} <= set(course_report)
        assert 0.0 <= course_report["coverage"] <= 1.0
        assert course_report["gap_score"] == pytest.approx(
            1.0 - course_report["coverage"], abs=1e-6
        )
        for module in course_report["suggested_modules"]:
            assert module.startswith("Add a module on '")
    # Worst gap first.
    gaps = [course_report["gap_score"] for course_report in report]
    assert gaps == sorted(gaps, reverse=True)


def test_gap_report_service_layer(db_session) -> None:
    from app.ai.curriculum_matcher import course_gap_report

    report = course_gap_report(db_session, limit=50)
    assert len(report) >= 3
    # Courses teaching exactly an in-demand skill get partial/full coverage.
    data_entry_courses = [
        item
        for item in report
        if "Data Entry" in item["course_skills"] and item["sector"] == "Information Technology"
    ]
    assert data_entry_courses, "seed includes Data Entry courses in IT districts"
    for item in data_entry_courses:
        assert item["coverage"] > 0.0


# ── Tracer NLP ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected_status", "expected_title", "expected_wage"),
    [
        ("I got a job as a welder, 14000 per month", "EMPLOYED", "Welder", 14000),
        (
            "Started working as a solar panel installer last month, earning 21000 monthly",
            "EMPLOYED",
            "Solar Panel Installer",
            21000,
        ),
        (
            "I am self employed, stitching clothes from home, around 9000 per month",
            "SELF_EMPLOYED",
            None,
            9000,
        ),
        ("Still searching for a job", "UNEMPLOYED", None, None),
        (
            "joined HarbourCare Health Network as a nursing assistant",
            "EMPLOYED",
            "Nursing Assistant",
            None,
        ),
        ("Now studying advanced diploma", "FURTHER_STUDY", None, None),
        ("asdf lol", None, None, None),
        ("Got hired! 25000 per month", "EMPLOYED", None, 25000),
        ("Lost my job last week", "UNEMPLOYED", None, None),
    ],
)
def test_reply_parser_phrases(
    text: str, expected_status: str | None, expected_title: str | None, expected_wage: int | None
) -> None:
    parsed = tracer_nlp.parse_reply(text)
    assert parsed.employment_status == expected_status, (text, parsed.to_dict())
    if expected_title is not None:
        assert parsed.job_title == expected_title, text
    if expected_wage is not None:
        assert parsed.monthly_wage == expected_wage, text
    if expected_status is None:
        assert parsed.needs_review is True
        assert parsed.confidence < tracer_nlp.MANUAL_REVIEW_THRESHOLD


def test_parser_confidence_and_manual_review_flag() -> None:
    strong = tracer_nlp.parse_reply("I got a job as a welder, 14000 per month")
    assert strong.confidence >= tracer_nlp.MANUAL_REVIEW_THRESHOLD
    assert strong.needs_review is False

    weak = tracer_nlp.parse_reply("hello there")
    assert weak.needs_review is True


def test_tracer_templates_are_channel_specific_and_english() -> None:
    kwargs = {
        "trainee_name": "Priya Sharma",
        "course_title": "Nursing Assistant",
        "milestone": "M3",
        "centre_name": "North District Skill Centre",
    }
    whatsapp = tracer_nlp.build_followup_message(channel="WHATSAPP", **kwargs)
    ivr = tracer_nlp.build_followup_message(channel="IVR", **kwargs)
    sms = tracer_nlp.build_followup_message(channel="SMS", **kwargs)

    assert "Priya" in whatsapp and "3 months" in whatsapp
    assert "welder, 14000 per month" in whatsapp  # worked example for the parser
    assert "Press 1" in ivr and "Press 2" in ivr
    assert "Reply" in sms
    for message in (whatsapp, ivr, sms):
        assert message.isascii()  # English-only product rule


def test_followup_messages_surface_in_views(client: TestClient) -> None:
    trainee_token = _login(client, "trainee.demo@trackskill.in")["access_token"]
    me = client.get("/trainee/me", headers=_auth(trainee_token))
    assert me.status_code == 200
    upcoming = me.json()["upcoming"]
    assert upcoming and all(item["message"] for item in upcoming)

    provider_token = _login(client, "provider.demo@trackskill.in")["access_token"]
    followups = client.get("/provider/followups", headers=_auth(provider_token))
    assert followups.status_code == 200
    buckets = followups.json()
    assert {"overdue", "due_soon", "manual_review"} <= set(buckets)


# ── Reply parsing over the API ───────────────────────────────────────────────


def _enrol_and_certify(
    client: TestClient, db_session, email: str, name: str
) -> tuple[str, str]:
    """Enrol + certify a trainee; returns (trainee_id, temporary_password)."""
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
            "phone": "+91 9000000021",
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
    return trainee_id, enrol.json()["temporary_password"]


def test_respond_text_high_confidence_creates_verification(
    client: TestClient, db_session
) -> None:
    trainee_id, temp_password = _enrol_and_certify(
        client, db_session, "text.reply@trackskill.in", "Text Reply Trainee"
    )
    trainee_token = _login(client, "text.reply@trackskill.in", temp_password)["access_token"]

    consent = client.post(
        "/trainee/consent",
        json={"channel": "WHATSAPP", "granted": True},
        headers=_auth(trainee_token),
    )
    assert consent.status_code == 200, consent.text

    m3_id = db_session.execute(
        select(FollowUp.id).where(
            FollowUp.trainee_id == uuid.UUID(trainee_id),
            FollowUp.milestone == FollowUpMilestone.M3,
        )
    ).scalar_one()

    response = client.post(
        f"/trainee/followups/{m3_id}/respond/text",
        json={"message": "I got a job as a web developer, 24000 per month"},
        headers=_auth(trainee_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["needs_review"] is False
    assert body["parsed"]["employment"] == "EMPLOYED"
    assert body["confidence"] >= tracer_nlp.MANUAL_REVIEW_THRESHOLD

    verification = db_session.get(Verification, uuid.UUID(body["verification_id"]))
    assert verification.trainee_signal is VerificationSignal.CONFIRMED

    followup = db_session.get(FollowUp, uuid.UUID(body["followup_id"]))
    assert (
        followup.response_json["raw_text"] == "I got a job as a web developer, 24000 per month"
    )
    assert followup.response_json["parsed_from_text"]["confidence"] >= 0.6


def test_respond_text_low_confidence_routes_to_manual_review(
    client: TestClient, db_session
) -> None:
    trainee_id, temp_password = _enrol_and_certify(
        client, db_session, "garbled.reply@trackskill.in", "Garbled Reply Trainee"
    )
    trainee_token = _login(client, "garbled.reply@trackskill.in", temp_password)["access_token"]
    client.post(
        "/trainee/consent",
        json={"channel": "WHATSAPP", "granted": True},
        headers=_auth(trainee_token),
    )
    m3_id = db_session.execute(
        select(FollowUp.id).where(
            FollowUp.trainee_id == uuid.UUID(trainee_id),
            FollowUp.milestone == FollowUpMilestone.M3,
        )
    ).scalar_one()

    response = client.post(
        f"/trainee/followups/{m3_id}/respond/text",
        json={"message": "ok will tell later maybe"},
        headers=_auth(trainee_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["needs_review"] is True
    assert body["verification_id"] is None

    followup = db_session.get(FollowUp, uuid.UUID(body["followup_id"]))
    assert followup.response_json["needs_review"] is True

    # The provider sees the manual-review item in their followups view.
    provider_token = _login(client, "provider.demo@trackskill.in")["access_token"]
    provider_followups = client.get("/provider/followups", headers=_auth(provider_token)).json()
    assert any(
        item["followup_id"] == body["followup_id"] for item in provider_followups["manual_review"]
    )


# ── Anomaly rules ────────────────────────────────────────────────────────────


def _make_record(
    client: TestClient, db_session, *, email: str, wage: int, start_offset_days: int
) -> EmploymentRecord:
    """Certified trainee + an employment record with controlled values."""
    trainee_id, _ = _enrol_and_certify(client, db_session, email, f"Anomaly {email.split('@')[0]}")
    trainee = db_session.get(Trainee, uuid.UUID(trainee_id))
    # Backdate the journey so realistic start dates exist: certified 60 days
    # ago, enrolled 24 weeks before that.
    trainee.certified_on = date.today() - timedelta(days=60)
    trainee.enrolled_on = trainee.certified_on - timedelta(weeks=24)
    db_session.flush()
    record = EmploymentRecord(
        id=uuid.uuid4(),
        trainee_id=trainee.id,
        employer_id=None,
        status=EmploymentStatus.EMPLOYED,
        job_title="Test Role",
        monthly_wage=wage,
        started_on=trainee.certified_on + timedelta(days=start_offset_days),
    )
    db_session.add(record)
    db_session.flush()
    return record


def test_wage_outlier_rule_raises_flag(client: TestClient, db_session) -> None:
    record = _make_record(
        client, db_session, email="anomaly.wage@trackskill.in", wage=250000, start_offset_days=30
    )
    raised = asyncio.run(check_employment_record(db_session, record))
    assert RULE_WAGE_OUTLIER in raised

    event = db_session.execute(
        select(Event).where(Event.type == "FLAG_RAISED").order_by(Event.created_at.desc())
    ).scalars().first()
    assert event.payload["rule"] == RULE_WAGE_OUTLIER

    # Deduplication: the same record never double-raises.
    assert asyncio.run(check_employment_record(db_session, record)) == []


def test_impossible_start_date_rule(client: TestClient, db_session) -> None:
    record = _make_record(
        client,
        db_session,
        email="anomaly.date@trackskill.in",
        wage=20000,
        start_offset_days=-120,  # 120 days BEFORE certification
    )
    raised = asyncio.run(check_employment_record(db_session, record))
    assert "IMPOSSIBLE_START_DATE" in raised


def test_normal_record_raises_nothing(client: TestClient, db_session) -> None:
    record = _make_record(
        client, db_session, email="anomaly.normal@trackskill.in", wage=22000, start_offset_days=30
    )
    assert asyncio.run(check_employment_record(db_session, record)) == []


def test_employer_confirmation_spike_and_admin_scan(client: TestClient, db_session) -> None:
    admin_token = _login(client, "admin.demo@trackskill.in")["access_token"]
    employer = db_session.execute(
        select(Employer).join(User, Employer.user_id == User.id).where(
            User.email == "employer.demo@trackskill.in"
        )
    ).scalar_one()

    # Seed + chain data push the demo employer over the threshold. The flag
    # may already exist (dedupe is global), so accept either outcome — but a
    # second identical check must never raise again.
    raised = asyncio.run(check_employer_confirmation_volume(db_session, employer.id))
    assert raised in ([], ["EMPLOYER_CONFIRMATION_SPIKE"])
    assert asyncio.run(check_employer_confirmation_volume(db_session, employer.id)) == []

    scan = client.post("/admin/anomalies/scan", headers=_auth(admin_token))
    assert scan.status_code == 200, scan.text
    body = scan.json()
    assert {"raised", "raised_count"} <= set(body)

    events = client.get("/admin/events?limit=200", headers=_auth(admin_token))
    flag_events = [event for event in events.json() if event["type"] == "FLAG_RAISED"]
    assert flag_events, "FLAG_RAISED events must reach the admin audit feed"


# ── Dual-signal source of truth ──────────────────────────────────────────────


def test_dual_signal_helper_is_single_source_of_truth() -> None:
    assert is_verified((VerificationSignal.CONFIRMED, VerificationSignal.CONFIRMED)) is True
    assert is_verified((VerificationSignal.CONFIRMED, VerificationSignal.PENDING)) is False
    assert is_verified(None) is False


