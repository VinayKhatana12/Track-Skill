"""Service layer: business logic lives here, routers stay thin."""

from app.services.health_service import check_database

__all__ = ["check_database"]
