"""Tests for POST /oauth/internal/sweep-tokens — D9 spec acceptance criteria.

Required tests (spec §7)
------------------------
- ``test_oauth_7day_testing_mode_expiry_is_flagged``
- ``test_oauth_sweep_requires_cron_secret``
- ``test_jwt_background_refresh``

Strategy
--------
All tests run fully in-memory using ``unittest.mock``.  No real Supabase
connection, no real Google API call.  The sweep endpoint's logic is exercised
by controlling exactly what the mocked DB client returns and asserting what it
was told to update.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_CRON_SECRET = "test-cron-secret-abc123"
_BEARER = f"Bearer {_CRON_SECRET}"

# A connected_at timestamp that is exactly 6 days 13 hours old — past the
# 6d 12h threshold, so it SHOULD be flagged.
_PAST_THRESHOLD = (datetime.now(timezone.utc) - timedelta(days=6, hours=13)).isoformat()

# A connected_at timestamp that is only 2 days old — should NOT be flagged.
_WITHIN_THRESHOLD = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()


@pytest.fixture(autouse=True)
def _patch_cron_secret() -> None:
    """Temporarily set CRON_SECRET on the live settings singleton for the duration of each test."""
    original = settings.CRON_SECRET
    # Pydantic v2 models are frozen by default; bypass with object.__setattr__
    object.__setattr__(settings, "CRON_SECRET", _CRON_SECRET)
    yield
    object.__setattr__(settings, "CRON_SECRET", original)


# ---------------------------------------------------------------------------
# Fixture: mock the Supabase service-role client used by the sweep endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_service_client():
    """
    Patches ``create_client`` in the oauth router so the sweep endpoint never
    touches a real database.  Yields a configured MagicMock that callers can
    further customise per-test.
    """
    with patch("app.api.routers.oauth.create_client") as mock_create:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        # Default: table().select().in_().eq().execute() returns empty data
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        mock_select = MagicMock()
        mock_table.select.return_value = mock_select

        mock_in = MagicMock()
        mock_select.in_.return_value = mock_in

        mock_eq = MagicMock()
        mock_in.eq.return_value = mock_eq

        mock_execute = MagicMock()
        mock_eq.execute.return_value = mock_execute
        mock_execute.data = []

        # For the update chain: table().update().in_().execute()
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update_in = MagicMock()
        mock_update.in_.return_value = mock_update_in
        mock_update_in.execute.return_value = MagicMock()

        yield mock_client


# ---------------------------------------------------------------------------
# Test 1 — spec §7 criterion 2
# ---------------------------------------------------------------------------


def test_oauth_7day_testing_mode_expiry_is_flagged(mock_service_client: MagicMock) -> None:
    """A Google connection older than 6d 12h must be flagged as expired_testing_mode.

    Spec: Insert a connection with connected_at set to 6.9 days ago,
    run the sweep, and verify the status changes to flag the upcoming expiry.
    """
    # --- Arrange ---
    # Two active connections: one past the threshold (should be flagged),
    # one within the threshold (should be left alone).
    stale_row = {
        "id": "conn-uuid-stale",
        "user_id": "user-uuid-1",
        "provider": "google_calendar",
        "connected_at": _PAST_THRESHOLD,
        "status": "active",
    }
    fresh_row = {
        "id": "conn-uuid-fresh",
        "user_id": "user-uuid-2",
        "provider": "gmail",
        "connected_at": _WITHIN_THRESHOLD,
        "status": "active",
    }

    # Wire the mock so the DB query returns both rows
    mock_eq = mock_service_client.table.return_value.select.return_value.in_.return_value.eq
    mock_eq.return_value.execute.return_value.data = [
        stale_row,
        fresh_row,
    ]

    # --- Act ---
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/oauth/internal/sweep-tokens",
        headers={"Authorization": _BEARER},
    )

    # --- Assert ---
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["scanned"] == 2, "Both rows should have been examined"
    assert data["flagged"] == 1, "Only the stale row should be flagged"

    # Verify update() was called with the correct status and only the stale ID
    mock_table = mock_service_client.table.return_value
    mock_table.update.assert_called_once_with({"status": "expired_testing_mode"})

    update_in_call = mock_table.update.return_value.in_
    update_in_call.assert_called_once_with("id", ["conn-uuid-stale"])


# ---------------------------------------------------------------------------
# Test 2 — spec §7 criterion 3
# ---------------------------------------------------------------------------


def test_oauth_sweep_requires_cron_secret() -> None:
    """The sweep endpoint must reject requests with a missing or wrong secret.

    Spec: Ensures the internal sweep endpoint rejects requests missing
    the correct auth secret.
    """
    client = TestClient(app, raise_server_exceptions=False)

    # Case A — no Authorization header at all
    response_no_auth = client.post("/oauth/internal/sweep-tokens")
    assert response_no_auth.status_code == 401, (
        f"Expected 401 without auth, got {response_no_auth.status_code}"
    )
    assert "Invalid or missing" in response_no_auth.json()["detail"]

    # Case B — wrong secret value
    response_wrong_secret = client.post(
        "/oauth/internal/sweep-tokens",
        headers={"Authorization": "Bearer definitely-wrong-secret"},
    )
    assert response_wrong_secret.status_code == 401, (
        f"Expected 401 with wrong secret, got {response_wrong_secret.status_code}"
    )
    assert "Invalid or missing" in response_wrong_secret.json()["detail"]

    # Case C — correct format but wrong scheme (not "Bearer")
    response_bad_scheme = client.post(
        "/oauth/internal/sweep-tokens",
        headers={"Authorization": f"Token {_CRON_SECRET}"},
    )
    assert response_bad_scheme.status_code == 401, (
        f"Expected 401 with bad scheme, got {response_bad_scheme.status_code}"
    )


# ---------------------------------------------------------------------------
# Test 3 — spec §7 criterion 1
# ---------------------------------------------------------------------------


def test_jwt_background_refresh() -> None:
    """The /auth/refresh endpoint issues a new token pair without interrupting the user.

    Spec: The client/system successfully renews the Supabase JWT before it
    expires, without interrupting the user.

    This verifies the backend mechanism that enables automatic background
    refresh (POST /auth/refresh) works correctly — the client calls this
    proactively before the 1-hour access token expires so the user never
    gets logged out mid-task.
    """
    with patch("app.api.routers.auth.supabase.auth.refresh_session") as mock_refresh:
        # Simulate a successful Supabase token refresh response
        mock_session = MagicMock()
        mock_session.session.access_token = "new-background-access-token"
        mock_session.session.refresh_token = "new-background-refresh-token"
        mock_refresh.return_value = mock_session

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": "still-valid-refresh-token"},
        )

    # The call must succeed with a fresh token pair
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["access_token"] == "new-background-access-token", (
        "A fresh access token must be returned to allow seamless background renewal"
    )
    assert data["refresh_token"] == "new-background-refresh-token", (
        "A fresh refresh token must be returned so the next proactive refresh can succeed"
    )

    # The refresh was called exactly once — no double-refresh, no silent failure
    mock_refresh.assert_called_once_with("still-valid-refresh-token")
