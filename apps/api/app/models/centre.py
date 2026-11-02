"""Training centres and their provider staff."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.governance import FundAllocation, ProviderScore
    from app.models.trainee import Trainee
    from app.models.user import User


class TrainingCentre(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "training_centres"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    district: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(120), nullable=False)
    sector_focus: Mapped[str] = mapped_column(String(120), nullable=False)
    funding_status: Mapped[str] = mapped_column(String(60), nullable=False)

    courses: Mapped[list["Course"]] = relationship(back_populates="centre")
    staff_links: Mapped[list["ProviderStaff"]] = relationship(back_populates="centre")
    trainees: Mapped[list["Trainee"]] = relationship(back_populates="centre")
    scores: Mapped[list["ProviderScore"]] = relationship(back_populates="centre")
    fund_allocations: Mapped[list["FundAllocation"]] = relationship(back_populates="centre")


class ProviderStaff(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "provider_staff"
    __table_args__ = (UniqueConstraint("user_id", "centre_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    centre_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_centres.id", ondelete="CASCADE"), nullable=False, index=True
    )

    user: Mapped["User"] = relationship(back_populates="staff_links")
    centre: Mapped["TrainingCentre"] = relationship(back_populates="staff_links")
