"""Privacy helpers (Phase 11): field masking and sensitive-read auditing.

``mask_phone`` / ``mask_email`` let any serializer expose contact fields to
roles that do not own the record without leaking the full value. ``audit_read``
writes an append-only Event row (type ``READ_AUDIT``) for every read that
exposes personal data across roles — audited reads are queryable via the
events table and never broadcast over the realtime channels.
"""

import logging
import re
from typing import TYPE_CHECKING

from app.models import Event

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.models.user import User

logger = logging.getLogger(__name__)

_PHONE_KEEP = re.compile(r"[+\d]")
_MASK = "\u2022"  # bullet •


def mask_phone(phone: str | None) -> str | None:
    """Keep the leading country code and the last four digits; mask the rest.

    ``+91 90123 45678`` -> ``+91 •••••45678``. Non-owner roles only ever see
    this form; the owner (the trainee) and their centre's provider staff see
    the full value through owner-scoped endpoints.
    """
    if not phone:
        return phone
    digits = "".join(character for character in phone if _PHONE_KEEP.match(character))
    if len(digits) <= 4:
        return _MASK * len(digits) if digits else phone
    country_end = 3 if digits.startswith("+") else 0
    tail = digits[-4:]
    masked_count = max(len(digits) - country_end - 4, 2)
    prefix = digits[:country_end] if country_end else ""
    if prefix:
        return f"{prefix} {_MASK * masked_count}{tail}"
    return f"{_MASK * masked_count}{tail}"


def mask_email(email: str | None) -> str | None:
    """Show the first two characters of the local part, then dots.

    ``meera.iyer@example.com`` -> ``me••••••@example.com``.
    """
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    visible = local[:2]
    return f"{visible}{_MASK * max(len(local) - 2, 3)}@{domain}"


def audit_read(
    db: "Session",
    *,
    reader: "User",
    kind: str,
    detail: dict | None = None,
) -> "UUID":
    """Record that ``reader`` accessed personal data of ``kind``.

    Only the audit row is written — no WebSocket broadcast, no notification:
    reads happen constantly and must not create alert noise, but they must
    all be attributable.
    """
    event = Event(
        type="READ_AUDIT",
        actor_user_id=reader.id,
        actor_role=reader.role.value,
        payload={"kind": kind, **(detail or {})},
    )
    db.add(event)
    db.flush()
    logger.info("READ_AUDIT %s by %s (%s)", kind, reader.id, reader.role.value)
    return event.id
