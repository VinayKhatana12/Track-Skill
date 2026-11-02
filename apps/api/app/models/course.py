"""Vocational courses offered by training centres."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.centre import TrainingCentre
    from app.models.trainee import Trainee


class Course(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("nsqf_level >= 1 AND nsqf_level <= 10", name="nsqf_level_range"),
    )

    centre_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_centres.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    nsqf_level: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    centre: Mapped["TrainingCentre"] = relationship(back_populates="courses")
    trainees: Mapped[list["Trainee"]] = relationship(back_populates="course")
