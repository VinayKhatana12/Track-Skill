"""Market demand signals used for curriculum-to-industry matching."""

from datetime import date

from sqlalchemy import Date, Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MarketDemand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_demand"
    __table_args__ = (
        UniqueConstraint("sector", "skill", "district", "month"),
        Index("ix_market_demand_district_month", "district", "month"),
    )

    sector: Mapped[str] = mapped_column(String(120), nullable=False)
    skill: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    district: Mapped[str] = mapped_column(String(120), nullable=False)
    demand_score: Mapped[float] = mapped_column(Float, nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
