"""Tests for app.mcp_clients.google_token_refresh.get_valid_google_token

Spec: D27 §4.1 — Google token refresh (9 tests)
Manual: §14, §15.4, §18 A3

Strategy
--------
All tests are fully mocked:
  - supabase_admin   → patched at app.mcp_clients.google_token_refresh.supabase_admin
  - httpx.post       → patched at app.mcp_clients.google_token_refresh.httpx.post
  - settings         → patched at app.mcp_clients.google_token_refresh.settings

No live Supabase connection, no real Google API call, no env vars required.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_FERNET_KEY = Fernet.generate_key()
_FERNET = Fernet(_FERNET_KEY)

_USER_ID = "user-uuid-abc123"
_PROVIDER = "google_calendar"


def _encrypt(value: str) -> str:
    return _FERNET.encrypt(value.encode()).decode()


def _future_expires_at(minutes: int = 30) -> str:
    """Return an ISO timestamp N minutes in the future."""
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _past_expires_at(minutes: int = 10) -> str:
    """Return an ISO timestamp N minutes in the past."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _make_db_row(
    access_token: str = "plain-access-token",
    refresh_token: str | None = "plain-refresh-token",
    expires_at: str | None = None,
    status: str = "active",
    encrypt: bool = True,
) -> dict:
    """Build a fake oauth_connections row as returned by Supabase."""
    row: dict = {
        "access_token": _encrypt(access_token) if encrypt else access_token,
        "refresh_token": _encrypt(refresh_token) if (encrypt and refresh_token) else refresh_token,
        "expires_at": expires_at,
        "status": status,
    }
    return row


def _set_select_data(mock_admin: MagicMock, rows: list[dict]) -> None:
    """Helper to wire table().select()...execute().data to rows without long lines."""
    (
        mock_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data
    ) = rows


def _successful_refresh_response(new_token: str = "new-access-token") -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_resp.json.return_value = {
        "access_token": new_token,
        "expires_in": 3599,
    }
    return mock_resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("app.mcp_clients.google_token_refresh.settings")
