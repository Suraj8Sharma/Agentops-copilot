"""Security dependency — JWT verification for protected routes.

All protected routes declare ``Depends(get_current_user)`` which:
1. Extracts the Bearer token from the ``Authorization`` header.
2. Calls ``supabase.auth.get_user(token)`` to verify the token against
   Supabase Auth (handles HS256 signature, expiry, and revocation).
3. Returns a ``CurrentUser`` object for downstream route handlers.

Error semantics
---------------
- Missing token          → 401, detail = ``"not_authenticated"``
- Expired access token   → 401, detail = ``"token_expired"``  +
                           ``X-Token-Expired: true`` header so the client
                           knows to use the refresh token, not prompt login.
- Invalid / tampered     → 401, detail = ``"invalid_token"``

No token values are ever written to logs.
"""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP Bearer scheme — reads the token from the Authorization header.
# auto_error=False so we can return a custom 401 instead of FastAPI's default.
# ---------------------------------------------------------------------------
security_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Current-user model — returned by the dependency to route handlers
# ---------------------------------------------------------------------------


class CurrentUser(BaseModel):
    """Authenticated user extracted from a valid Supabase JWT."""

    id: str
    """Supabase user UUID (``auth.users.id``)."""

    email: str
    """User email address."""

    role: str = "authenticated"
    """Supabase role claim — always ``"authenticated"`` for regular users."""


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
) -> CurrentUser:
    """FastAPI dependency: verify the JWT and return the current user.

    Usage in a route::

        @router.get("/me")
        def me(user: CurrentUser = Depends(get_current_user)):
            return {"user_id": user.id}

    Or at router level (protects every route in the router)::

        router = APIRouter(dependencies=[Depends(get_current_user)])

    Raises:
        HTTPException(401): Token is missing, expired, or invalid.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not_authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    token = credentials.credentials

    try:
        response = supabase.auth.get_user(token)
        user = response.user

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.debug("Authenticated request from user_id=%s", user.id)
        return CurrentUser(
            id=str(user.id),
            email=user.email or "",
            role=user.role or "authenticated",
        )

    except HTTPException:
        # Re-raise HTTPExceptions from the block above as-is.
        raise

    except Exception as exc:
        error_msg = str(exc).lower()
        # No token value in logs — only the error class name.
        logger.warning(
            "Token verification failed [%s]", type(exc).__name__
        )

        if "expired" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token_expired",
                headers={
                    "WWW-Authenticate": "Bearer",
                    "X-Token-Expired": "true",
                },
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc