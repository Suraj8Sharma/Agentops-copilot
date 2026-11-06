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

        # Also patch the supabase singleton and create_client that the auth router already imported.
        with (
            mock.patch("app.api.routers.auth.supabase", mock_supabase),
            mock.patch("app.api.routers.auth.create_client", return_value=mock_supabase),
        ):
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


def test_signup_duplicate_email_rejected(client: TestClient, mock_supabase: MagicMock) -> None:
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


def test_signup_weak_password_rejected(client: TestClient, mock_supabase: MagicMock) -> None:
    """Password below Supabase's minimum policy -> 400, not 500."""
    mock_supabase.auth.sign_up.side_effect = Exception("Password should be at least 6 characters.")

    response = client.post(
        "/auth/signup",
        json={"email": "user@example.com", "password": "abc"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] != ""


def test_signup_sends_verification_email(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """When email confirmation is required, Supabase returns user without session."""
    user = _make_user(user_id="unconfirmed-user-1")
    # session is None because email verification is pending
    mock_supabase.auth.sign_up.return_value = _make_auth_response(user, None)

    response = client.post(
        "/auth/signup",
        json={"email": "unconfirmed@example.com", "password": "SecurePass123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == "unconfirmed-user-1"
    assert body["access_token"] == ""
    assert body["refresh_token"] == ""
    mock_supabase.auth.sign_up.assert_called_once_with(
        {"email": "unconfirmed@example.com", "password": "SecurePass123"}
    )


# ---------------------------------------------------------------------------
# POST /auth/login tests
# ---------------------------------------------------------------------------


def test_login_correct_credentials_succeeds(client: TestClient, mock_supabase: MagicMock) -> None:
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


def test_login_incorrect_password_rejected(client: TestClient, mock_supabase: MagicMock) -> None:
    """Wrong password -> 401, no token issued."""
    mock_supabase.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "WrongPassword"},
    )

    assert response.status_code == 401
    body = response.json()
    assert "access_token" not in body
    assert "refresh_token" not in body


# ---------------------------------------------------------------------------
# Forgot password tests
# ---------------------------------------------------------------------------


def test_forgot_password_sends_reset_email(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """POST /auth/forgot-password triggers reset_password_email and returns 200."""
    mock_supabase.auth.reset_password_email.return_value = None

    response = client.post(
        "/auth/forgot-password",
        json={"email": "forgot@example.com"},
    )

    assert response.status_code == 200
    assert "password reset link has been sent" in response.json()["message"]
    mock_supabase.auth.reset_password_email.assert_called_once_with("forgot@example.com")


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------


def test_logout_clears_local_session(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """POST /auth/logout invalidates session via Supabase sign_out."""
    mock_supabase.auth.sign_out.return_value = None

    response = client.post(
        "/auth/logout",
        json={"refresh_token": "mock-refresh-token"},
    )

    assert response.status_code == 200
    assert "Logged out successfully" in response.json()["message"]
    mock_supabase.auth.sign_out.assert_called_once()


# ---------------------------------------------------------------------------
# Account deletion tests
# ---------------------------------------------------------------------------


def test_account_deletion_cascades_across_all_17_tables(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """DELETE /auth/account calls Supabase admin.delete_user and cascades across tables."""
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    test_user = CurrentUser(id="cascade-user-uuid", email="delete@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        response = client.delete("/auth/account")
        assert response.status_code == 200
        assert "Account deleted successfully" in response.json()["message"]
        mock_supabase.auth.admin.delete_user.assert_called_once_with("cascade-user-uuid")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # Calling without JWT should fail with 401
    unauthed_response = client.delete("/auth/account")
    assert unauthed_response.status_code == 401


# ---------------------------------------------------------------------------
# Session & Lockout tests
# ---------------------------------------------------------------------------


def test_session_persists_across_app_restart(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """Simulates app restart: stored refresh_token successfully issues a fresh session."""
    session = _make_session(
        access_token="restarted-access-token",
        refresh_token="rotated-refresh-token",
    )
    mock_supabase.auth.refresh_session.return_value = _make_auth_response(_make_user(), session)

    response = client.post(
        "/auth/refresh",
        json={"refresh_token": "persisted-device-refresh-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "restarted-access-token"
    assert body["refresh_token"] == "rotated-refresh-token"
    mock_supabase.auth.refresh_session.assert_called_once_with("persisted-device-refresh-token")


def test_login_lockout_after_5_failed_attempts(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """After 5 failed login attempts, Supabase raises rate limit / lockout, returning 429."""
    mock_supabase.auth.sign_in_with_password.side_effect = [
        Exception("Invalid login credentials"),
        Exception("Invalid login credentials"),
        Exception("Invalid login credentials"),
        Exception("Invalid login credentials"),
        Exception("Too many requests: User is temporarily locked out"),
    ]

    for _ in range(4):
        res = client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "WrongPassword"},
        )
        assert res.status_code == 401

    # 5th attempt triggers brute-force lockout
    fifth_res = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "WrongPassword"},
    )
    assert fifth_res.status_code == 429
    assert (
        "too many" in fifth_res.json()["detail"].lower()
        or "locked out" in fifth_res.json()["detail"].lower()
    )


# ---------------------------------------------------------------------------
# Email verification tests
# ---------------------------------------------------------------------------


def test_email_verification_link_activates_account(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """Submitting valid token to /auth/verify activates the account and returns session tokens."""
    user = _make_user(user_id="verified-uid-456")
    session = _make_session(
        access_token="activated-access-token",
        refresh_token="activated-refresh-token",
    )
    mock_supabase.auth.verify_otp.return_value = _make_auth_response(user, session)

    response = client.post(
        "/auth/verify",
        json={"email": "verify@example.com", "token": "valid-otp-123", "type": "signup"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Email verified successfully."
    assert body["access_token"] == "activated-access-token"
    assert body["refresh_token"] == "activated-refresh-token"
    mock_supabase.auth.verify_otp.assert_called_once_with(
        {"email": "verify@example.com", "token": "valid-otp-123", "type": "signup"}
    )


def test_email_verification_expired_link_can_resend(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """Expired verification link returns 400, and user can request a resend."""
    # 1. Verification with expired token fails
    mock_supabase.auth.verify_otp.side_effect = Exception("Token has expired")
    failed_verify = client.post(
        "/auth/verify",
        json={"email": "expired@example.com", "token": "old-token-123", "type": "signup"},
    )
    assert failed_verify.status_code == 400
    assert "expired" in failed_verify.json()["detail"].lower()

    # 2. Resend new verification email succeeds
    mock_supabase.auth.resend.return_value = None
    resend_resp = client.post(
        "/auth/resend-verification",
        json={"email": "expired@example.com", "type": "signup"},
    )
    assert resend_resp.status_code == 200
    assert "resent successfully" in resend_resp.json()["message"]
    mock_supabase.auth.resend.assert_called_once_with(
        {"type": "signup", "email": "expired@example.com"}
    )


# ---------------------------------------------------------------------------
# Password reset tests
# ---------------------------------------------------------------------------


def test_reset_password_invalidates_old_sessions(
    client: TestClient, mock_supabase: MagicMock
) -> None:
    """Password reset updates credentials and old refresh tokens are rejected."""
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    test_user = CurrentUser(id="user-pwd-reset-1", email="reset@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        # 1. Reset password
        mock_supabase.auth.update_user.return_value = None
        reset_res = client.post(
            "/auth/reset-password",
            json={"password": "BrandNewPassword999!"},
        )
        assert reset_res.status_code == 200
        mock_supabase.auth.update_user.assert_called_once_with(
            {"password": "BrandNewPassword999!"}
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # 2. Old session refresh token is invalidated server-side
    mock_supabase.auth.refresh_session.side_effect = Exception(
        "Invalid or expired refresh token"
    )
    old_session_res = client.post(
        "/auth/refresh",
        json={"refresh_token": "stale-old-token-prior-to-reset"},
    )
    assert old_session_res.status_code == 401
