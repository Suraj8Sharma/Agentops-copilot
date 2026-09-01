"""OAuth consent-flow router — D7.

Endpoint
--------
GET /oauth/{provider}/connect

    Starts the OAuth consent flow for the signed-in user by building a
    Google authorization URL and returning it as JSON.  The Flutter client
    opens this URL in an external browser / custom tab.

    - Auth:     JWT required (``get_current_user`` dependency).
    - Scopes:   Calendar events + Gmail send + Gmail compose.
    - State:    HMAC-SHA256 signed token binding ``user_id`` and ``provider``
                for CSRF protection.  The callback (D8) will verify this.
    - Returns:  ``{"authorization_url": "https://accounts.google.com/..."}``

Out of scope here
-----------------
- Code exchange / token storage        → D8 (callback endpoint)
- GitHub / Slack providers             → D10
- Token revocation                     → later

Security notes
--------------
- ``client_secret`` is never read or logged in this module.
- The full authorization URL is never logged (it contains ``client_id``
  and the signed ``state``).
- ``GOOGLE_OAUTH_CLIENT_ID`` being empty at request time → 500, loud.
"""

import hashlib
import hmac
import logging
import secrets
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GOOGLE_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"

# Full scope string per spec §5
_GOOGLE_SCOPES = " ".join([
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
])

# Only provider supported until D10
_SUPPORTED_PROVIDERS = frozenset({"google"})

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/oauth", tags=["oauth"])


# ---------------------------------------------------------------------------
# State-token helpers (CSRF protection)
# ---------------------------------------------------------------------------

def _build_state_token(user_id: str, provider: str) -> str:
    """Create a signed, unguessable state token for CSRF protection.

    Format (URL-safe):
        ``{payload}.{signature}``

    Where:
        - ``payload``   = ``{user_id}:{provider}:{nonce}``
          (nonce is 32 random bytes encoded as hex)
        - ``signature`` = first 32 hex chars of
          HMAC-SHA256(SUPABASE_JWT_SECRET, payload)

    The callback endpoint (D8) will call a corresponding verify function.

    Args:
        user_id:  The authenticated user's Supabase UUID.
        provider: The OAuth provider string (e.g. ``"google"``).

    Returns:
        A dot-separated ``payload.signature`` string safe for use as a URL
        query parameter value.
    """
    nonce = secrets.token_hex(32)
    payload = f"{user_id}:{provider}:{nonce}"
    secret = settings.SUPABASE_JWT_SECRET.encode()
    signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{signature}"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{provider}/connect",
    summary="Start OAuth consent flow",
    description=(
        "Builds a Google OAuth authorization URL for the signed-in user "
        "and returns it as JSON.  The Flutter client opens this URL in an "
        "external browser or custom tab.  Requires a valid JWT.\n\n"
        "For D7, only ``provider=google`` is supported "
        "(GitHub / Slack arrive in D10)."
    ),
    status_code=status.HTTP_200_OK,
)
def oauth_connect(
    provider: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """Return the authorization URL to start the OAuth consent flow.

    Args:
        provider:     Path param — OAuth provider name.  Only ``"google"``
                      is valid for D7; others return 404.
        current_user: Injected by the JWT dependency — carries ``user_id``.

    Returns:
        ``{"authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?..."}``

    Raises:
        HTTPException(401): Missing or invalid JWT (automatic via dependency).
        HTTPException(404): Unsupported provider.
        HTTPException(500): Required config (``GOOGLE_OAUTH_CLIENT_ID`` or
                            ``GOOGLE_OAUTH_REDIRECT_URI``) is missing.
    """
    # ---- 1. Validate provider -----------------------------------------------
    if provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown OAuth provider: {provider!r}. Supported: google.",
        )

    # ---- 2. Guard: required config must be present --------------------------
    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        logger.error(
            "GOOGLE_OAUTH_CLIENT_ID is not configured — cannot build "
            "authorization URL for user_id=%s",
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth is not configured on this server.",
        )

    if not settings.GOOGLE_OAUTH_REDIRECT_URI:
        logger.error(
            "GOOGLE_OAUTH_REDIRECT_URI is not configured — cannot build "
            "authorization URL for user_id=%s",
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth redirect URI is not configured on this server.",
        )

    # ---- 3. Build signed state token (CSRF protection) ----------------------
    state = _build_state_token(user_id=current_user.id, provider=provider)

    # ---- 4. Build the Google authorization URL ------------------------------
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": _GOOGLE_SCOPES,
        "access_type": "offline",   # required to receive a refresh token
        "prompt": "consent",         # re-issues refresh token on repeat consent
        "state": state,
    }
    authorization_url = f"{_GOOGLE_AUTH_BASE}?{urlencode(params)}"

    # NOTE: Do NOT log authorization_url — it contains client_id and state.
    logger.info(
        "Built OAuth authorization URL for user_id=%s provider=%s",
        current_user.id,
        provider,
    )

    return {"authorization_url": authorization_url}