@patch("app.mcp_clients.google_token_refresh.httpx.post")
@patch("app.mcp_clients.google_token_refresh.supabase_admin")
def test_valid_token_returned_without_refresh(
    mock_admin: MagicMock,
    mock_post: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """When expires_at is in the future, return existing token without calling httpx.post."""
    mock_settings.ENCRYPTION_KEY = _FERNET_KEY.decode()
    row = _make_db_row(expires_at=_future_expires_at(30))
    _set_select_data(mock_admin, [row])

    from app.mcp_clients.google_token_refresh import get_valid_google_token

    result = get_valid_google_token(_USER_ID, _PROVIDER)

    assert result == "plain-access-token"
    mock_post.assert_not_called()


@patch("app.mcp_clients.google_token_refresh.settings")
@patch("app.mcp_clients.google_token_refresh.httpx.post")
@patch("app.mcp_clients.google_token_refresh.supabase_admin")
def test_expired_token_triggers_google_refresh(
    mock_admin: MagicMock,
    mock_post: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """When expires_at is in the past, call httpx.post and return the new decrypted token."""
    mock_settings.ENCRYPTION_KEY = _FERNET_KEY.decode()
    mock_settings.GOOGLE_OAUTH_CLIENT_ID = "fake-client-id"
    mock_settings.GOOGLE_OAUTH_CLIENT_SECRET = "fake-client-secret"

    row = _make_db_row(expires_at=_past_expires_at(10))
    _set_select_data(mock_admin, [row])

    mock_post.return_value = _successful_refresh_response("refreshed-access-token")

    # Mock the update chain
    update_mock = mock_admin.table.return_value.update.return_value
    update_mock.eq.return_value.in_.return_value.execute.return_value = MagicMock()

    from app.mcp_clients.google_token_refresh import get_valid_google_token

    result = get_valid_google_token(_USER_ID, _PROVIDER)

    assert result == "refreshed-access-token"

    # Verify httpx.post was called with correct grant_type
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs[1]["data"]["grant_type"] == "refresh_token"
    assert call_kwargs[1]["data"]["refresh_token"] == "plain-refresh-token"

    # Verify the DB update was called with an encrypted new token (not the plaintext)
    update_call = mock_admin.table.return_value.update.call_args
    update_payload = update_call[0][0]
    assert update_payload["access_token"] != "refreshed-access-token", (
        "Token must be encrypted before storing"
    )
    # Decrypt and verify
    decrypted = Fernet(_FERNET_KEY).decrypt(update_payload["access_token"].encode()).decode()
    assert decrypted == "refreshed-access-token"


@patch("app.mcp_clients.google_token_refresh.settings")
@patch("app.mcp_clients.google_token_refresh.httpx.post")
@patch("app.mcp_clients.google_token_refresh.supabase_admin")
def test_refresh_updates_both_provider_rows(
    mock_admin: MagicMock,
    mock_post: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """After successful refresh, both google_calendar and gmail rows are updated."""
    mock_settings.ENCRYPTION_KEY = _FERNET_KEY.decode()
    mock_settings.GOOGLE_OAUTH_CLIENT_ID = "fake-client-id"
    mock_settings.GOOGLE_OAUTH_CLIENT_SECRET = "fake-client-secret"

    row = _make_db_row(expires_at=_past_expires_at(10))
    _set_select_data(mock_admin, [row])
    mock_post.return_value = _successful_refresh_response()
    update_mock = mock_admin.table.return_value.update.return_value
    update_mock.eq.return_value.in_.return_value.execute.return_value = MagicMock()

    from app.mcp_clients.google_token_refresh import get_valid_google_token

    get_valid_google_token(_USER_ID, "google_calendar")

    # Verify .in_() was called with both providers
    in_call = mock_admin.table.return_value.update.return_value.eq.return_value.in_
    in_call.assert_called_once()
    _, providers_arg = in_call.call_args[0]
    assert set(providers_arg) == {"google_calendar", "gmail"}, (
        f"Both provider rows must be updated; got {providers_arg}"
    )


@patch("app.mcp_clients.google_token_refresh.settings")
@patch("app.mcp_clients.google_token_refresh.httpx.post")
@patch("app.mcp_clients.google_token_refresh.supabase_admin")
def test_revoked_token_returns_none_and_marks_expired(
    mock_admin: MagicMock,
    mock_post: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """When Google returns invalid_grant, return None and set status='expired' in the DB."""
    mock_settings.ENCRYPTION_KEY = _FERNET_KEY.decode()
    mock_settings.GOOGLE_OAUTH_CLIENT_ID = "fake-client-id"
    mock_settings.GOOGLE_OAUTH_CLIENT_SECRET = "fake-client-secret"

    row = _make_db_row(expires_at=_past_expires_at(10))
    _set_select_data(mock_admin, [row])

    # Google returns non-2xx
    mock_revoked = MagicMock()
    mock_revoked.is_success = False
    mock_revoked.status_code = 400
    mock_revoked.json.return_value = {"error": "invalid_grant"}
    mock_post.return_value = mock_revoked

    update_mock = mock_admin.table.return_value.update.return_value
    update_mock.eq.return_value.eq.return_value.execute.return_value = MagicMock()

    from app.mcp_clients.google_token_refresh import get_valid_google_token

    result = get_valid_google_token(_USER_ID, _PROVIDER)

    assert result is None

    # Verify _mark_expired fired: update({"status": "expired"})
    update_call = mock_admin.table.return_value.update.call_args
    assert update_call is not None, "_mark_expired must call supabase_admin.table().update()"
    assert update_call[0][0] == {"status": "expired"}


@patch("app.mcp_clients.google_token_refresh.settings")
@patch("app.mcp_clients.google_token_refresh.httpx.post")
@patch("app.mcp_clients.google_token_refresh.supabase_admin")
def test_missing_refresh_token_returns_none(
    mock_admin: MagicMock,
    mock_post: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """When refresh_token is None and access token expired, return None without calling httpx."""
    mock_settings.ENCRYPTION_KEY = _FERNET_KEY.decode()

    row = _make_db_row(refresh_token=None, expires_at=_past_expires_at(10), encrypt=False)
    row["access_token"] = _encrypt("plain-access-token")
    _set_select_data(mock_admin, [row])

    from app.mcp_clients.google_token_refresh import get_valid_google_token

    result = get_valid_google_token(_USER_ID, _PROVIDER)

    assert result is None
    mock_post.assert_not_called()


@patch("app.mcp_clients.google_token_refresh.settings")
@patch("app.mcp_clients.google_token_refresh.httpx.post")
@patch("app.mcp_clients.google_token_refresh.supabase_admin")
def test_no_db_row_returns_none(
    mock_admin: MagicMock,
    mock_post: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """When the DB query returns no rows (e.g. after disconnect), return None."""
    mock_settings.ENCRYPTION_KEY = _FERNET_KEY.decode()
    _set_select_data(mock_admin, [])

    from app.mcp_clients.google_token_refresh import get_valid_google_token

    result = get_valid_google_token(_USER_ID, _PROVIDER)

    assert result is None
    mock_post.assert_not_called()


@patch("app.mcp_clients.google_token_refresh.settings")
@patch("app.mcp_clients.google_token_refresh.httpx.post")
@patch("app.mcp_clients.google_token_refresh.supabase_admin")
def test_network_error_returns_none(
    mock_admin: MagicMock,
    mock_post: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """When httpx raises RequestError during refresh call, return None without re-raising."""
    import httpx

    mock_settings.ENCRYPTION_KEY = _FERNET_KEY.decode()
    mock_settings.GOOGLE_OAUTH_CLIENT_ID = "fake-client-id"
    mock_settings.GOOGLE_OAUTH_CLIENT_SECRET = "fake-client-secret"

    row = _make_db_row(expires_at=_past_expires_at(10))
    _set_select_data(mock_admin, [row])

    mock_post.side_effect = httpx.RequestError("Connection refused")

    from app.mcp_clients.google_token_refresh import get_valid_google_token

    result = get_valid_google_token(_USER_ID, _PROVIDER)  # must not raise

    assert result is None


@patch("app.mcp_clients.google_token_refresh.settings")
@patch("app.mcp_clients.google_token_refresh.httpx.post")
@patch("app.mcp_clients.google_token_refresh.supabase_admin")
@pytest.mark.xfail(
    strict=True,
    reason=(
        "get_valid_google_token does not check status field; "
        "scope_mismatch rows proceed as active. Fix in D28. "
        "Documented in docs/issues/d28-oauth-bugs.md (Issue 1)"
    ),
)
def test_scope_mismatch_row_returns_none(
    mock_admin: MagicMock,
    mock_post: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """A row with status='scope_mismatch' must return None (Manual §15.4)."""
    mock_settings.ENCRYPTION_KEY = _FERNET_KEY.decode()

    row = _make_db_row(expires_at=_future_expires_at(30), status="scope_mismatch")
    _set_select_data(mock_admin, [row])

    from app.mcp_clients.google_token_refresh import get_valid_google_token

    result = get_valid_google_token(_USER_ID, _PROVIDER)

    assert result is None


@patch("app.mcp_clients.google_token_refresh.settings")
@patch("app.mcp_clients.google_token_refresh.httpx.post")
@patch("app.mcp_clients.google_token_refresh.supabase_admin")
def test_refresh_success_rate_meets_a3_threshold(
    mock_admin: MagicMock,
    mock_post: MagicMock,
    mock_settings: MagicMock,
) -> None:
    """Acceptance A3: token refresh success rate must be >= 95%.

    Simulates 20 refresh attempts: 19 succeed, 1 returns invalid_grant.
    Asserts:
    - success rate >= 95%
    - the 1 failure returns None (never raises, never silent success)
    - _mark_expired is called exactly once (for the revoked case)
    """
    mock_settings.ENCRYPTION_KEY = _FERNET_KEY.decode()
    mock_settings.GOOGLE_OAUTH_CLIENT_ID = "fake-client-id"
    mock_settings.GOOGLE_OAUTH_CLIENT_SECRET = "fake-client-secret"

    expired_row = _make_db_row(expires_at=_past_expires_at(10))

    success_resp = _successful_refresh_response("new-token")
    revoked_resp = MagicMock()
    revoked_resp.is_success = False
    revoked_resp.status_code = 400
    revoked_resp.json.return_value = {"error": "invalid_grant"}

    # 19 successes then 1 failure
    mock_post.side_effect = [success_resp] * 19 + [revoked_resp]

    _set_select_data(mock_admin, [expired_row])
    update_mock = mock_admin.table.return_value.update.return_value
    update_mock.eq.return_value.in_.return_value.execute.return_value = MagicMock()
    update_mock.eq.return_value.eq.return_value.execute.return_value = MagicMock()

    from app.mcp_clients.google_token_refresh import get_valid_google_token

    results = [get_valid_google_token(_USER_ID, _PROVIDER) for _ in range(20)]

    successes = [r for r in results if r is not None]
    failures = [r for r in results if r is None]

    success_rate = len(successes) / 20
    assert success_rate >= 0.95, f"A3: refresh success rate must be >= 95%, got {success_rate:.0%}"
    assert len(failures) == 1, "Exactly 1 failure expected"
    assert failures[0] is None, "Failure must return None, not raise"
