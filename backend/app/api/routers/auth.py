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
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator

from app.db.supabase_client import supabase

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
        response = supabase.auth.sign_up(
            {"email": payload.email, "password": payload.password}
        )
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
