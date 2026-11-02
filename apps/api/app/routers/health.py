"""Health and readiness endpoints."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas import HealthResponse, ReadinessResponse
from app.services import check_database

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe: the API process is up."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.project_name,
        version=settings.project_version,
        environment=settings.environment,
    )


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness() -> ReadinessResponse:
    """Readiness probe: the API can reach its database."""
    settings = get_settings()
    database_ok = check_database()
    return ReadinessResponse(
        status="ok" if database_ok else "degraded",
        service=settings.project_name,
        version=settings.project_version,
        environment=settings.environment,
        database=database_ok,
    )
