"""Public landing-page contact endpoint."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models import ContactMessage
from app.schemas.contact import ContactRequest
from app.services.rate_limit import contact_limiter, enforce_rate_limit
from app.services.realtime import publish_event

router = APIRouter(tags=["contact"])


@router.post("/contact", status_code=201, summary="Submit a contact enquiry")
async def submit_contact(
    payload: ContactRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Public endpoint: stores the enquiry and notifies admins live."""
    enforce_rate_limit(
        contact_limiter, request, max_attempts=5, window_seconds=600, scope="contact"
    )
    message = ContactMessage(
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        organisation=(payload.organisation or "").strip() or None,
        role=payload.role,
        message=payload.message.strip(),
    )
    db.add(message)
    db.flush()

    await publish_event(
        db,
        event_type="CONTACT_RECEIVED",
        actor_user_id=None,
        actor_role="PUBLIC",
        payload={
            "contact_id": str(message.id),
            "name": message.name,
            "role": message.role,
            "organisation": message.organisation,
        },
        audience_roles=["ADMIN"],
    )

    settings = get_settings()
    return {
        "status": "received",
        "id": str(message.id),
        "message": (
            "Thanks for reaching out — the TrackSkill AI team will "
            f"reply to {message.email} within two working days."
        ),
        "contact": settings.project_name,
    }
