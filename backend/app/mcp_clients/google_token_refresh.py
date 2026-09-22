"""Google OAuth access-token refresh helper.

Shared by calendar.py and gmail.py.  Never imported by the planner or risk
gate — only by the two MCP clients that need it.

Logic
-----
1. Fetch ``access_token``, ``refresh_token``, and ``expires_at`` from
   ``oauth_connections`` for the given (user_id, provider) pair.
2. Decrypt both tokens with Fernet.
3. If ``expires_at`` is more than ``_EXPIRY_BUFFER`` seconds in the future,
   return the existing access token immediately (no network round-trip).
4. Otherwise, POST to Google's token endpoint with ``grant_type=refresh_token``
   to exchange the refresh token for a new access token (and possibly a new
   refresh token).
5. Encrypt the new token(s) and upsert them back into ``oauth_connections``,
   updating ``expires_at`` so future calls know when to refresh again.
6. Return the fresh access token.

If the refresh fails (network error, revoked token, missing refresh_token),
``None`` is returned so the caller can surface a reconnect-required error.

Note: GitHub and Slack tokens are not handled here — GitHub OAuth App tokens
never expire and Slack bot tokens don't expire under normal workspace
operation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from cryptography.fernet import Fernet

from app.core.config import settings
from app.db.supabase_client import supabase_admin

logger = logging.getLogger(__name__)

# Google's token refresh endpoint
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Refresh the access token this many seconds before it actually expires,
# to avoid using a token that expires mid-request.
_EXPIRY_BUFFER = timedelta(seconds=300)  # 5 minutes

# HTTP timeout for the refresh call.
_TIMEOUT = 10.0


def _fernet() -> Fernet | None:
    if not settings.ENCRYPTION_KEY:
        return None
    try:
        return Fernet(settings.ENCRYPTION_KEY.encode())
    except Exception:
        return None


def _decrypt(fernet: Fernet | None, value: str) -> str:
    """Decrypt a Fernet-encrypted value, falling back to raw on failure."""
    if not fernet:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except Exception:
        # Dev/test tokens may be stored unencrypted.
        return value


def _encrypt(fernet: Fernet | None, value: str) -> str:
    if not fernet:
        return value
    return fernet.encrypt(value.encode()).decode()


def get_valid_google_token(user_id: str, provider: str) -> Optional[str]:
    """Return a valid (non-expired) Google OAuth access token for the user.

    Transparently refreshes the token if it is expired or about to expire.
    Returns ``None`` if:
    - No token row exists for this (user_id, provider) pair.
    - The refresh_token is missing and the access_token is expired.
    - The Google refresh endpoint returns an error (token revoked, etc.).

    Args:
        user_id:  Supabase UUID of the authenticated user.
        provider: ``"google_calendar"`` or ``"gmail"``.

    Returns:
        A valid plaintext Google OAuth access token, or ``None``.
    """
    # ------------------------------------------------------------------
    # 1. Fetch the DB row
    # ------------------------------------------------------------------
    try:
        result = (
            supabase_admin.table("oauth_connections")
            .select("access_token, refresh_token, expires_at")
            .eq("user_id", user_id)
            .eq("provider", provider)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.error(
            "google_token_refresh: DB fetch failed [user_id=%s provider=%s]",
            user_id,
            provider,
            exc_info=True,
        )
        return None

    if not result.data:
        logger.warning(
            "google_token_refresh: no token row found [user_id=%s provider=%s]",
            user_id,
            provider,
        )
        return None

    row = result.data[0]
    encrypted_access = row.get("access_token") or ""
    encrypted_refresh = row.get("refresh_token") or ""
    expires_at_raw: str | None = row.get("expires_at")

    if not encrypted_access:
        logger.warning(
            "google_token_refresh: empty access_token in DB [user_id=%s provider=%s]",
            user_id,
            provider,
        )
        return None

    fernet = _fernet()

    # ------------------------------------------------------------------
    # 2. Decrypt
    # ------------------------------------------------------------------
    access_token = _decrypt(fernet, encrypted_access)
    refresh_token = _decrypt(fernet, encrypted_refresh) if encrypted_refresh else None

    # ------------------------------------------------------------------
    # 3. Check expiry — return early if still valid
    # ------------------------------------------------------------------
    if expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) + _EXPIRY_BUFFER < expires_at:
                # Token is fresh — no refresh needed.
                return access_token
        except ValueError:
            # Unparseable timestamp — fall through and attempt refresh.
            logger.warning(
                "google_token_refresh: unparseable expires_at=%r [user_id=%s] — attempting refresh",
                expires_at_raw,
                user_id,
            )
    else:
        # No expiry stored — assume still valid (legacy rows).
        return access_token

    # ------------------------------------------------------------------
    # 4. Token is expired (or approaching expiry) — attempt refresh
    # ------------------------------------------------------------------
    if not refresh_token:
        logger.warning(
            "google_token_refresh: token expired but no refresh_token stored "
            "[user_id=%s provider=%s] — user must reconnect",
            user_id,
            provider,
        )
        return None

    logger.info(
        "google_token_refresh: refreshing expired token [user_id=%s provider=%s]",
        user_id,
        provider,
    )

    try:
        response = httpx.post(
            _GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=_TIMEOUT,
        )
    except httpx.RequestError as exc:
        logger.error(
            "google_token_refresh: network error during refresh [user_id=%s]: %s",
            user_id,
            exc,
        )
        return None

    if not response.is_success:
        try:
            err_body = response.json()
        except Exception:
            err_body = {}
        logger.warning(
            "google_token_refresh: refresh failed [user_id=%s provider=%s status=%d error=%r]",
            user_id,
            provider,
            response.status_code,
            err_body.get("error"),
        )
        # Mark the connection as expired so the app warns the user.
        _mark_expired(user_id, provider)
        return None

    token_data = response.json()
    new_access_token: str = token_data.get("access_token", "")
    if not new_access_token:
        logger.error(
            "google_token_refresh: refresh response missing access_token [user_id=%s]",
            user_id,
        )
        return None

    expires_in: int = token_data.get("expires_in", 3599)
    new_expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()

    # Google may issue a new refresh token (rare but possible).
    new_refresh_token: str | None = token_data.get("refresh_token")

    # ------------------------------------------------------------------
    # 5. Persist the refreshed tokens back to DB
    # ------------------------------------------------------------------
    update_payload: dict = {
        "access_token": _encrypt(fernet, new_access_token),
        "expires_at": new_expires_at,
        "status": "active",
    }
    if new_refresh_token:
        update_payload["refresh_token"] = _encrypt(fernet, new_refresh_token)

    # Both google_calendar and gmail share the same access_token (one consent
    # gives both scopes), so we update both provider rows together.
    sibling = "gmail" if provider == "google_calendar" else "google_calendar"
    providers_to_update = [provider, sibling]

    try:
        supabase_admin.table("oauth_connections").update(update_payload).eq(
            "user_id", user_id
        ).in_("provider", providers_to_update).execute()
        logger.info(
            "google_token_refresh: token refreshed and persisted [user_id=%s providers=%s]",
            user_id,
            providers_to_update,
        )
    except Exception:
        logger.error(
            "google_token_refresh: failed to persist refreshed token [user_id=%s]",
            user_id,
            exc_info=True,
        )
        # Still return the new token even if persistence failed — the current
        # call can succeed; the next call will re-refresh.

    return new_access_token


def _mark_expired(user_id: str, provider: str) -> None:
    """Best-effort update of the connection status to 'expired' in the DB."""
    try:
        supabase_admin.table("oauth_connections").update(
            {"status": "expired"}
        ).eq("user_id", user_id).eq("provider", provider).execute()
    except Exception:
        logger.warning(
            "google_token_refresh: failed to mark token expired [user_id=%s provider=%s]",
            user_id,
            provider,
            exc_info=True,
        )
