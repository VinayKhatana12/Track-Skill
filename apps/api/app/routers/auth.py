"""Authentication endpoints: register, login, refresh, logout, profile."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import (
    clear_refresh_cookie,
    create_access_token,
    create_refresh_token,
    decode_token,
    set_refresh_cookie,
)
from app.dependencies import require_role
from app.models import Trainee, User
from app.models.enums import UserRole
from app.schemas import (
    DemoAccount,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserPublic,
)
from app.services.auth_service import (
    EmailAlreadyRegisteredError,
    UnknownCentreCodeError,
    authenticate_email_only,
    authenticate_user,
    create_password_reset_token,
    create_registration_consents,
    register_user,
    reset_password_with_token,
)
from app.services.rate_limit import enforce_rate_limit, login_limiter, reset_limiter

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
SELF_SIGNUP_ROLES = (UserRole.TRAINEE, UserRole.EMPLOYER)


def _set_refresh_cookie(response: Response, token: str) -> None:
    set_refresh_cookie(response, token)


def _clear_refresh_cookie(response: Response) -> None:
    clear_refresh_cookie(response)


def _token_response(user: User) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserPublic.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    """Self-signup for TRAINEE and EMPLOYER accounts only.

    PROVIDER and ADMIN accounts are provisioned by the seed or by an
    administrator. Signing up signs the caller in (access token in the body,
    refresh token as an httpOnly cookie).
    """
    if payload.role not in SELF_SIGNUP_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-signup is available for Trainee and Employer accounts only.",
        )
    if payload.role is UserRole.TRAINEE and (not payload.phone or not payload.district):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Trainee registration requires a phone number and district.",
        )
    if payload.role is UserRole.EMPLOYER and not (payload.company_name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Employer registration requires a company name.",
        )

    try:
        user = register_user(
            db,
            name=payload.name,
            email=payload.email,
            password=payload.password,
            role=payload.role,
            phone=payload.phone,
            district=payload.district,
            centre_code=payload.centre_code,
            company_name=payload.company_name,
            company_district=payload.company_district,
            company_sector=payload.company_sector,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    except UnknownCentreCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That centre code was not recognised. Check it with your training centre.",
        ) from exc

    if payload.role is UserRole.TRAINEE and payload.consent_channels:
        trainee = db.execute(
            select(Trainee).where(Trainee.user_id == user.id)
        ).scalar_one()
        create_registration_consents(
            db, trainee_id=trainee.id, channels=payload.consent_channels
        )

    _set_refresh_cookie(response, create_refresh_token(user.id))
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    """Exchange email + password for an access token and refresh cookie.

    Failures share one generic message and are rate limited per IP + email.
    """
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    limiter_key = f"{client_ip}:{payload.email.strip().lower()}"

    if not login_limiter.has_capacity(
        limiter_key, settings.login_max_attempts, settings.login_window_seconds
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )

    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        login_limiter.record(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    login_limiter.reset(limiter_key)
    _set_refresh_cookie(response, create_refresh_token(user.id))
    return _token_response(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange the httpOnly refresh cookie for a fresh access token.

    The refresh token is rotated on every use. CSRF: the cookie is
    SameSite=Lax and Path-scoped to /auth; as defense in depth a request that
    carries a cross-origin Origin header is rejected outright.
    """
    origin = request.headers.get("origin")
    if origin:
        allowed = {value.rstrip("/") for value in get_settings().cors_origins}
        if origin.rstrip("/") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-origin refresh requests are not allowed.",
            )
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    try:
        payload = decode_token(token, expected_type="refresh")
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session."
        ) from None

    try:
        user = db.get(User, UUID(str(payload.get("sub"))))
    except ValueError:
        user = None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session."
        )

    _set_refresh_cookie(response, create_refresh_token(user.id))
    return _token_response(user)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    """Clear the refresh cookie; the client drops its in-memory access token."""
    _clear_refresh_cookie(response)
    return {"detail": "Logged out."}


@router.post("/forgot-password", summary="Request a password reset")
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Always responds generically. In DEMO_MODE the response includes the
    reset link so the flow works without an email gateway."""
    enforce_rate_limit(
        reset_limiter, request, max_attempts=5, window_seconds=600, scope="forgot"
    )
    settings = get_settings()
    response: dict = {
        "status": "ok",
        "message": "If that email exists, a reset link has been sent.",
    }
    if settings.demo_mode:
        user = authenticate_email_only(db, payload.email)
        if user is not None:
            token = create_password_reset_token(user.id)
            response["reset_link"] = f"/reset-password?token={token}"
    return response


@router.post("/reset-password", summary="Reset the password with a demo token")
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> dict:
    applied = reset_password_with_token(
        db, token=payload.token, new_password=payload.new_password
    )
    if not applied:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired.",
        )
    return {"status": "ok", "message": "Password updated. You can sign in now."}


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(require_role())) -> User:
    """Profile of the authenticated user (any role)."""
    return current_user


@router.get("/admin-area")
def admin_area(current_user: User = Depends(require_role(UserRole.ADMIN))) -> dict[str, str]:
    """RBAC smoke endpoint: only ADMIN passes; every other role gets 403."""
    return {"detail": "Welcome to the admin area.", "role": current_user.role.value}


@router.get("/demo-accounts", response_model=list[DemoAccount])
def demo_accounts() -> list[DemoAccount]:
    """Pre-seeded reviewer logins, available only while DEMO_MODE is enabled."""
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    password = settings.demo_password
    return [
        DemoAccount(
            role=UserRole.ADMIN,
            email="admin.demo@trackskill.in",
            password=password,
            dashboard="/dashboard/admin",
        ),
        DemoAccount(
            role=UserRole.PROVIDER,
            email="provider.demo@trackskill.in",
            password=password,
            dashboard="/dashboard/provider",
        ),
        DemoAccount(
            role=UserRole.TRAINEE,
            email="trainee.demo@trackskill.in",
            password=password,
            dashboard="/dashboard/trainee",
        ),
        DemoAccount(
            role=UserRole.EMPLOYER,
            email="employer.demo@trackskill.in",
            password=password,
            dashboard="/dashboard/employer",
        ),
    ]
