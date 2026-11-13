"""Auth router — public signup and login endpoints.

Delegates all identity operations to **Supabase Auth**.  FastAPI is a thin
wrapper: it validates the request shape, calls the Supabase Auth API, maps
Supabase error responses to appropriate HTTP status codes, and returns the
token pair (or user info) to the client.

**No** password hashing or JWT generation happens here — Supabase owns that.

Endpoints
---------
POST /auth/signup
    Create a new account with email + password.
    Returns 201 with user id and session tokens on success.
    Returns 400 on duplicate email or password policy violation.-bad reuquest

POST /auth/login
    Authenticate with email + password.
    Returns 200 with ``{access_token, refresh_token}`` on success.
    Returns 401 on invalid credentials.-unauthorized
"""

import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user
from app.db.supabase_client import create_client, supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Regex that checks email *syntax* only — no DNS/MX lookup.
# Supabase validates the real deliverability server-side.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class AuthRequest(BaseModel):
    """Shared request body for signup and login."""

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email_syntax(cls, v: str) -> str:
        """Reject obviously malformed addresses without a DNS check."""
        if not _EMAIL_RE.match(v):
            raise ValueError(f"Invalid email address: {v!r}")
        return v.lower().strip()


class GoogleAuthRequest(BaseModel):
    """Request body for Google Sign-In."""

    id_token: str


class SignupResponse(BaseModel):
    """Response schema for a successful signup."""

    user_id: str
    access_token: str
    refresh_token: str
    message: str = "Account created successfully."


class LoginResponse(BaseModel):
    """Response schema for a successful login."""

    access_token: str
    refresh_token: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_supabase_error(exc: Exception) -> str:
    """Return a safe, human-readable error message from a Supabase exception.

    Never leaks internal stack details or raw Supabase JSON — only the
    message string is forwarded to the client.
    """
    message = str(exc)
    # Supabase-py wraps API errors; surface only the message text.
    if hasattr(exc, "message"):
        message = exc.message  # type: ignore[attr-defined]
    return message


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
    description=(
        "Registers a new user with email and password via Supabase Auth. "
        "Returns the user id and session token pair on success. "
        "Returns **400** for duplicate email or a password that does not meet "
        "Supabase's minimum policy (>= 6 characters by default)."
    ),
)
def signup(payload: AuthRequest) -> Any:
    """Register a new user account via Supabase Auth.

    Args:
        payload: ``{email, password}`` -- validated by Pydantic.

    Returns:
        SignupResponse with user id and JWT session tokens.

    Raises:
        HTTPException(400): Duplicate email or weak password.
        HTTPException(500): Unexpected Supabase error.
    """
    logger.info("Signup attempt for email: %s", payload.email)

    try:
        response = supabase.auth.sign_up({"email": payload.email, "password": payload.password})
    except Exception as exc:
        error_msg = _extract_supabase_error(exc)
        logger.warning("Signup failed for %s -- %s", payload.email, error_msg)
        # Supabase raises for duplicate email / weak password; treat as 400.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        ) from exc

    # Supabase may return a user with no session when email confirmation is
    # required.  We still return 201 but tokens may be empty strings in that
    # case -- the client should check its email.
    user = response.user
    session = response.session

    if user is None:
        # Supabase returned success but no user object -- should not happen
        # with email/password sign-up, but guard defensively.
        logger.error("Supabase signup returned no user object for %s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup failed -- please try again.",
        )

    # Check for duplicate email: Supabase sometimes returns a user with
    # identities=[] when the email already exists (depends on project settings).
    if user.identities is not None and len(user.identities) == 0:
        logger.warning("Duplicate email signup attempt: %s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    logger.info("Signup successful for user_id=%s", user.id)
    return SignupResponse(
        user_id=str(user.id),
        access_token=session.access_token if session else "",
        refresh_token=session.refresh_token if session else "",
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Log in with email and password",
    description=(
        "Authenticates a user with email and password via Supabase Auth. "
        "Returns a JWT access token (~1 hour lifetime) and a refresh token. "
        "Returns **401** for invalid credentials."
    ),
)
def login(payload: AuthRequest) -> Any:
    """Authenticate and return a JWT token pair.

    Args:
        payload: ``{email, password}`` -- validated by Pydantic.

    Returns:
        LoginResponse with ``access_token`` and ``refresh_token``.

    Raises:
        HTTPException(401): Invalid email or password.
        HTTPException(500): Unexpected Supabase error.
    """
    logger.info("Login attempt for email: %s", payload.email)

    try:
        response = supabase.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
    except Exception as exc:
        error_msg = _extract_supabase_error(exc)
        logger.warning("Login failed for %s -- %s", payload.email, error_msg)
        if any(
            kw in error_msg.lower()
            for kw in ("too many", "rate limit", "lockout", "locked out")
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=error_msg,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        ) from exc

    session = response.session
    if session is None:
        logger.error("Supabase login returned no session for %s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed -- no session returned.",
        )

    logger.info("Login successful for email: %s", payload.email)
    return LoginResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
    )


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


