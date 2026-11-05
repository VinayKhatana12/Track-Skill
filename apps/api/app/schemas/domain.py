"""Request payloads for the role-scoped REST APIs."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import ConsentChannel, EmploymentStatus


class EnrolTraineeRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone: str = Field(min_length=5, max_length=20)
    course_id: UUID
    gender: str = Field(default="UNSPECIFIED", max_length=20)
    centre_id: UUID | None = None


class CertifyTraineeRequest(BaseModel):
    certified_on: date | None = None


class ConsentRequest(BaseModel):
    channel: ConsentChannel
    granted: bool


class RespondTextRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class SkillsAssessmentRequest(BaseModel):
    self_reported_skills: list[str] = Field(default_factory=list, max_length=20)
    free_text: str | None = Field(default=None, max_length=2000)


class RespondFollowUpRequest(BaseModel):
    employment_status: EmploymentStatus
    job_title: str | None = Field(default=None, max_length=255)
    monthly_wage: float | None = Field(default=None, ge=0)
    employer_id: UUID | None = None


class EmploymentSelfReportRequest(BaseModel):
    employment_status: EmploymentStatus
    job_title: str = Field(min_length=2, max_length=255)
    monthly_wage: float = Field(gt=0)
    started_on: date | None = None
    employer_id: UUID | None = None


class HireTraineeRequest(BaseModel):
    job_title: str = Field(min_length=2, max_length=255)
    monthly_wage: float = Field(gt=0)
    started_on: date | None = None


class DisputeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AllocationRequest(BaseModel):
    centre_id: UUID
    amount: Decimal = Field(gt=0)
    rationale: str = Field(min_length=3, max_length=1000)


class FlagRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
