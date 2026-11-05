"""Admin REST API: state KPIs, PPI leaderboard, allocations, audit feed."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai import anomalies, curriculum_matcher
from app.core.config import get_settings
from app.core.db import get_db
from app.dependencies import require_role
from app.models import User
from app.models.enums import UserRole
from app.schemas.domain import AllocationRequest, FlagRequest
from app.services import admin_service, tracer_service

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/tracer/run", summary="Run the tracer cycle now (demo fast-forward)")
async def run_tracer(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    """Demo control: fast-forwards demo tracers to today and delivers them.

    Available only while DEMO_MODE is enabled.
    """
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return await tracer_service.run_tracer_now(db)


@router.get("/overview", summary="State-wide KPIs and district heat data")
def overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    return admin_service.state_overview(db)


@router.get("/providers", summary="PPI leaderboard")
def providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> list[dict]:
    return admin_service.providers_leaderboard(db)


@router.get("/providers/{centre_id}", summary="Centre detail with score history")
def provider_detail(
    centre_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    return admin_service.provider_detail(db, centre_id)


@router.post("/allocations", status_code=201, summary="Record a fund allocation")
async def create_allocation(
    payload: AllocationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    return await admin_service.create_allocation(
        db,
        admin_user=current_user,
        centre_id=payload.centre_id,
        amount=float(payload.amount),
        rationale=payload.rationale,
    )


@router.post("/providers/{centre_id}/flag", summary="Flag a centre (live notification)")
async def flag_provider(
    centre_id: UUID,
    payload: FlagRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    return await admin_service.flag_provider(
        db, admin_user=current_user, centre_id=centre_id, reason=payload.reason
    )


@router.post("/demo/reset", summary="Reset demo data (DEMO_MODE only)")
async def demo_reset(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return await admin_service.reset_demo_data(db)


@router.get(
    "/curriculum-gaps",
    summary="Per-course curriculum-demand gap report (AI module)",
)
def curriculum_gaps(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> list[dict]:
    return curriculum_matcher.course_gap_report(db, limit=limit)


@router.post("/anomalies/scan", summary="Run statistical anomaly detection now")
async def run_anomaly_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> dict:
    raised = await anomalies.scan_all(db)
    return {"raised": raised, "raised_count": len(raised)}


@router.get("/events", summary="Live audit feed")
def events(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> list[dict]:
    return admin_service.events_feed(db, limit=limit)
