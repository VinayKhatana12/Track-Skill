"""HTTP routers. Each domain gets its own module, registered in app.main."""

from app.routers import auth, health, trainees

__all__ = ["auth", "health", "trainees"]
