"""Public contact request schema."""

from pydantic import BaseModel, EmailStr, Field

CONTACT_ROLES = ("PROVIDER", "TRAINEE", "EMPLOYER", "ADMIN", "OTHER")


class ContactRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    organisation: str | None = Field(default=None, max_length=255)
    role: str = Field(pattern="^(PROVIDER|TRAINEE|EMPLOYER|ADMIN|OTHER)$")
    message: str = Field(min_length=10, max_length=4000)
