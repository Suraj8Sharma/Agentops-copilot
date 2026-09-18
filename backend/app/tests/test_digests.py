"""Tests for GET /digests — D23.

Covers:
    test_get_digests_returns_only_callers_rows
        Authenticated user gets their own digest rows, newest-first.

    test_get_digests_filters_by_period_type
        period_type=daily query param is passed through to the DB filter.

    test_get_digests_rejects_unauthenticated_request
        Missing JWT → 401.

    test_get_digests_pagination_params
        limit + offset are forwarded to the query.

    test_get_digests_returns_empty_list_when_no_digests
        User with no digest rows gets 200 + empty list (not 404).

All tests mock the Supabase client — no real network calls.
"""

from __future__ import annotations

import unittest.mock as mock
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Bootstrap: patch supabase client before importing the app
# ---------------------------------------------------------------------------
with (
    mock.patch("app.db.supabase_client.create_client"),
    mock.patch("app.db.supabase_client.probe_connection"),
):
    from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_AUTH_HEADER = {"Authorization": "Bearer valid.jwt.token"}
_USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_OTHER_USER_ID = "bbbbbbbb-0000-0000-0000-000000000002"
_DIGEST_ID = "eeeeeeee-0000-0000-0000-000000000005"

_SAMPLE_DIGEST: dict[str, Any] = {
    "id": _DIGEST_ID,
    "user_id": _USER_ID,
    "period_type": "daily",
    "summary_text": "2 tasks completed: Push hotfix to prod, Review open PRs",
    "tasks_included": ["cccccccc-0000-0000-0000-000000000003"],
    "generated_at": "2026-09-18T08:00:00+00:00",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_current_user(user_id: str = _USER_ID) -> MagicMock:
    """Mock that looks like a Supabase auth.get_user() response."""
    user = MagicMock()
    user.id = user_id
    user.email = "test@example.com"
    user.role = "authenticated"
    resp = MagicMock()
    resp.user = user
    return resp


def _make_db_result(data: list[dict], count: int | None = None) -> MagicMock:
    """Mock that looks like a supabase-py QueryResponse."""
    result = MagicMock()
    result.data = data
    result.count = count
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_auth():
    """Patch supabase.auth.get_user so JWT verification always succeeds."""
    with patch("app.core.security.supabase.auth.get_user") as m:
        m.return_value = _make_current_user()
        yield m


@pytest.fixture
def mock_table():
    """Patch the supabase singleton inside the digests router."""
    with patch("app.api.routers.digests.supabase") as mock_sb:
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.range.return_value = chain
        mock_sb.table.return_value = chain
        yield mock_sb, chain


# ---------------------------------------------------------------------------
# GET /digests
# ---------------------------------------------------------------------------


def test_get_digests_returns_only_callers_rows(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """Authenticated user receives their own digest rows with correct shape."""
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([_SAMPLE_DIGEST], count=1)

    response = client.get("/digests", headers=_AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["digests"]) == 1
    assert body["digests"][0]["id"] == _DIGEST_ID
    assert body["digests"][0]["user_id"] == _USER_ID
    assert body["digests"][0]["period_type"] == "daily"


def test_get_digests_returns_empty_list_when_no_digests(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """User with no digest rows gets 200 + empty list, not 404."""
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([], count=0)

    response = client.get("/digests", headers=_AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert body["digests"] == []
    assert body["total"] == 0


def test_get_digests_filters_by_period_type(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """period_type=weekly query param is forwarded to the DB as an eq filter."""
    _, chain = mock_table
    weekly_digest = {**_SAMPLE_DIGEST, "period_type": "weekly"}
    chain.execute.return_value = _make_db_result([weekly_digest], count=1)

    response = client.get("/digests?period_type=weekly", headers=_AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert body["digests"][0]["period_type"] == "weekly"

    # Verify .eq("period_type", "weekly") was called on the chain
    eq_calls = [str(c) for c in chain.eq.call_args_list]
    assert any("weekly" in c for c in eq_calls)


def test_get_digests_rejects_invalid_period_type(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """Invalid period_type value → 422 Unprocessable Entity (FastAPI Literal validation)."""
    response = client.get("/digests?period_type=monthly", headers=_AUTH_HEADER)
    assert response.status_code == 422


def test_get_digests_rejects_unauthenticated_request(
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """Missing Authorization header → 401."""
    response = client.get("/digests")
    assert response.status_code == 401


def test_get_digests_pagination_params(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """limit and offset query params are reflected in the response envelope."""
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([], count=0)

    response = client.get("/digests?limit=5&offset=10", headers=_AUTH_HEADER)

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 5
    assert body["offset"] == 10

    # Verify .range(10, 14) was called (offset=10, offset+limit-1=14)
    chain.range.assert_called_once_with(10, 14)
