"""Tests for GET /oauth/{provider}/callback — D8 spec acceptance criteria.

Required tests (spec §9)
------------------------
- ``test_oauth_callback_exchanges_code_for_token``
- ``test_oauth_token_encrypted_at_rest``
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.security import CurrentUser, get_current_user
from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_USER = CurrentUser(id="test-user-uuid-1234", email="test@example.com")

_FAKE_ENCRYPTION_KEY = Fernet.generate_key().decode()


def _authed_client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    client = TestClient(app, raise_server_exceptions=False)
    return client


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_settings():
    """Patch the settings object used inside the router so credentials and
    encryption key are always present, regardless of the local .env file."""
    with patch("app.api.routers.oauth.settings") as m:
        m.ENCRYPTION_KEY = _FAKE_ENCRYPTION_KEY
        m.SUPABASE_JWT_SECRET = "test-jwt-secret"
        m.SUPABASE_URL = "https://fake.supabase.co"
        m.SUPABASE_SERVICE_ROLE_KEY = "fake-service-key"
        m.GOOGLE_OAUTH_CLIENT_ID = "fake-google-client-id"
        m.GOOGLE_OAUTH_CLIENT_SECRET = "fake-google-client-secret"
        m.GOOGLE_OAUTH_REDIRECT_URI = "http://localhost:8000/oauth/google/callback"
        m.GITHUB_OAUTH_CLIENT_ID = "fake-github-client-id"
        m.GITHUB_OAUTH_CLIENT_SECRET = "fake-github-client-secret"
        m.SLACK_CLIENT_ID = "fake-slack-client-id"
        m.SLACK_CLIENT_SECRET = "fake-slack-client-secret"
        yield m


@pytest.fixture
def mock_supabase_table():
    with patch("app.api.routers.oauth.create_client") as mock_create_client:
        mock_client_instance = MagicMock()
        mock_create_client.return_value = mock_client_instance

        mock_table_method = MagicMock()
        mock_client_instance.table = mock_table_method

        mock_table_instance = MagicMock()
        mock_table_method.return_value = mock_table_instance

        mock_upsert = MagicMock()
        mock_table_instance.upsert.return_value = mock_upsert

        yield mock_table_method


@pytest.fixture
def mock_verify_state():
    with patch("app.api.routers.oauth._verify_and_extract_user_id", return_value="test-user-uuid-1234") as mock_verify:
        yield mock_verify


@pytest.fixture
def mock_httpx_post():
    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200  # required: new code inspects status_code for Google
        mock_response.json.return_value = {
            "access_token": "mock_google_access_token",
            "refresh_token": "mock_google_refresh_token",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/calendar.events",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        yield mock_post


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_oauth_callback_exchanges_code_for_token(
    mock_supabase_table, mock_verify_state, mock_httpx_post
) -> None:
    """Asserts the backend successfully trades the code for tokens and upserts them."""

    client = _authed_client()

    response = client.get("/oauth/google/callback?code=mock_auth_code&state=mock_valid_state")

    assert response.status_code == 200
    assert response.json() == {"message": "OAuth connection successful"}

    # Verify the code exchange call used the Google token URL from PROVIDER_CONFIG
    mock_httpx_post.assert_called_once()
    args, kwargs = mock_httpx_post.call_args
    assert args[0] == "https://oauth2.googleapis.com/token"
    assert kwargs["data"]["code"] == "mock_auth_code"
    assert kwargs["data"]["grant_type"] == "authorization_code"

    # Verify the database upsert call
    mock_supabase_table.assert_called_once_with("oauth_connections")
    upsert_mock = mock_supabase_table().upsert
    upsert_mock.assert_called_once()

    # We should have inserted two rows (google_calendar and gmail)
    records = upsert_mock.call_args[0][0]
    assert len(records) == 2

    providers = {r["provider"] for r in records}
    assert providers == {"google_calendar", "gmail"}

    for r in records:
        assert r["user_id"] == _FAKE_USER.id
        assert r["status"] == "active"
        assert r["access_token"] is not None


def test_oauth_token_encrypted_at_rest(
    mock_supabase_table, mock_verify_state, mock_httpx_post
) -> None:
    """Asserts that the tokens sent to the database are encrypted and decryptable."""

    client = _authed_client()

    response = client.get("/oauth/google/callback?code=mock_auth_code&state=mock_valid_state")
    assert response.status_code == 200

    # Grab what was passed to supabase.table().upsert()
    upsert_mock = mock_supabase_table().upsert
    records = upsert_mock.call_args[0][0]
    record = records[0]

    encrypted_access = record["access_token"]
    encrypted_refresh = record["refresh_token"]

    # 1. Ensure the raw string isn't the one saved
    assert encrypted_access != "mock_google_access_token"
    assert encrypted_refresh != "mock_google_refresh_token"

    # 2. Ensure we can decrypt it back to the original using the backend key
    fernet = Fernet(_FAKE_ENCRYPTION_KEY.encode())

    decrypted_access = fernet.decrypt(encrypted_access.encode()).decode()
    decrypted_refresh = fernet.decrypt(encrypted_refresh.encode()).decode()

    assert decrypted_access == "mock_google_access_token"
    assert decrypted_refresh == "mock_google_refresh_token"


def test_oauth_callback_invalid_state_rejected() -> None:
    """Asserts a tampered or missing state token blocks the flow."""
    client = _authed_client()

    response = client.get("/oauth/google/callback?code=mock_code&state=tampered.state")

    assert response.status_code == 400
    assert "Invalid state token" in response.json()["detail"]


def test_oauth_callback_consent_denied(mock_verify_state) -> None:
    """Asserts that if the user clicks 'Cancel' on Google consent, we handle it."""
    client = _authed_client()

    response = client.get("/oauth/google/callback?error=access_denied&state=mock_state")

    assert response.status_code == 400
    assert "access_denied" in response.json()["detail"]