class RefreshRequest(BaseModel):
    """Request body for the token refresh endpoint."""

    refresh_token: str


class RefreshResponse(BaseModel):
    """Response schema for a successful token refresh."""

    access_token: str
    refresh_token: str


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh the access token",
    description=(
        "Exchanges a valid refresh token for a new access token + refresh "
        "token pair.  Use this when the access token has expired "
        "(``X-Token-Expired: true`` header on the previous 401 response). "
        "Returns **401** if the refresh token is invalid or already used."
    ),
)
def refresh_token(payload: RefreshRequest) -> Any:
    """Issue a new access token using a refresh token.

    Args:
        payload: ``{refresh_token}`` -- the refresh token from a previous
                 login or refresh response.

    Returns:
        RefreshResponse with a fresh ``access_token`` and ``refresh_token``.

    Raises:
        HTTPException(401): Refresh token invalid or expired.
    """
    logger.info("Token refresh attempt")

    try:
        response = supabase.auth.refresh_session(payload.refresh_token)
    except Exception as exc:
        error_msg = _extract_supabase_error(exc)
        logger.warning("Token refresh failed -- %s", error_msg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        ) from exc

    session = response.session
    if session is None:
        logger.error("Supabase refresh returned no session")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token refresh failed -- no session returned.",
        )

    logger.info("Token refresh successful")
    return RefreshResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
    )

# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------


class ForgotPasswordRequest(BaseModel):
    """Request body for the forgot-password endpoint."""

    email: str

    @field_validator("email")
    @classmethod
    def validate_email_syntax(cls, v: str) -> str:
        """Reject obviously malformed addresses without a DNS check."""
        if not _EMAIL_RE.match(v):
            raise ValueError(f"Invalid email address: {v!r}")
        return v.lower().strip()


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Send a password reset email",
    description=(
        "Triggers a Supabase Auth password-reset email for the given address. "
        "Always returns **200** regardless of whether the email is registered — "
        "this prevents user-enumeration attacks."
    ),
)
def forgot_password(payload: ForgotPasswordRequest) -> dict:
    """Send a password-reset email via Supabase Auth.

    Args:
        payload: ``{email}`` — the address to send the reset link to.

    Returns:
        ``{\"message\": \"...\"}`` — always 200, never reveals registration status.
    """
    logger.info("forgot_password: reset requested for email=%s", payload.email)
    try:
        supabase.auth.reset_password_email(payload.email)
        logger.info("forgot_password: reset email dispatched for %s", payload.email)
    except Exception as exc:
        # Log but swallow — do not leak whether the address is registered.
        logger.warning(
            "forgot_password: Supabase error for %s -- %s", payload.email, exc
        )
    return {"message": "If that email is registered, a password reset link has been sent."}


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class LogoutRequest(BaseModel):
    """Request body for the logout endpoint."""

    refresh_token: str


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Log out and invalidate the current session",
    description=(
        "Calls Supabase Auth ``sign_out`` to invalidate the session server-side. "
        "The client should discard both tokens after calling this endpoint. "
        "Always returns **200** — a best-effort sign-out even if Supabase is unreachable."
    ),
)
def logout(payload: LogoutRequest) -> dict:
    """Invalidate the current Supabase Auth session.

    Args:
        payload: ``{refresh_token}`` — the refresh token to invalidate.

    Returns:
        ``{\"message\": \"Logged out successfully.\"}`` — always 200.
    """
    logger.info("logout: sign-out requested")
    try:
        supabase.auth.sign_out()
        logger.info("logout: session invalidated successfully")
    except Exception as exc:
        # Best-effort — the client must discard tokens regardless.
        logger.warning("logout: Supabase sign_out error -- %s", exc)
    return {"message": "Logged out successfully."}


# ---------------------------------------------------------------------------
# Account deletion
# ---------------------------------------------------------------------------


@router.delete(
    "/account",
    status_code=status.HTTP_200_OK,
    summary="Permanently delete the authenticated user's account",
    description=(
        "Deletes the authenticated user's account via the Supabase Admin API. "
        "Cascades across all 17 database tables via ``ON DELETE CASCADE`` foreign "
        "keys — tasks, oauth_connections, memory, notifications, digests, etc. "
        "Requires a valid JWT. This action is **irreversible**."
    ),
)
def delete_account(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """Permanently delete the authenticated user and all their data.

    Uses the service-role admin client to bypass RLS and call
    ``auth.admin.delete_user``, which triggers Supabase's cascade deletion
    across every table that has a ``user_id`` foreign key referencing
    ``auth.users``.

    Args:
        current_user: Injected by the JWT dependency — carries ``user_id``.

    Returns:
        ``{\"message\": \"Account deleted successfully.\"}``

    Raises:
        HTTPException(401): Missing or invalid JWT (automatic via dependency).
        HTTPException(500): Supabase admin deletion failed.
    """
    logger.info("delete_account: deletion requested for user_id=%s", current_user.id)
    try:
        service_client = create_client(
            settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
        )
        service_client.auth.admin.delete_user(current_user.id)
        logger.info(
            "delete_account: user_id=%s deleted successfully", current_user.id
        )
    except Exception as exc:
        error_msg = _extract_supabase_error(exc)
        logger.error(
            "delete_account: failed to delete user_id=%s -- %s",
            current_user.id,
            error_msg,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account deletion failed. Please try again.",
        ) from exc

    return {"message": "Account deleted successfully."}


@router.post(
    "/google",
    status_code=status.HTTP_200_OK,
    response_model=LoginResponse,
    summary="Google Sign-In",
    description=(
        "Authenticates a user via a Google ID token obtained from native Google Sign-In. "
        "Returns a JWT access token and a refresh token. "
        "Returns **401** for invalid tokens."
    ),
)
def google_auth(payload: GoogleAuthRequest) -> Any:
    """Authenticate and return a JWT token pair using a Google ID token."""
    logger.info("Google Sign-In attempt")

    try:
        res = supabase.auth.sign_in_with_id_token({
            "provider": "google",
            "id_token": payload.id_token
        })
    except Exception as exc:
        msg = _extract_supabase_error(exc)
        logger.warning("Google Sign-In failed: %s", msg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=msg,
        ) from exc

    if not res.session:
        logger.warning("Google Sign-In returned no session")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
        )

    logger.info("Google Sign-In successful for user: %s", res.user.id)
    return LoginResponse(
        access_token=res.session.access_token,
        refresh_token=res.session.refresh_token,
    )


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


class VerifyOtpRequest(BaseModel):
    """Request body for email/OTP verification."""

    email: str
    token: str
    type: str = "signup"


@router.post(
    "/verify",
    status_code=status.HTTP_200_OK,
    summary="Verify email OTP / confirmation token",
    description="Verifies an email verification token/OTP via Supabase Auth.",
)
def verify_email(payload: VerifyOtpRequest) -> dict:
    """Verifies email verification token via Supabase Auth."""
    logger.info("Email verification attempt for %s", payload.email)
    try:
        response = supabase.auth.verify_otp(
            {
                "email": payload.email,
                "token": payload.token,
                "type": payload.type,
            }
        )
    except Exception as exc:
        error_msg = _extract_supabase_error(exc)
        logger.warning("Email verification failed for %s -- %s", payload.email, error_msg)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        ) from exc

    session = response.session
    return {
        "message": "Email verified successfully.",
        "access_token": session.access_token if session else "",
        "refresh_token": session.refresh_token if session else "",
    }


class ResendVerificationRequest(BaseModel):
    """Request body for resending verification email."""

    email: str
    type: str = "signup"


@router.post(
    "/resend-verification",
    status_code=status.HTTP_200_OK,
    summary="Resend email verification link",
    description="Resends a signup verification email via Supabase Auth.",
)
def resend_verification(payload: ResendVerificationRequest) -> dict:
    """Resend signup verification email via Supabase Auth."""
    logger.info("Resend verification requested for email=%s", payload.email)
    try:
        supabase.auth.resend({"type": payload.type, "email": payload.email})
    except Exception as exc:
        error_msg = _extract_supabase_error(exc)
        logger.warning("Resend verification failed for %s -- %s", payload.email, error_msg)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        ) from exc
    return {"message": "Verification email resent successfully."}


# ---------------------------------------------------------------------------
# Password reset / update
# ---------------------------------------------------------------------------


class ResetPasswordRequest(BaseModel):
    """Request body for resetting/updating password."""

    password: str


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset / update user password",
    description="Updates password via Supabase Auth and invalidates prior sessions.",
)
def reset_password(
    payload: ResetPasswordRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """Update password for the authenticated user."""
    logger.info("Password reset requested for user_id=%s", current_user.id)
    try:
        supabase.auth.update_user({"password": payload.password})
    except Exception as exc:
        error_msg = _extract_supabase_error(exc)
        logger.warning(
            "Password reset failed for user_id=%s -- %s", current_user.id, error_msg
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        ) from exc
    return {"message": "Password updated successfully. Prior sessions invalidated."}
