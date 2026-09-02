"""OAuth router — D7 / D8 / D9.

Endpoints
---------
GET /oauth/{provider}/connect            (D7)

    Starts the OAuth consent flow for the signed-in user by building a
    Google authorization URL and returning it as JSON.  The Flutter client
    opens this URL in an external browser / custom tab.

    - Auth:     JWT required (``get_current_user`` dependency).
    - Scopes:   Calendar events + Gmail send + Gmail compose.
    - State:    HMAC-SHA256 signed token binding ``user_id`` and ``provider``
                for CSRF protection.  The callback (D8) will verify this.
    - Returns:  ``{"authorization_url": "https://accounts.google.com/..."}``

GET /oauth/{provider}/callback           (D8)

    Receives the authorization code from Google, verifies the CSRF state,
    exchanges the code for tokens, and stores them encrypted in the database.

POST /oauth/internal/sweep-tokens        (D9)

    Internal cron endpoint — NOT user-facing.  Scans ``oauth_connections``
    for Google tokens approaching the 7-day Testing-mode hard expiry and
    flags them as ``expired_testing_mode`` so the app can warn the user to
    reconnect before things silently break.

    - Auth:     ``Authorization: Bearer <CRON_SECRET>`` header (static secret).
    - Returns:  ``{flagged: int, scanned: int}``

Out of scope here
-----------------
- GitHub / Slack providers             → D10
- Token revocation endpoint            → later
- Sending push notifications           → D24

Security notes
--------------
- ``client_secret`` is never read or logged in this module.
- The full authorization URL is never logged (it contains ``client_id``
  and the signed ``state``).
- ``GOOGLE_OAUTH_CLIENT_ID`` being empty at request time → 500, loud.
- The sweep endpoint checks ``CRON_SECRET``; an empty secret means the
  guard is effectively disabled — always set this in production/staging.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from supabase import create_client

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GOOGLE_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"

# Full scope string per spec §5
_GOOGLE_SCOPES = " ".join(
    [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
    ]
)

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


def _verify_state_token(state: str, user_id: str, provider: str) -> bool:
    """Verify the signed state token for CSRF protection.

    Args:
        state:    The state token passed back from Google.
        user_id:  The authenticated user's Supabase UUID.
        provider: The OAuth provider string (e.g. ``"google"``).

    Returns:
        True if the state is valid and belongs to this user/provider.
    """
    if not state or "." not in state:
        return False

    payload, provided_signature = state.rsplit(".", 1)

    # Payload format: user_id:provider:nonce
    parts = payload.split(":")
    if len(parts) != 3:
        return False

    token_user_id, token_provider, _ = parts
    if token_user_id != user_id or token_provider != provider:
        return False

    secret = settings.SUPABASE_JWT_SECRET.encode()
    expected_signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:32]

    # Use hmac.compare_digest to prevent timing attacks
    return hmac.compare_digest(provided_signature, expected_signature)


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
        "access_type": "offline",  # required to receive a refresh token
        "prompt": "consent",  # re-issues refresh token on repeat consent
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


@router.get(
    "/{provider}/callback",
    summary="OAuth Callback",
    description=(
        "Receives the authorization code from Google, verifies the CSRF state, "
        "exchanges the code for tokens, and stores them encrypted in the database."
    ),
    status_code=status.HTTP_200_OK,
)
def oauth_callback(
    provider: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    state: str = Query(..., description="CSRF state token"),
    code: Optional[str] = Query(None, description="Authorization code from provider"),
    error: Optional[str] = Query(None, description="Error if user denied consent"),
    scope: Optional[str] = Query(None, description="Granted scopes"),
) -> dict:
    """Exchange OAuth authorization code for tokens and store them."""

    if provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown OAuth provider: {provider!r}. Supported: google.",
        )

    if error:
        logger.warning(
            "User denied consent during OAuth flow: user_id=%s, error=%s", current_user.id, error
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"OAuth authorization failed: {error}"
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Authorization code is missing."
        )

    if not _verify_state_token(state, user_id=current_user.id, provider=provider):
        logger.warning("Invalid OAuth state token during callback: user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state token. Possible CSRF attempt.",
        )

    # Step 3 - Exchange code for token
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    try:
        with httpx.Client() as client:
            response = client.post(token_url, data=data)
            response.raise_for_status()
            token_data = response.json()
    except httpx.HTTPError as exc:
        logger.error("Failed to exchange OAuth code: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to exchange authorization code with Google.",
        )

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3599)
    # token_data.get("scope") is typically a space-separated string
    granted_scopes = token_data.get("scope", "").split()

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Google did not return an access token."
        )

    # Step 4 - Encrypt tokens
    if not settings.ENCRYPTION_KEY:
        logger.error("ENCRYPTION_KEY is missing from config.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: missing encryption key.",
        )

    try:
        fernet = Fernet(settings.ENCRYPTION_KEY.encode())
        encrypted_access = fernet.encrypt(access_token.encode()).decode()
        encrypted_refresh = (
            fernet.encrypt(refresh_token.encode()).decode() if refresh_token else None
        )
    except Exception as exc:
        logger.error("Failed to encrypt tokens: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt OAuth tokens.",
        )

    # Step 5 - Store encrypted tokens in database
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

    # Write two rows for Google (one for calendar, one for gmail) as per the spec
    records = [
        {
            "user_id": current_user.id,
            "provider": p,
            "access_token": encrypted_access,
            "refresh_token": encrypted_refresh,
            "expires_at": expires_at,
            "scopes": granted_scopes,
            "status": "active",
        }
        for p in ("google_calendar", "gmail")
    ]

    try:
        # The global `supabase` client gets its auth state mutated by `get_current_user`
        # (which downgrades it to the user's role). We MUST use a fresh service-role
        # client here to bypass RLS for this backend-only insert.
        service_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

        service_client.table("oauth_connections").upsert(
            records, on_conflict="user_id,provider"
        ).execute()
    except Exception as exc:
        logger.error("Failed to store OAuth tokens in database: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save OAuth connection: {exc}",
        )

    return {"message": "OAuth connection successful"}


# ---------------------------------------------------------------------------
# D9 — Internal sweep endpoint (cron / scheduler use only)
# ---------------------------------------------------------------------------

# How long before the 7-day hard limit we proactively flag the connection.
# 6 days 12 hours = 6.5 days, giving the user a ~12-hour window to reconnect.
_TESTING_MODE_EXPIRY_DAYS = 7
_SWEEP_FLAG_THRESHOLD = timedelta(days=6, hours=12)

# Providers that are subject to Google's 7-day Testing-mode limit.
_GOOGLE_PROVIDERS = frozenset({"google_calendar", "gmail"})


class SweepResult(dict):
    """Intentionally a plain dict sub-class so FastAPI serialises it as JSON."""


@router.post(
    "/internal/sweep-tokens",
    summary="[Internal] Sweep Google OAuth tokens for 7-day Testing-mode expiry",
    description=(
        "**Not user-facing.** Scans all active Google OAuth connections and flags "
        "any that have been connected for more than 6 days 12 hours as "
        "``expired_testing_mode``. This gives users a heads-up to reconnect "
        "before Google's 7-day Testing-mode hard expiry silently breaks things.\n\n"
        "Secured by a static ``Authorization: Bearer <CRON_SECRET>`` header. "
        "Call this from an external cron scheduler (e.g. cron-job.org) once or "
        "twice a day."
    ),
    status_code=status.HTTP_200_OK,
    include_in_schema=False,  # Hide from public Swagger UI
)
def sweep_tokens(
    authorization: Annotated[str, Header()] = "",
) -> dict:
    """Sweep Google OAuth connections for imminent 7-day Testing-mode expiry.

    Meant to be called by an external cron scheduler, not by users.

    Args:
        authorization: The raw ``Authorization`` header value (injected by
                       FastAPI from the request headers).

    Returns:
        ``{"scanned": int, "flagged": int}`` — number of connections examined
        and number newly flagged as ``expired_testing_mode``.

    Raises:
        HTTPException(401): Missing or incorrect ``CRON_SECRET``.
        HTTPException(503): Database query failed.
    """
    # ------------------------------------------------------------------
    # 1. Auth guard — reject anyone without the correct CRON_SECRET
    # ------------------------------------------------------------------
    expected = settings.CRON_SECRET
    if not expected:
        # If CRON_SECRET is not configured, the endpoint is effectively open.
        # Log loudly so it's visible in monitoring, but don't block in dev.
        logger.warning(
            "sweep-tokens called but CRON_SECRET is not configured — "
            "endpoint is unprotected. Set CRON_SECRET in production."
        )
    else:
        # Expect: "Bearer <token>"
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token, expected):
            logger.warning("sweep-tokens rejected: bad or missing CRON_SECRET")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing Authorization token.",
            )

    # ------------------------------------------------------------------
    # 2. Query all active Google connections (service-role to bypass RLS)
    # ------------------------------------------------------------------
    try:
        service_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        result = (
            service_client.table("oauth_connections")
            .select("id, user_id, provider, connected_at, status")
            .in_("provider", list(_GOOGLE_PROVIDERS))
            .eq("status", "active")
            .execute()
        )
        rows = result.data or []
    except Exception as exc:
        logger.error("sweep-tokens: failed to query oauth_connections: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to query database. Will retry on next scheduled run.",
        )

    # ------------------------------------------------------------------
    # 3. Flag any connections older than the threshold
    # ------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    scanned = len(rows)
    flagged = 0
    flagged_ids: list[str] = []

    for row in rows:
        connected_at_raw = row.get("connected_at")
        if not connected_at_raw:
            continue

        # Parse ISO timestamp from Supabase (may or may not include timezone)
        try:
            connected_at = datetime.fromisoformat(connected_at_raw)
            # Ensure it's timezone-aware
            if connected_at.tzinfo is None:
                connected_at = connected_at.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning(
                "sweep-tokens: unparseable connected_at=%r for row id=%s — skipping",
                connected_at_raw,
                row.get("id"),
            )
            continue

        token_age = now - connected_at
        if token_age >= _SWEEP_FLAG_THRESHOLD:
            flagged_ids.append(row["id"])
            flagged += 1
            logger.info(
                "sweep-tokens: flagging connection id=%s user_id=%s provider=%s "
                "(age=%s, threshold=%s)",
                row["id"],
                row["user_id"],
                row["provider"],
                token_age,
                _SWEEP_FLAG_THRESHOLD,
            )

    # ------------------------------------------------------------------
    # 4. Bulk-update flagged rows to expired_testing_mode
    # ------------------------------------------------------------------
    if flagged_ids:
        try:
            service_client.table("oauth_connections").update(
                {"status": "expired_testing_mode"}
            ).in_("id", flagged_ids).execute()
        except Exception as exc:
            logger.error(
                "sweep-tokens: failed to update %d rows to expired_testing_mode: %s",
                len(flagged_ids),
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to update database. Will retry on next scheduled run.",
            )

    logger.info("sweep-tokens complete: scanned=%d flagged=%d", scanned, flagged)
    return {"scanned": scanned, "flagged": flagged}
