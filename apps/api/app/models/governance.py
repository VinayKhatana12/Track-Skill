"""Governance analytics: Provider Performance Index and fund allocations."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.centre import TrainingCentre
    from app.models.user import User


class ProviderScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "provider_scores"
    __table_args__ = (UniqueConstraint("centre_id", "period"),)

    centre_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_centres.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[date] = mapped_column(Date, nullable=False)
    placement_rate: Mapped[float] = mapped_column(Float, nullable=False)
    retention_3m: Mapped[float] = mapped_column(Float, nullable=False)
    retention_6m: Mapped[float] = mapped_column(Float, nullable=False)
    retention_12m: Mapped[float] = mapped_column(Float, nullable=False)
    wage_growth: Mapped[float] = mapped_column(Float, nullable=False)
    verification_rate: Mapped[float] = mapped_column(Float, nullable=False)
    ppi_score: Mapped[float] = mapped_column(Float, nullable=False)

    centre: Mapped["TrainingCentre"] = relationship(back_populates="scores")


class FundAllocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fund_allocations"

    centre_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_centres.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    centre: Mapped["TrainingCentre"] = relationship(back_populates="fund_allocations")
    decider: Mapped[Optional["User"]] = relationship()
