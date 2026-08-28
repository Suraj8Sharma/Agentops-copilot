"""Tests for POST /auth/signup and POST /auth/login.

All tests run against a **mocked** Supabase client -- no real network calls,
no production data touched.  The mock is applied at the supabase module level
so the singleton client is replaced before the FastAPI app is imported.

Test matrix (matches Section 15.4 of the project manual):
    test_signup_valid_credentials_creates_account
    test_signup_duplicate_email_rejected
    test_signup_weak_password_rejected
    test_login_correct_credentials_succeeds
    test_login_incorrect_password_rejected
"""

from __future__ import annotations

import unittest.mock as mock
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers to build realistic Supabase-style response objects
# ---------------------------------------------------------------------------


def _make_user(user_id: str = "test-uid-123", identities: list | None = None) -> MagicMock:
    """Return a mock object that looks like a Supabase User."""
    user = MagicMock()
    user.id = user_id
    user.identities = identities if identities is not None else [MagicMock()]
    return user


def _make_session(
    access_token: str = "mock-access-token",
    refresh_token: str = "mock-refresh-token",
) -> MagicMock:
    """Return a mock object that looks like a Supabase Session."""
    session = MagicMock()
    session.access_token = access_token
    session.refresh_token = refresh_token
    return session


def _make_auth_response(user: Any, session: Any) -> MagicMock:
    """Return a mock object that looks like a Supabase AuthResponse."""
    resp = MagicMock()
    resp.user = user
    resp.session = session
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject fake env vars so pydantic-settings does not raise on import."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


@pytest.fixture()
def mock_supabase() -> MagicMock:
    """Return a MagicMock that replaces the supabase singleton."""
    return MagicMock()


@pytest.fixture()
def client(mock_supabase: MagicMock) -> TestClient:
    """TestClient with Supabase create_client and probe stubbed out."""
    with (
        mock.patch("app.db.supabase_client.create_client", return_value=mock_supabase),
        mock.patch("app.db.supabase_client.probe_connection", return_value=None),
    ):
        # Import app *after* patching so module-level create_client is intercepted.
        from app.main import app  # noqa: PLC0415

        # Also patch the supabase singleton that the auth router already imported.
        with mock.patch("app.api.routers.auth.supabase", mock_supabase):
            yield TestClient(app)


# ---------------------------------------------------------------------------
# POST /auth/signup tests
# ---------------------------------------------------------------------------


def test_signup_valid_credentials_creates_account(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """Valid email/password -> 201 with user_id and both tokens present."""
    user = _make_user()
    session = _make_session()
    mock_supabase.auth.sign_up.return_value = _make_auth_response(user, session)

    response = client.post(
        "/auth/signup",
        json={"email": "newuser@example.com", "password": "SecurePass123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == "test-uid-123"
    assert body["access_token"] == "mock-access-token"
    assert body["refresh_token"] == "mock-refresh-token"
    mock_supabase.auth.sign_up.assert_called_once_with(
        {"email": "newuser@example.com", "password": "SecurePass123"}
    )


def test_signup_duplicate_email_rejected(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """Re-signing up with an existing email -> 400, not 500."""
    # Supabase returns a user with identities=[] for duplicate email
    # (when "Confirm email" is enabled in project settings).
    user = _make_user(identities=[])  # empty identities signals duplicate
    session = _make_session()
    mock_supabase.auth.sign_up.return_value = _make_auth_response(user, session)

    response = client.post(
        "/auth/signup",
        json={"email": "existing@example.com", "password": "SecurePass123"},
    )

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_signup_weak_password_rejected(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """Password below Supabase's minimum policy -> 400, not 500."""
    mock_supabase.auth.sign_up.side_effect = Exception(
        "Password should be at least 6 characters."
    )

    response = client.post(
        "/auth/signup",
        json={"email": "user@example.com", "password": "abc"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] != ""


# ---------------------------------------------------------------------------
# POST /auth/login tests
# ---------------------------------------------------------------------------


def test_login_correct_credentials_succeeds(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """Valid credentials -> 200 with both access_token and refresh_token."""
    session = _make_session()
    mock_supabase.auth.sign_in_with_password.return_value = _make_auth_response(
        _make_user(), session
    )

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "SecurePass123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["access_token"] == "mock-access-token"
    assert body["refresh_token"] == "mock-refresh-token"


def test_login_incorrect_password_rejected(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """Wrong password -> 401, no token issued."""
    mock_supabase.auth.sign_in_with_password.side_effect = Exception(
        "Invalid login credentials"
    )

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "WrongPassword"},
    )

    assert response.status_code == 401
    body = response.json()
    assert "access_token" not in body
    assert "refresh_token" not in body
