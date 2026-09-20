"""OAuth router — D7 / D8 / D9 / D10.

Endpoints
---------
GET /oauth/{provider}/connect            (D7 / D10)

    Starts the OAuth consent flow for the signed-in user by building a
    provider authorization URL and returning it as JSON.  The Flutter client
    opens this URL in an external browser / custom tab.

    - Auth:     JWT required (``get_current_user`` dependency).
    - Providers: google, github, slack.
    - State:    HMAC-SHA256 signed token binding ``user_id`` and ``provider``
                for CSRF protection.  The callback (D8) will verify this.
    - Returns:  ``{"authorization_url": "https://<provider>.com/..."}``

GET /oauth/{provider}/callback           (D8)

    Receives the authorization code from the provider, verifies the CSRF state,
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
- Token revocation endpoint            → later
- Sending push notifications           → D24

Security notes
--------------
- ``client_secret`` is never read or logged in this module.
- The full authorization URL is never logged (it contains ``client_id``
  and the signed ``state``).
- A missing ``client_id`` at request time → 500, loud.
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
# Provider configuration
# ---------------------------------------------------------------------------
# Each entry contains everything needed to build an authorization URL for
# that provider.  No token-exchange logic lives here — that's a separate task.
#
# Keys:
#   authorize_url       — OAuth consent-screen endpoint.
#   token_url           — Token-exchange endpoint (used in callback, not here).
#   scopes              — List of OAuth scope strings to request.
#   scope_delimiter     — Character used to join scopes into a single string.
#                         Google/GitHub use " " (space); Slack uses "," (comma).
#   redirect_uri        — Must exactly match the URI registered in the provider's
#                         OAuth app dashboard.
#   client_id_env       — Name of the settings attribute holding the client ID.
#   client_secret_env   — Name of the settings attribute holding the client secret.
#   token_exchange_headers — Extra HTTP headers for the token-exchange POST.
#                            Empty dict for providers that need none.
# ---------------------------------------------------------------------------

PROVIDER_CONFIG: dict[str, dict] = {
    # -- Google (calendar + gmail) ------------------------------------------
    # Google requires access_type=offline and prompt=consent (added in the
    # connect handler because they're Google-specific behaviour flags, not
    # generic OAuth params).
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.compose",
        ],
        "scope_delimiter": " ",
        "redirect_uri": "http://localhost:8000/oauth/google/callback",
        "client_id_env": "GOOGLE_OAUTH_CLIENT_ID",
        "client_secret_env": "GOOGLE_OAUTH_CLIENT_SECRET",
        "token_exchange_headers": {},
    },
    # -- GitHub ---------------------------------------------------------------
    # Scope "repo" is intentionally broad: GitHub's classic OAuth has no
    # narrower scope that grants read/write access to *private* repositories.
    # "public_repo" cannot access private repos at all, so it is not used here.
    # The consent screen will note that this grants access to all repositories —
    # that is expected behaviour with this scope, not a misconfiguration.
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": ["repo"],
        "scope_delimiter": " ",
        "redirect_uri": "http://localhost:8000/oauth/github/callback",
        "client_id_env": "GITHUB_OAUTH_CLIENT_ID",
        "client_secret_env": "GITHUB_OAUTH_CLIENT_SECRET",
        # GitHub returns form-encoded by default; Accept: application/json
        # makes it return a JSON body instead, which is easier to parse.
        "token_exchange_headers": {"Accept": "application/json"},
    },
    # -- Slack ----------------------------------------------------------------
    # Slack v2 uses a comma-separated scope string (unlike Google/GitHub which
    # use spaces).  This is a confirmed difference in the Slack OAuth v2 spec.
    "slack": {
        "authorize_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes": ["chat:write", "channels:read", "reactions:write"],
        "scope_delimiter": ",",
        "redirect_uri": "http://localhost:8000/oauth/slack/callback",
        "client_id_env": "SLACK_CLIENT_ID",
        "client_secret_env": "SLACK_CLIENT_SECRET",
        "token_exchange_headers": {},
    },
}

# Derived from PROVIDER_CONFIG so there's a single source of truth.
_SUPPORTED_PROVIDERS: frozenset[str] = frozenset(PROVIDER_CONFIG)

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


def _verify_and_extract_user_id(state: str, provider: str) -> str:
    """Verify the signed state token for CSRF protection and extract the user_id.

    Args:
        state:    The state token passed back from Google.
        provider: The OAuth provider string (e.g. ``"google"``).

    Returns:
        The authenticated user's Supabase UUID.
        
    Raises:
        ValueError: If the state token is invalid, tampered with, or for the wrong provider.
    """
    if not state or "." not in state:
        raise ValueError("Malformed state token")

    payload, provided_signature = state.rsplit(".", 1)

    # Payload format: user_id:provider:nonce
    parts = payload.split(":")
    if len(parts) != 3:
        raise ValueError("Malformed state payload")

    token_user_id, token_provider, _ = parts
    if token_provider != provider:
        raise ValueError("Provider mismatch")

    secret = settings.SUPABASE_JWT_SECRET.encode()
    expected_signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:32]

    # Use hmac.compare_digest to prevent timing attacks
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise ValueError("Invalid signature")
        
    return token_user_id


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{provider}/connect",
    summary="Start OAuth consent flow",
    description=(
        "Builds a provider OAuth authorization URL for the signed-in user "
        "and returns it as JSON.  The Flutter client opens this URL in an "
        "external browser or custom tab.  Requires a valid JWT.\n\n"
        "Supported providers: ``google``, ``github``, ``slack``."
    ),
    status_code=status.HTTP_200_OK,
)
def oauth_connect(
    provider: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """Return the authorization URL to start the OAuth consent flow.

    Args:
        provider:     Path param — OAuth provider name.
                      Valid values: ``"google"``, ``"github"``, ``"slack"``.
        current_user: Injected by the JWT dependency — carries ``user_id``.

    Returns:
        ``{"authorization_url": "https://<provider-auth-endpoint>?..."}``

    Raises:
        HTTPException(401): Missing or invalid JWT (automatic via dependency).
        HTTPException(404): Unsupported provider.
        HTTPException(500): Required client_id config for the provider is missing.
    """
    # ---- 1. Validate provider -----------------------------------------------
    if provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Unknown OAuth provider: {provider!r}. "
                f"Supported: {', '.join(sorted(_SUPPORTED_PROVIDERS))}."
            ),
        )

    cfg = PROVIDER_CONFIG[provider]

    # ---- 2. Guard: client_id must be present in settings --------------------
    client_id = getattr(settings, cfg["client_id_env"], "")
    if not client_id:
        logger.error(
            "%s is not configured — cannot build authorization URL for user_id=%s",
            cfg["client_id_env"],
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth is not configured on this server.",
        )

    # ---- 3. Build signed state token (CSRF protection) ----------------------
    state = _build_state_token(user_id=current_user.id, provider=provider)

    # ---- 4. Build the authorization URL -------------------------------------
    # scope_delimiter differs per provider:
    #   Google / GitHub → " " (space)
    #   Slack           → "," (comma)
    scope_string = cfg["scope_delimiter"].join(cfg["scopes"])

    params: dict = {
        "client_id": client_id,
        "redirect_uri": cfg["redirect_uri"],  # hardcoded from config, not from request
        "response_type": "code",
        "scope": scope_string,
        "state": state,
    }

    # Google-specific extras — not part of the base OAuth 2.0 spec
    if provider == "google":
        params["access_type"] = "offline"  # required to receive a refresh token
        params["prompt"] = "consent"  # re-issues refresh token on repeat consent

    authorization_url = f"{cfg['authorize_url']}?{urlencode(params)}"

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
        "Receives the authorization code from the provider, verifies the CSRF state, "
        "exchanges the code for tokens, and stores them encrypted in the database."
    ),
    status_code=status.HTTP_200_OK,
)
def oauth_callback(
    provider: str,
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

    try:
        user_id = _verify_and_extract_user_id(state, provider)
    except ValueError as e:
        logger.warning("Invalid OAuth state token during callback: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state token. Possible CSRF attempt.",
        )

    if error:
        logger.warning(
            "User denied consent during OAuth flow: user_id=%s, error=%s", user_id, error
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"OAuth authorization failed: {error}"
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Authorization code is missing."
        )

    # -------------------------------------------------------------------------
    # Step 3 — Exchange code for token (provider-agnostic)
    # -------------------------------------------------------------------------
    cfg = PROVIDER_CONFIG[provider]

    client_id = getattr(settings, cfg["client_id_env"], "")
    client_secret = getattr(settings, cfg["client_secret_env"], "")

    if not client_id or not client_secret:
        logger.error(
            "OAuth credentials not configured for provider=%s (user_id=%s)",
            provider,
            user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth is not configured on this server.",
        )

    token_url = cfg["token_url"]
    exchange_headers = cfg.get("token_exchange_headers", {})

    exchange_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": cfg["redirect_uri"],
        "grant_type": "authorization_code",
    }

    try:
        with httpx.Client() as client:
            response = client.post(token_url, data=exchange_data, headers=exchange_headers)
            # NOTE: do NOT call raise_for_status() here globally.
            # GitHub and Slack both return HTTP 200 on failed exchanges,
            # so we check the body ourselves for every provider below.
    except httpx.HTTPError as exc:
        logger.error(
            "Network error during token exchange for provider=%s user_id=%s: %s",
            provider,
            user_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reach {provider} token endpoint.",
        )

    # -------------------------------------------------------------------------
    # Parse response body — attempt JSON first, then fall back to form-encoded.
    # GitHub returns form-encoded without Accept: application/json, but
    # PROVIDER_CONFIG already sets that header for GitHub so JSON is the
    # expected path. The fallback is a defensive measure.
    # -------------------------------------------------------------------------
    from urllib.parse import parse_qs  # noqa: PLC0415 (local import is fine here)

    token_data: dict
    try:
        token_data = response.json()
    except Exception:
        parsed = parse_qs(response.text)
        token_data = {k: v[0] if v else "" for k, v in parsed.items()}

    # -------------------------------------------------------------------------
    # Provider-specific success/failure detection
    # -------------------------------------------------------------------------
    # Google: HTTP status already reflects outcome.
    if provider == "google":
        if response.status_code >= 400:
            logger.error(
                "Google token exchange failed: status=%d body=%r user_id=%s",
                response.status_code,
                token_data,
                user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to exchange authorization code with Google.",
            )

    # GitHub: returns HTTP 200 even on error; presence of "error" key = failure.
    elif provider == "github":
        if "error" in token_data:
            err_code = token_data.get("error", "unknown_error")
            err_desc = token_data.get("error_description", "No description provided.")
            logger.warning(
                "GitHub token exchange failed (expected — bad/expired/reused code): "
                "user_id=%s error=%r description=%r",
                user_id,
                err_code,
                err_desc,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"GitHub authorization failed ({err_code}): {err_desc} "
                    "Please start the connection flow again."
                ),
            )

    # Slack: returns HTTP 200 even on error; ok==False = failure.
    elif provider == "slack":
        if not token_data.get("ok", False):
            err_code = token_data.get("error", "unknown_error")
            logger.warning(
                "Slack token exchange failed (expected — bad/expired/reused code): "
                "user_id=%s error=%r",
                user_id,
                err_code,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Slack authorization failed ({err_code}). "
                    "Please start the connection flow again."
                ),
            )

    # -------------------------------------------------------------------------
    # Extract access_token from the now-validated response body
    # -------------------------------------------------------------------------
    access_token = token_data.get("access_token")
    if not access_token:
        # Slack: the top-level access_token is the bot token (preferred).
        # If absent, try authed_user.access_token as a defensive fallback.
        if provider == "slack":
            access_token = (token_data.get("authed_user") or {}).get("access_token")
        if not access_token:
            logger.error(
                "Provider=%s returned no access_token despite apparent success: "
                "user_id=%s body_keys=%r",
                provider,
                user_id,
                list(token_data.keys()),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{provider} did not return an access token.",
            )

    # -------------------------------------------------------------------------
    # Step 4 — Encrypt tokens
    # -------------------------------------------------------------------------
    if not settings.ENCRYPTION_KEY:
        logger.error("ENCRYPTION_KEY is missing from config.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: missing encryption key.",
        )

    try:
        fernet = Fernet(settings.ENCRYPTION_KEY.encode())
        encrypted_access = fernet.encrypt(access_token.encode()).decode()
    except Exception as exc:
        logger.error("Failed to encrypt tokens for provider=%s: %s", provider, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt OAuth tokens.",
        )

    # -------------------------------------------------------------------------
    # Step 5 — Build DB record(s) and upsert
    # -------------------------------------------------------------------------
    try:
        service_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    except Exception as exc:
        logger.error("Failed to create Supabase service client: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database client initialisation failed.",
        )

    if provider == "google":
        # Google issues a refresh token and an expiry.  Store two rows — one per
        # logical service (google_calendar and gmail) — as per the original spec.
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3599)
        granted_scopes = token_data.get("scope", "").split()  # space-separated

        try:
            encrypted_refresh = (
                fernet.encrypt(refresh_token.encode()).decode() if refresh_token else None
            )
        except Exception as exc:
            logger.error("Failed to encrypt Google refresh token: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to encrypt OAuth tokens.",
            )

        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        records = [
            {
                "user_id": user_id,
                "provider": p,
                "access_token": encrypted_access,
                "refresh_token": encrypted_refresh,
                "expires_at": expires_at,
                "scopes": granted_scopes,
                "status": "active",
            }
            for p in ("google_calendar", "gmail")
        ]

    elif provider == "github":
        # GitHub: no refresh token (token rotation disabled on OAuth App),
        # no expiry.  GitHub echoes scopes as a comma-separated string even
        # though the request used space-delimited — split on comma defensively.
        raw_scopes = token_data.get("scope", "")
        granted_scopes = [s.strip() for s in raw_scopes.split(",") if s.strip()]

        records = [
            {
                "user_id": user_id,
                "provider": "github",
                "access_token": encrypted_access,
                "refresh_token": None,
                "expires_at": None,
                "scopes": granted_scopes,
                "status": "active",
            }
        ]

    elif provider == "slack":
        # Slack bot tokens: no refresh token, tokens don't expire under normal
        # workspace-install operation.
        # Slack returns granted scopes in the "scope" field (comma-separated).
        raw_scopes = token_data.get("scope", "")
        granted_scopes = [s.strip() for s in raw_scopes.split(",") if s.strip()]

        records = [
            {
                "user_id": user_id,
                "provider": "slack",
                "access_token": encrypted_access,
                "refresh_token": None,
                "expires_at": None,
                "scopes": granted_scopes,
                "status": "active",
            }
        ]

    else:
        # Should be unreachable given _SUPPORTED_PROVIDERS guard at the top.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No storage logic defined for provider={provider!r}.",
        )

    try:
        service_client.table("oauth_connections").upsert(
            records, on_conflict="user_id,provider"
        ).execute()
    except Exception as exc:
        logger.error("Failed to store OAuth tokens in database: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save OAuth connection: {exc}",
        )

    logger.info(
        "OAuth connection stored successfully: user_id=%s provider=%s",
        user_id,
        provider,
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

@router.get(
    "/connections",
    summary="List user OAuth connections",
)
def get_connections(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    from app.db.supabase_client import create_client
    service_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    result = service_client.table("oauth_connections").select(
        "provider, status, scopes, expires_at, connected_at"
    ).eq("user_id", current_user.id).execute()
    return {"connections": result.data or []}

@router.delete(
    "/{provider}",
    summary="Disconnect OAuth provider",
)
def delete_connection(
    provider: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    from app.db.supabase_client import create_client
    service_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    service_client.table("oauth_connections").delete().eq(
        "user_id", current_user.id
    ).eq("provider", provider).execute()
    return {"message": "Disconnected"}
