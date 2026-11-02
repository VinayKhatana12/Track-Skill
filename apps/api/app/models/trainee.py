"""Trainees and their consent records.

Consent is mandatory: no follow-up may be traced for a trainee without an
active row in ``consents`` (granted=True, revoked_at IS NULL).
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConsentChannel, TraineeStatus

if TYPE_CHECKING:
    from app.models.centre import TrainingCentre
    from app.models.course import Course
    from app.models.employment import EmploymentRecord
    from app.models.followup import FollowUp
    from app.models.user import User


class Trainee(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trainees"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    centre_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_centres.id", ondelete="CASCADE"), nullable=True, index=True
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    district: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    enrolled_on: Mapped[date] = mapped_column(Date, nullable=False)
    certified_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[TraineeStatus] = mapped_column(
        Enum(TraineeStatus, name="trainee_status"), nullable=False, index=True
    )

    user: Mapped["User"] = relationship(back_populates="trainee_profile")
    centre: Mapped["TrainingCentre"] = relationship(back_populates="trainees")
    course: Mapped["Course"] = relationship(back_populates="trainees")
    consents: Mapped[list["Consent"]] = relationship(back_populates="trainee")
    employment_records: Mapped[list["EmploymentRecord"]] = relationship(
        back_populates="trainee"
    )
    followups: Mapped[list["FollowUp"]] = relationship(back_populates="trainee")


class Consent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("trainee_id", "channel", "version"),)

    trainee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[ConsentChannel] = mapped_column(
        Enum(ConsentChannel, name="consent_channel"), nullable=False
    )
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purpose_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)

    trainee: Mapped["Trainee"] = relationship(back_populates="consents")
