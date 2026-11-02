"""TrackSkill AI API entrypoint."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.realtime.ws import router as ws_router
from app.routers import admin, auth, contact, employer, health, provider, trainee, trainees

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
    application.include_router(trainees.router)
    application.include_router(provider.router)
    application.include_router(trainee.router)
    application.include_router(employer.router)
    application.include_router(admin.router)
    application.include_router(ws_router)
    return application


app = create_app()
