"""Tests for GET /oauth/{provider}/callback — GitHub and Slack token exchange.

Covers
------
Happy paths
  - GitHub: successful exchange stores one row, refresh_token=NULL, expires_at=NULL
  - Slack:  successful exchange stores one row, refresh_token=NULL, expires_at=NULL

HTTP-200-on-failure detection (the critical new behaviour)
  - GitHub: HTTP 200 body with {"error": "bad_verification_code"} → 400, no DB write
  - GitHub: HTTP 200 body with {"error": "bad_verification_code"} (form-encoded fallback)
  - Slack:  HTTP 200 body with {"ok": false, "error": "invalid_code"} → 400, no DB write

Encryption
  - GitHub access_token is encrypted at rest and decryptable
  - Slack  access_token is encrypted at rest and decryptable

Scope parsing
  - GitHub returns comma-separated scopes; they are split correctly
  - Slack  returns comma-separated scopes; they are split correctly

Existing Google path is NOT broken
  - A Google callback still creates two rows (google_calendar + gmail)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user
from app.main import app

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FAKE_USER = CurrentUser(id="test-user-uuid-1234", email="test@example.com")

_VALID_ENCRYPTION_KEY = Fernet.generate_key().decode()


def _authed_client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Clean up dependency overrides after every test."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def enc_key(monkeypatch):
    """Patch ENCRYPTION_KEY on the live settings object."""
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", _VALID_ENCRYPTION_KEY)
    return _VALID_ENCRYPTION_KEY


@pytest.fixture()
def mock_settings():
    """Replace the settings object used inside the router for full isolation."""
    with patch("app.api.routers.oauth.settings") as m:
        m.ENCRYPTION_KEY = _VALID_ENCRYPTION_KEY
        m.SUPABASE_JWT_SECRET = "test-jwt-secret"
        m.SUPABASE_URL = "https://fake.supabase.co"
        m.SUPABASE_SERVICE_ROLE_KEY = "fake-service-key"
        # GitHub credentials
        m.GITHUB_OAUTH_CLIENT_ID = "fake-github-client-id"
        m.GITHUB_OAUTH_CLIENT_SECRET = "fake-github-client-secret"
        # Slack credentials
        m.SLACK_CLIENT_ID = "fake-slack-client-id"
        m.SLACK_CLIENT_SECRET = "fake-slack-client-secret"
        # Google (kept so existing tests using this fixture don't break)
        m.GOOGLE_OAUTH_CLIENT_ID = "fake-google-client-id"
        m.GOOGLE_OAUTH_CLIENT_SECRET = "fake-google-client-secret"
        m.GOOGLE_OAUTH_REDIRECT_URI = "http://localhost:8000/oauth/google/callback"
        yield m


@pytest.fixture()
def mock_state():
    """Bypass the CSRF state verification for all tests that use it."""
    with patch("app.api.routers.oauth._verify_state_token", return_value=True):
        yield


@pytest.fixture()
def mock_db():
    """Return a mock that intercepts all create_client → table → upsert calls."""
    with patch("app.api.routers.oauth.create_client") as mock_create:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        mock_upsert = MagicMock()
        mock_table.upsert.return_value = mock_upsert

        yield mock_table


def _mock_token_response(body: dict, status_code: int = 200) -> MagicMock:
    """Build a fake httpx response object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = ""  # not used when JSON parse succeeds
    resp.headers = {"content-type": "application/json"}
    return resp


# ---------------------------------------------------------------------------
# GitHub — happy path
# ---------------------------------------------------------------------------


