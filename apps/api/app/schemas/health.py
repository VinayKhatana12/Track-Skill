"""Response schemas for the health endpoints."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness payload reported by GET /health."""

    status: str
    service: str
    version: str
    environment: str


class ReadinessResponse(HealthResponse):
    """Readiness payload reported by GET /health/ready (includes DB check)."""

    database: bool
