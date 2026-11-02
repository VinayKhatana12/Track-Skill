"""Trainee-facing schemas."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import TraineeStatus


class TraineePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    centre_id: UUID
    course_id: UUID
    district: str
    gender: str
    enrolled_on: date
    certified_on: date | None
    status: TraineeStatus
