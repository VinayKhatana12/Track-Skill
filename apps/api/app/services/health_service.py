"""Domain-agnostic service helpers backing the health endpoints."""

import logging

from sqlalchemy import text

from app.core.db import engine

logger = logging.getLogger(__name__)


def check_database() -> bool:
    """Return True when the database answers a trivial query, False otherwise."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # any failure means "not ready"
        logger.warning("Database readiness check failed: %s", exc)
        return False
