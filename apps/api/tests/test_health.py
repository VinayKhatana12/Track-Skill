"""Tests for the health endpoints."""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "TrackSkill AI"
    assert body["version"]
    assert body["environment"]


def test_readiness_reports_database_state(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["database"], bool)
    assert body["status"] in {"ok", "degraded"}
