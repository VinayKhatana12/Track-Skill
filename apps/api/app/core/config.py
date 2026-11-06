"""Application settings, loaded from environment variables / .env files."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the TrackSkill AI API."""

    # Application
    project_name: str = "TrackSkill AI"
    project_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+psycopg://trackskill:trackskill_dev_password@localhost:5432/trackskill"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Security — JWT (access + refresh) and session cookies.
    # HS256 needs at least 32 bytes of key material; generate a real secret
    # for anything outside local development.
    secret_key: str = "dev-only-insecure-secret-key-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # Demo mode exposes GET /auth/demo-accounts (never enable in production).
    demo_mode: bool = True
    demo_password: str = "Demo@1234"

    # AI module: true = deterministic hashed n-gram embedder (no model
    # download, runs on any laptop); false = sentence-transformers
    # all-MiniLM-L6-v2 (better semantics, needs the package + model).
    use_light_nlp: bool = True

    # Tracer engine (Phase 6): delivery gateway + background scheduler.
    tracer_provider: str = "simulated"  # simulated | twilio | meta (stubs)
    scheduler_enabled: bool = True
    tracer_interval_seconds: int = 300
    tracer_expiry_days: int = 14  # SENT -> MISSED when no reply after this many days
    tracer_max_attempts: int = 3

    # Login rate limiting (in-memory sliding window per IP + email).
    login_max_attempts: int = 5
    login_window_seconds: int = 300

    # Web Push (Phase 10): VAPID identity. Both keys may be omitted — a P-256
    # pair is then generated once and stored in vapid_keys_file so local demo
    # runs need zero configuration. Provide real keys in production:
    #   python -m app.core.vapid
    vapid_private_key: str | None = None
    vapid_public_key: str | None = None
    vapid_keys_file: str = "vapid-keys.json"
    push_subject: str = "mailto:demo@trackskill.in"

    # CORS — NoDecode keeps pydantic-settings from JSON-parsing the raw env
    # string so the comma-split validator below can handle it.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept CORS_ORIGINS='http://a,http://b' in addition to JSON lists."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
