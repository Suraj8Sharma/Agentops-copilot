"""Tests for DELETE /oauth/{provider} — D27 §4.2

Spec: D27 §4.2 — OAuth disconnect / revoke (3 tests)
Manual: §14

Strategy
--------
All tests mock app.api.routers.oauth.create_client and override the
get_current_user dependency with a fake user. No live Supabase, no env vars.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import CurrentUser, get_current_user
from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_USER = CurrentUser(id="test-user-uuid-revoke", email="revoke@example.com")


def _authed_client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    return TestClient(app, raise_server_exceptions=False)


def _unauthed_client() -> TestClient:
    app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Ensure dependency overrides are cleared between tests."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_service_client():
    """Patch create_client at its source module and patch settings so the
    DELETE endpoint can read SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."""
    with (
        patch("app.db.supabase_client.create_client") as mock_create,
        patch("app.api.routers.oauth.settings") as mock_settings,
    ):
        # Provide the settings values the DELETE endpoint reads
        mock_settings.SUPABASE_URL = "https://fake.supabase.co"
        mock_settings.SUPABASE_SERVICE_ROLE_KEY = "fake-service-role-key"

        mock_client = MagicMock()
        mock_create.return_value = mock_client

        # Wire up the delete chain: table().delete().eq().eq().execute()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_delete = MagicMock()
        mock_table.delete.return_value = mock_delete
        mock_eq1 = MagicMock()
        mock_delete.eq.return_value = mock_eq1
        mock_eq2 = MagicMock()
        mock_eq1.eq.return_value = mock_eq2
        mock_eq2.execute.return_value = MagicMock()

        yield mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_disconnect_google_deletes_row(mock_service_client: MagicMock) -> None:
    """DELETE /oauth/google_calendar returns 200 and calls the correct delete chain.

    Verifies:
    - Response is 200 {"message": "Disconnected"}
    - table("oauth_connections").delete().eq("user_id", <user_id>).eq("provider", "google_calendar").execute() is called
    """
    client = _authed_client()

    response = client.delete("/oauth/google_calendar")

    assert response.status_code == 200, response.text
    assert response.json() == {"message": "Disconnected"}

    mock_table = mock_service_client.table
    mock_table.assert_called_with("oauth_connections")
    mock_table.return_value.delete.assert_called_once()

    # Verify eq("user_id", ...) was called with the fake user's id
    eq1_call = mock_table.return_value.delete.return_value.eq
    eq1_call.assert_called_once_with("user_id", _FAKE_USER.id)

    # Verify eq("provider", "google_calendar") was chained
    eq2_call = eq1_call.return_value.eq
    eq2_call.assert_called_once_with("provider", "google_calendar")


def test_disconnect_requires_jwt() -> None:
    """DELETE /oauth/github without Authorization header must return 401."""
    client = _unauthed_client()

    response = client.delete("/oauth/github")

    assert response.status_code == 401, (
        f"Expected 401 without JWT, got {response.status_code}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DELETE /oauth/{provider} does not validate provider against _SUPPORTED_PROVIDERS. "
        "An unknown provider like 'notion' silently runs an empty delete instead of returning 404. "
        "Fix in D28: add _SUPPORTED_PROVIDERS guard to the DELETE endpoint. "
        "Documented in docs/issues/d28-oauth-bugs.md (Issue 2)"
    ),
)
def test_disconnect_unknown_provider_returns_404(mock_service_client: MagicMock) -> None:
    """DELETE /oauth/notion (unknown provider) must return 404.

    Currently xfail: the endpoint has no provider validation guard.
    Once the guard is added in D28, this test will pass — remove the xfail marker.
    """
    client = _authed_client()

    response = client.delete("/oauth/notion")

    assert response.status_code == 404, (
        f"Expected 404 for unknown provider, got {response.status_code}: {response.text}"
    )
