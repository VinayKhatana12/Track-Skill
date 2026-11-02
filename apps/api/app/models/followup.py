"""Post-certification follow-up tracers at the 3/6/12-month milestones."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConsentChannel, FollowUpMilestone, FollowUpState

if TYPE_CHECKING:
    from app.models.trainee import Trainee


class FollowUp(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "followups"
    __table_args__ = (UniqueConstraint("trainee_id", "milestone"),)

    trainee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    milestone: Mapped[FollowUpMilestone] = mapped_column(
        Enum(FollowUpMilestone, name="followup_milestone"), nullable=False
    )
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[ConsentChannel] = mapped_column(
        Enum(ConsentChannel, name="consent_channel"), nullable=False
    )
    state: Mapped[FollowUpState] = mapped_column(
        Enum(FollowUpState, name="followup_state"), nullable=False, index=True
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Delivery tracking for the tracer engine (Phase 6).
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trainee: Mapped["Trainee"] = relationship(back_populates="followups")
