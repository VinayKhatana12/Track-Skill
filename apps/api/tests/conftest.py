"""Shared pytest fixtures: API client backed by a roll-back-per-test session.

Integration tests expect a migrated + seeded database behind DATABASE_URL
(`alembic upgrade head` and `python -m app.seed`); every write a test makes
is rolled back, so the dev database stays untouched.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import engine, get_db
from app.main import app
from app.services.rate_limit import login_limiter

TestingSessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


@pytest.fixture(name="db_session")
def db_session_fixture():
    """Session bound to an outer transaction that is always rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(name="client")
def client_fixture(db_session: Session, monkeypatch):
    """TestClient whose requests run against the roll-back test session.

    The background tracer scheduler is disabled so jobs never fire mid-test;
    tracer behaviour is exercised by calling the engine directly.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "scheduler_enabled", False)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    login_limiter.reset_all()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
