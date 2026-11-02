"""Request/response schemas for authentication."""

import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import ConsentChannel, UserRole


class RegisterRequest(BaseModel):
    """Self-signup payload (TRAINEE and EMPLOYER only — enforced in the router).

    The profile fields are validated conditionally in the router: trainees
    supply phone + district (+ optional centre code), employers supply a
    company name.
    """

    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: UserRole
    phone: str | None = Field(default=None, max_length=20)
    district: str | None = Field(default=None, max_length=120)
    centre_code: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=255)
    company_district: str | None = Field(default=None, max_length=120)
    company_sector: str | None = Field(default=None, max_length=120)
    consent_channels: list[ConsentChannel] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        """Require upper case, lower case, a number and a symbol."""
        checks = {
            "an uppercase letter": re.search(r"[A-Z]", value),
            "a lowercase letter": re.search(r"[a-z]", value),
            "a number": re.search(r"[0-9]", value),
            "a symbol": re.search(r"[^A-Za-z0-9]", value),
        }
        missing = [label for label, match in checks.items() if not match]
        if missing:
            raise ValueError("Password must contain " + ", ".join(missing) + ".")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    """Non-sensitive account fields returned to the caller."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    role: UserRole
    is_demo: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class DemoAccount(BaseModel):
    """A pre-seeded reviewer login, exposed only while DEMO_MODE is enabled."""

    role: UserRole
    email: str
    password: str
    dashboard: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        checks = {
            "an uppercase letter": re.search(r"[A-Z]", value),
            "a lowercase letter": re.search(r"[a-z]", value),
            "a number": re.search(r"[0-9]", value),
            "a symbol": re.search(r"[^A-Za-z0-9]", value),
        }
        missing = [label for label, match in checks.items() if not match]
        if missing:
            raise ValueError("Password must contain " + ", ".join(missing) + ".")
        return value
