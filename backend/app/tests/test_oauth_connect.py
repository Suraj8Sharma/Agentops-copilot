"""Tests for GET /oauth/{provider}/connect — D7 spec acceptance criteria.

All tests use FastAPI's TestClient with a mocked ``get_current_user``
dependency so no live Supabase connection is needed.

Required test (spec §10)
------------------------
- ``test_oauth_google_consent_redirect_has_correct_scopes``

Additional coverage
-------------------
- 401 when no Authorization header is sent
- 404 for an unknown provider
- 500 when GOOGLE_OAUTH_CLIENT_ID is not configured
- 500 when GOOGLE_OAUTH_REDIRECT_URI is not configured
- Response URL contains required OAuth params
  (response_type, access_type, prompt, state)
"""

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.core.security import CurrentUser, get_current_user
from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_USER = CurrentUser(id="test-user-uuid-1234", email="test@example.com")

_REQUIRED_SCOPES = {
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
}


def _authed_client() -> TestClient:
    """Return a TestClient where get_current_user is short-circuited."""
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    client = TestClient(app, raise_server_exceptions=True)
    return client


def _unauthed_client() -> TestClient:
    """Return a TestClient with no dependency override (real auth path)."""
    app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Ensure dependency overrides are cleaned up after each test."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _mock_settings():
    """Ensure required OAuth config is set for all tests in this file.
    
    In CI environments, .env is not present, so GOOGLE_OAUTH_CLIENT_ID
    and GOOGLE_OAUTH_REDIRECT_URI would default to "" and trigger 500 errors.
    """
    with patch("app.api.routers.oauth.settings") as mock_settings:
        mock_settings.GOOGLE_OAUTH_CLIENT_ID = "test-client-id"
        mock_settings.GOOGLE_OAUTH_REDIRECT_URI = "http://localhost:8000/oauth/google/callback"
        mock_settings.SUPABASE_JWT_SECRET = "test-jwt-secret-for-hmac-signing"
        yield mock_settings



# ---------------------------------------------------------------------------
# §10 Required acceptance test
# ---------------------------------------------------------------------------


def test_oauth_google_consent_redirect_has_correct_scopes() -> None:
    """Spec §10: The built URL scope list matches EXACTLY the three scopes.

    Asserts:
    - calendar.events  (read/write on events, not full calendar admin)
    - gmail.send
    - gmail.compose

    No broader scopes (e.g. gmail.readonly, calendar) must appear.
    """
    client = _authed_client()
    response = client.get("/oauth/google/connect")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "authorization_url" in body

    parsed = urlparse(body["authorization_url"])
    qs = parse_qs(parsed.query)

    # scope comes as a space-separated string — split it
    assert "scope" in qs, "authorization_url must contain a 'scope' parameter"
    returned_scopes = set(qs["scope"][0].split())

    assert returned_scopes == _REQUIRED_SCOPES, (
        f"Scope mismatch.\n"
        f"  Expected : {sorted(_REQUIRED_SCOPES)}\n"
        f"  Got      : {sorted(returned_scopes)}"
    )


# ---------------------------------------------------------------------------
# Required OAuth URL params
# ---------------------------------------------------------------------------


def test_oauth_connect_url_has_required_params() -> None:
    """Authorization URL must include all mandatory OAuth2 parameters."""
    client = _authed_client()
    response = client.get("/oauth/google/connect")

    assert response.status_code == 200
    parsed = urlparse(response.json()["authorization_url"])
    qs = parse_qs(parsed.query)

    assert qs.get("response_type") == ["code"], "response_type must be 'code'"
    assert qs.get("access_type") == ["offline"], "access_type must be 'offline' (for refresh token)"
    assert qs.get("prompt") == ["consent"], (
        "prompt must be 'consent' (forces refresh token reissue)"
    )
    assert "state" in qs and qs["state"][0], "state must be a non-empty signed token"
    assert "client_id" in qs, "client_id must be present"
    assert "redirect_uri" in qs, "redirect_uri must be present"


def test_oauth_connect_url_targets_correct_base() -> None:
    """Authorization URL must use the correct Google OAuth2 base endpoint."""
    client = _authed_client()
    response = client.get("/oauth/google/connect")

    assert response.status_code == 200
    parsed = urlparse(response.json()["authorization_url"])

    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/v2/auth"


def test_oauth_connect_state_is_unique_per_request() -> None:
    """Each call must return a different state token (nonce-based)."""
    client = _authed_client()
    r1 = client.get("/oauth/google/connect")
    r2 = client.get("/oauth/google/connect")

    assert r1.status_code == 200
    assert r2.status_code == 200

    qs1 = parse_qs(urlparse(r1.json()["authorization_url"]).query)
    qs2 = parse_qs(urlparse(r2.json()["authorization_url"]).query)

    assert qs1["state"][0] != qs2["state"][0], (
        "state tokens must be unique per request (nonce ensures this)"
    )


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_oauth_connect_unknown_provider_returns_404() -> None:
    """Unknown providers must return 404 — GitHub/Slack arrive in D10."""
    client = _authed_client()
    response = client.get("/oauth/github/connect")
    assert response.status_code == 404


def test_oauth_connect_slack_returns_404() -> None:
    """Slack is also not yet supported — must return 404."""
    client = _authed_client()
    response = client.get("/oauth/slack/connect")
    assert response.status_code == 404


def test_oauth_connect_requires_auth_returns_401() -> None:
    """Hitting the endpoint without a JWT must return 401."""
    client = _unauthed_client()
    # No Authorization header — TestClient won't add one by default.
    response = client.get("/oauth/google/connect")
    assert response.status_code == 401


def test_oauth_connect_missing_client_id_returns_500(_mock_settings) -> None:
    """Missing GOOGLE_OAUTH_CLIENT_ID must produce a loud 500."""
    _mock_settings.GOOGLE_OAUTH_CLIENT_ID = ""
    client = _authed_client()
    response = client.get("/oauth/google/connect")

    assert response.status_code == 500
    assert "not configured" in response.json()["detail"].lower()


def test_oauth_connect_missing_redirect_uri_returns_500(_mock_settings) -> None:
    """Missing GOOGLE_OAUTH_REDIRECT_URI must produce a loud 500."""
    _mock_settings.GOOGLE_OAUTH_REDIRECT_URI = ""
    client = _authed_client()
    response = client.get("/oauth/google/connect")

    assert response.status_code == 500
    assert "not configured" in response.json()["detail"].lower()

