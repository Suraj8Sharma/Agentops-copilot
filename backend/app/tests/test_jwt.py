"""Tests for JWT middleware and protected routes."""

from __future__ import annotations

import unittest.mock as mock
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# We patch both the startup connection probe AND the creation of the supabase
# client singleton so the tests run entirely in-memory without a real database.
# ---------------------------------------------------------------------------
with (
    mock.patch("app.db.supabase_client.create_client"),
    mock.patch("app.db.supabase_client.probe_connection"),
):
    from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_supabase_get_user() -> Any:
    """Mock the supabase.auth.get_user method used in the dependency."""
    with mock.patch("app.core.security.supabase.auth.get_user") as m:
        yield m


@pytest.fixture
def mock_supabase_refresh() -> Any:
    """Mock the supabase.auth.refresh_session method."""
    with mock.patch("app.api.routers.auth.supabase.auth.refresh_session") as m:
        yield m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_jwt_valid_token_accepted(mock_supabase_get_user: MagicMock) -> None:
    """A valid token should grant access to a protected route."""
    # Setup mock
    mock_user = MagicMock()
    mock_user.user.id = "mock-user-123"
    mock_user.user.email = "test@example.com"
    mock_user.user.role = "authenticated"
    mock_supabase_get_user.return_value = mock_user

    response = client.get("/me", headers={"Authorization": "Bearer valid.jwt.token"})

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "mock-user-123"
    assert data["email"] == "test@example.com"


def test_jwt_missing_token_rejected() -> None:
    """A request with no Authorization header should be rejected."""
    response = client.get("/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_jwt_tampered_signature_rejected(mock_supabase_get_user: MagicMock) -> None:
    """A token that fails signature validation should be rejected."""
    mock_supabase_get_user.side_effect = Exception("JWT signature is invalid")
    
    response = client.get("/me", headers={"Authorization": "Bearer bad.jwt.token"})
    
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_token"


def test_jwt_expired_token_rejected(mock_supabase_get_user: MagicMock) -> None:
    """An expired token should be rejected with a specific 'token_expired' detail."""
    mock_supabase_get_user.side_effect = Exception("JWT expired")
    
    response = client.get("/me", headers={"Authorization": "Bearer expired.jwt.token"})
    
    assert response.status_code == 401
    assert response.json()["detail"] == "token_expired"
    assert response.headers["X-Token-Expired"] == "true"


def test_jwt_refresh_issues_new_access_token(mock_supabase_refresh: MagicMock) -> None:
    """The /auth/refresh endpoint should exchange a valid refresh token for a new pair."""
    # Setup mock
    mock_session = MagicMock()
    mock_session.session.access_token = "new-access-token"
    mock_session.session.refresh_token = "new-refresh-token"
    mock_supabase_refresh.return_value = mock_session

    response = client.post("/auth/refresh", json={"refresh_token": "valid-old-refresh-token"})

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "new-access-token"
    assert data["refresh_token"] == "new-refresh-token"


def test_jwt_refresh_invalid_token_rejected(mock_supabase_refresh: MagicMock) -> None:
    """The /auth/refresh endpoint should reject an invalid refresh token."""
    mock_supabase_refresh.side_effect = Exception("Invalid Refresh Token: Refresh Token Not Found")

    response = client.post("/auth/refresh", json={"refresh_token": "bad-refresh-token"})

    assert response.status_code == 401
    assert "Invalid or expired refresh token" in response.json()["detail"]