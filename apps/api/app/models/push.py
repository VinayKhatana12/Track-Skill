"""Web push subscriptions (Phase 10): one row per browser/device."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class PushSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Web Push endpoint registered for a user.

    ``p256dh``/``auth`` are the client's ECDH keys from the subscription JSON;
    ``endpoint`` is unique so re-subscribing the same browser replaces the row.
    Subscriptions whose push service answers 404/410 are pruned on send.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[Optional["User"]] = relationship()
