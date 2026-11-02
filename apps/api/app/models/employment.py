"""Employment outcomes and their dual-signal verifications."""

import uuid
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Computed, Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EmploymentStatus, VerificationSignal

if TYPE_CHECKING:
    from app.models.employer import Employer
    from app.models.trainee import Trainee


class EmploymentRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employment_records"

    trainee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[EmploymentStatus] = mapped_column(
        Enum(EmploymentStatus, name="employment_status"), nullable=False, index=True
    )
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    monthly_wage: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    trainee: Mapped["Trainee"] = relationship(back_populates="employment_records")
    employer: Mapped[Optional["Employer"]] = relationship(back_populates="employment_records")
    verification: Mapped[Optional["Verification"]] = relationship(
        back_populates="employment_record", uselist=False
    )


# The database computes this column: verified exactly when both signals agree.
_VERIFIED_EXPRESSION = (
    "(trainee_signal = 'CONFIRMED'::verification_signal) "
    "AND (employer_signal = 'CONFIRMED'::verification_signal)"
)


class Verification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "verifications"

    employment_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employment_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    trainee_signal: Mapped[VerificationSignal] = mapped_column(
        Enum(VerificationSignal, name="verification_signal"),
        nullable=False,
        default=VerificationSignal.PENDING,
    )
    employer_signal: Mapped[VerificationSignal] = mapped_column(
        Enum(VerificationSignal, name="verification_signal"),
        nullable=False,
        default=VerificationSignal.PENDING,
    )
    verified: Mapped[bool] = mapped_column(
        Boolean,
        Computed(_VERIFIED_EXPRESSION, persisted=True),
        nullable=False,
    )

    employment_record: Mapped["EmploymentRecord"] = relationship(
        back_populates="verification"
    )