def test_github_callback_success_stores_one_row(mock_settings, mock_state, mock_db) -> None:
    """A valid GitHub exchange must store exactly one row with provider='github'."""
    token_resp = _mock_token_response(
        {"access_token": "ghs_fakeAccessToken", "token_type": "bearer", "scope": "repo"}
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        resp = client.get("/oauth/github/callback?code=valid_code&state=mock_state")

    assert resp.status_code == 200
    assert resp.json() == {"message": "OAuth connection successful"}

    mock_db.upsert.assert_called_once()
    records = mock_db.upsert.call_args[0][0]
    assert len(records) == 1
    assert records[0]["provider"] == "github"
    assert records[0]["status"] == "active"


def test_github_callback_success_null_refresh_and_expiry(
    mock_settings, mock_state, mock_db
) -> None:
    """GitHub rows must have refresh_token=None and expires_at=None."""
    token_resp = _mock_token_response(
        {"access_token": "ghs_fakeAccessToken", "token_type": "bearer", "scope": "repo"}
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        client.get("/oauth/github/callback?code=valid_code&state=mock_state")

    records = mock_db.upsert.call_args[0][0]
    assert records[0]["refresh_token"] is None
    assert records[0]["expires_at"] is None


def test_github_callback_comma_scope_parsed_correctly(mock_settings, mock_state, mock_db) -> None:
    """GitHub echoes scopes as comma-separated; we must split on commas."""
    token_resp = _mock_token_response(
        {
            "access_token": "ghs_fakeAccessToken",
            "token_type": "bearer",
            "scope": "repo,read:user",  # comma-separated (GitHub's actual format)
        }
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        client.get("/oauth/github/callback?code=valid_code&state=mock_state")

    records = mock_db.upsert.call_args[0][0]
    assert records[0]["scopes"] == ["repo", "read:user"]


def test_github_callback_access_token_encrypted_at_rest(mock_settings, mock_state, mock_db) -> None:
    """The access_token written to the DB must be Fernet-encrypted."""
    raw_token = "ghs_realSecretToken"
    token_resp = _mock_token_response(
        {"access_token": raw_token, "token_type": "bearer", "scope": "repo"}
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        client.get("/oauth/github/callback?code=valid_code&state=mock_state")

    records = mock_db.upsert.call_args[0][0]
    encrypted = records[0]["access_token"]

    # Must NOT be stored in plaintext
    assert encrypted != raw_token

    # Must be decryptable back to the original
    fernet = Fernet(_VALID_ENCRYPTION_KEY.encode())
    assert fernet.decrypt(encrypted.encode()).decode() == raw_token


# ---------------------------------------------------------------------------
# GitHub — HTTP-200-on-failure detection
# ---------------------------------------------------------------------------


def test_github_bad_code_returns_400_not_crash(mock_settings, mock_state, mock_db) -> None:
    """GitHub returns HTTP 200 with an 'error' key on a bad/reused code.
    We must return 400 and NOT write to the DB.
    """
    token_resp = _mock_token_response(
        {
            "error": "bad_verification_code",
            "error_description": "The code passed is incorrect or expired.",
        },
        status_code=200,  # GitHub quirk: HTTP 200 even on failure
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        resp = client.get("/oauth/github/callback?code=reused_code&state=mock_state")

    assert resp.status_code == 400
    assert "bad_verification_code" in resp.json()["detail"]
    mock_db.upsert.assert_not_called()


def test_github_bad_code_form_encoded_fallback(mock_settings, mock_state, mock_db) -> None:
    """If GitHub somehow returns form-encoded instead of JSON, we still detect failure."""
    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.json.side_effect = Exception("not json")
    bad_resp.text = "error=bad_verification_code&error_description=The+code+is+expired"
    bad_resp.headers = {"content-type": "application/x-www-form-urlencoded"}

    with patch("httpx.Client.post", return_value=bad_resp):
        client = _authed_client()
        resp = client.get("/oauth/github/callback?code=reused_code&state=mock_state")

    assert resp.status_code == 400
    assert "bad_verification_code" in resp.json()["detail"]
    mock_db.upsert.assert_not_called()


# ---------------------------------------------------------------------------
# Slack — happy path
# ---------------------------------------------------------------------------


def test_slack_callback_success_stores_one_row(mock_settings, mock_state, mock_db) -> None:
    """A valid Slack exchange must store exactly one row with provider='slack'."""
    token_resp = _mock_token_response(
        {
            "ok": True,
            "access_token": "xoxb-fake-bot-token",
            "token_type": "bot",
            "scope": "chat:write,channels:read",
        }
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        resp = client.get("/oauth/slack/callback?code=valid_code&state=mock_state")

    assert resp.status_code == 200
    assert resp.json() == {"message": "OAuth connection successful"}

    mock_db.upsert.assert_called_once()
    records = mock_db.upsert.call_args[0][0]
    assert len(records) == 1
    assert records[0]["provider"] == "slack"
    assert records[0]["status"] == "active"


def test_slack_callback_success_null_refresh_and_expiry(mock_settings, mock_state, mock_db) -> None:
    """Slack rows must have refresh_token=None and expires_at=None."""
    token_resp = _mock_token_response(
        {
            "ok": True,
            "access_token": "xoxb-fake-bot-token",
            "scope": "chat:write,channels:read",
        }
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        client.get("/oauth/slack/callback?code=valid_code&state=mock_state")

    records = mock_db.upsert.call_args[0][0]
    assert records[0]["refresh_token"] is None
    assert records[0]["expires_at"] is None


def test_slack_callback_comma_scope_parsed_correctly(mock_settings, mock_state, mock_db) -> None:
    """Slack returns scopes as comma-separated; we must split on commas."""
    token_resp = _mock_token_response(
        {
            "ok": True,
            "access_token": "xoxb-fake-bot-token",
            "scope": "chat:write,channels:read,users:read",
        }
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        client.get("/oauth/slack/callback?code=valid_code&state=mock_state")

    records = mock_db.upsert.call_args[0][0]
    assert records[0]["scopes"] == ["chat:write", "channels:read", "users:read"]


def test_slack_callback_access_token_encrypted_at_rest(mock_settings, mock_state, mock_db) -> None:
    """The access_token written to the DB must be Fernet-encrypted."""
    raw_token = "xoxb-real-secret-bot-token"
    token_resp = _mock_token_response(
        {"ok": True, "access_token": raw_token, "scope": "chat:write"}
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        client.get("/oauth/slack/callback?code=valid_code&state=mock_state")

    records = mock_db.upsert.call_args[0][0]
    encrypted = records[0]["access_token"]

    assert encrypted != raw_token

    fernet = Fernet(_VALID_ENCRYPTION_KEY.encode())
    assert fernet.decrypt(encrypted.encode()).decode() == raw_token


# ---------------------------------------------------------------------------
# Slack — HTTP-200-on-failure detection
# ---------------------------------------------------------------------------


def test_slack_bad_code_returns_400_not_crash(mock_settings, mock_state, mock_db) -> None:
    """Slack returns HTTP 200 with ok=false on a bad/reused code.
    We must return 400 and NOT write to the DB.
    """
    token_resp = _mock_token_response(
        {"ok": False, "error": "invalid_code"},
        status_code=200,  # Slack quirk: HTTP 200 even on failure
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        resp = client.get("/oauth/slack/callback?code=reused_code&state=mock_state")

    assert resp.status_code == 400
    assert "invalid_code" in resp.json()["detail"]
    mock_db.upsert.assert_not_called()


def test_slack_ok_false_without_error_field_returns_400(mock_settings, mock_state, mock_db) -> None:
    """ok=false with no 'error' field must still be treated as a failure."""
    token_resp = _mock_token_response({"ok": False})

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        resp = client.get("/oauth/slack/callback?code=bad_code&state=mock_state")

    assert resp.status_code == 400
    mock_db.upsert.assert_not_called()


# ---------------------------------------------------------------------------
# Regression — existing Google path still works
# ---------------------------------------------------------------------------


def test_google_callback_still_creates_two_rows(mock_settings, mock_state, mock_db) -> None:
    """Existing Google flow must be unaffected: two rows (google_calendar + gmail)."""
    token_resp = _mock_token_response(
        {
            "access_token": "ya29.google_access",
            "refresh_token": "1//google_refresh",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/calendar.events",
        },
        status_code=200,
    )

    with patch("httpx.Client.post", return_value=token_resp):
        client = _authed_client()
        resp = client.get("/oauth/google/callback?code=google_code&state=mock_state")

    assert resp.status_code == 200
    records = mock_db.upsert.call_args[0][0]
    assert len(records) == 2
    providers = {r["provider"] for r in records}
    assert providers == {"google_calendar", "gmail"}


# ---------------------------------------------------------------------------
# Shared edge cases
# ---------------------------------------------------------------------------


def test_callback_missing_code_returns_400(mock_settings, mock_state) -> None:
    """A callback with no code param must return 400."""
    client = _authed_client()
    resp = client.get("/oauth/github/callback?state=mock_state")
    assert resp.status_code == 400
    assert "missing" in resp.json()["detail"].lower()


def test_callback_user_denied_consent_returns_400(mock_settings) -> None:
    """If the user clicks 'Deny', provider sends error=access_denied → 400."""
    client = _authed_client()
    resp = client.get("/oauth/github/callback?error=access_denied&state=mock_state")
    assert resp.status_code == 400
    assert "access_denied" in resp.json()["detail"]


def test_callback_unknown_provider_returns_404(mock_settings) -> None:
    """An unsupported provider string must return 404."""
    client = _authed_client()
    resp = client.get("/oauth/notion/callback?code=x&state=y")
    assert resp.status_code == 404
