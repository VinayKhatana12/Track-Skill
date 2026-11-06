"""TrackSkill AI API entrypoint."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.realtime.ws import router as ws_router
from app.routers import (
    admin,
    auth,
    contact,
    employer,
    health,
    notifications,
    provider,
    push,
    search,
    trainee,
    trainees,
)

logging.basicConfig(
    level=get_settings().log_level.upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def tracer_tick() -> None:
    """One background tracer cycle: create, send, expire."""
    from app.core.db import SessionLocal
    from app.services import tracer_service

    with SessionLocal() as db:
        summary = await tracer_service.run_tracer_cycle(db)
        db.commit()
        if summary["created"] or summary["sent"] or summary["missed"]:
            logger.info(
                "Tracer tick: created %s, sent %s, missed %s",
                summary["created"],
                len(summary["sent"]),
                len(summary["missed"]),
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logger.info(
        "Starting %s v%s (%s)",
        settings.project_name,
        settings.project_version,
        settings.environment,
    )
    scheduler_started = False
    if settings.scheduler_enabled:
        scheduler.add_job(
            tracer_tick,
            "interval",
            seconds=settings.tracer_interval_seconds,
            id="tracer-tick",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        scheduler_started = True
        logger.info(
            "Tracer scheduler started (interval %ss, provider %s)",
            settings.tracer_interval_seconds,
            settings.tracer_provider,
        )
    yield
    if scheduler_started:
        scheduler.shutdown(wait=False)
    logger.info("Shutting down %s", settings.project_name)


def create_app() -> FastAPI:
    """Build the FastAPI application with middleware and routers attached."""
    settings = get_settings()
    application = FastAPI(
        title=settings.project_name,
        version=settings.project_version,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    async def secure_headers(request: Request, call_next):
        """OWASP secure headers on every response (Phase 11).

        The API serves only JSON, so its CSP pins to 'none'; the browser app
        sets its own policy in next.config.mjs. HSTS is emitted in production
        (HTTPS) environments only — on plain-http local runs it is meaningless
        and would linger in cached responses.
        """
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    application.middleware("http")(secure_headers)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(contact.router)
    application.include_router(notifications.router)
    application.include_router(push.router)
    application.include_router(search.router)
    application.include_router(trainees.router)
    application.include_router(provider.router)
    application.include_router(trainee.router)
    application.include_router(employer.router)
    application.include_router(admin.router)
    application.include_router(ws_router)
    return application


app = create_app()
