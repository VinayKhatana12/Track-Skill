"""Authentication services: credential checks, self-signup, password reset.

Self-signup creates the role profile too: a trainee row (optionally linked
to a centre via its code) or an employer row — so consent and dashboards
work immediately after registration.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import CONSENT_PURPOSE, CONSENT_VERSION
from app.core.security import hash_password, verify_password
from app.models import Consent, Employer, Trainee, TrainingCentre, User
from app.models.enums import ConsentChannel, TraineeStatus, UserRole

logger = logging.getLogger(__name__)

# Verifying against this hash when the account does not exist keeps response
# times uniform, so attackers cannot enumerate emails by timing.
_DUMMY_PASSWORD_HASH = hash_password("timing-equalizer-not-a-real-password")


class EmailAlreadyRegisteredError(Exception):
    """Raised when self-signup hits an existing email address."""


class UnknownCentreCodeError(Exception):
    """Raised when a registration centre code does not match any centre."""


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return the user for valid, active credentials; None otherwise."""
    normalized = email.strip().lower()
    user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def authenticate_email_only(db: Session, email: str) -> User | None:
    """Look up an active user by email (no secret involved)."""
    normalized = email.strip().lower()
    user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


def register_user(
    db: Session,
    *,
    name: str,
    email: str,
    password: str,
    role: UserRole,
    phone: str | None = None,
    district: str | None = None,
    centre_code: str | None = None,
    company_name: str | None = None,
    company_district: str | None = None,
    company_sector: str | None = None,
) -> User:
    """Create a new account plus its role profile (trainee or employer row).

    Self-registered trainees are not attached to a centre unless they provide
    a valid centre code; tracers start once a provider certifies them.
    """
    normalized = email.strip().lower()
    existing = db.execute(select(User.id).where(User.email == normalized)).scalar_one_or_none()
    if existing is not None:
        raise EmailAlreadyRegisteredError(normalized)

    user = User(
        name=name.strip(),
        email=normalized,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()

    if role is UserRole.TRAINEE:
        centre_id = None
        if centre_code and centre_code.strip():
            centre = db.execute(
                select(TrainingCentre).where(
                    TrainingCentre.code == centre_code.strip().upper()
                )
            ).scalar_one_or_none()
            if centre is None:
                raise UnknownCentreCodeError(centre_code)
            centre_id = centre.id
        db.add(
            Trainee(
                id=uuid4(),
                user_id=user.id,
                centre_id=centre_id,
                course_id=None,
                phone=(phone or "").strip() or "Unlisted",
                district=(district or "").strip() or "Unlisted",
                gender="UNSPECIFIED",
                enrolled_on=date.today(),
                certified_on=None,
                status=TraineeStatus.ENROLLED,
            )
        )
    elif role is UserRole.EMPLOYER:
        db.add(
            Employer(
                id=uuid4(),
                user_id=user.id,
                company_name=(company_name or "").strip() or f"{name.strip()} (Employer)",
                sector=(company_sector or "").strip() or "Other",
                district=(company_district or "").strip() or "Unlisted",
            )
        )

    db.flush()
    logger.info("Registered new %s account: %s", role.value, normalized)
    return user


def create_registration_consents(
    db: Session, *, trainee_id: UUID, channels: list[ConsentChannel]
) -> int:
    """Store version-stamped consent rows for channels accepted at signup.

    The frontend applies these right after registration; tracers only start
    once a provider certifies the trainee.
    """
    granted_at = datetime.now(UTC)
    created = 0
    for channel in channels:
        existing = db.execute(
            select(Consent.id).where(
                Consent.trainee_id == trainee_id,
                Consent.channel == channel,
                Consent.version == CONSENT_VERSION,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            Consent(
                id=uuid4(),
                trainee_id=trainee_id,
                channel=channel,
                granted=True,
                granted_at=granted_at,
                revoked_at=None,
                purpose_text=CONSENT_PURPOSE,
                version=CONSENT_VERSION,
            )
        )
        created += 1
    if created:
        db.flush()
    logger.info("Stored %s registration consent(s) for trainee %s", created, trainee_id)
    return created


def create_password_reset_token(user_id: UUID) -> str:
    """Short-lived password-reset token (30 minutes, single purpose)."""
    from app.core.security import _create_token

    return _create_token(str(user_id), "pwd_reset", timedelta(minutes=30))


def reset_password_with_token(db: Session, *, token: str, new_password: str) -> bool:
    """Reset a password given a valid pwd_reset token. False if invalid."""
    from jwt import InvalidTokenError

    from app.core.security import decode_token

    try:
        payload = decode_token(token, expected_type="pwd_reset")
    except InvalidTokenError:
        return False
    try:
        user_id = UUID(str(payload.get("sub")))
    except ValueError:
        return False
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return False
    user.password_hash = hash_password(new_password)
    db.flush()
    logger.info("Password reset applied for %s", user.email)
    return True
