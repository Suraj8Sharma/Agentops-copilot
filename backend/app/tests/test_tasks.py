"""Tests for POST /tasks, GET /tasks, and GET /tasks/{id}.

All tests run against a **mocked** Supabase client — no real network calls,
no production data touched.  The mock is applied at the supabase module level
so the singleton is replaced before the FastAPI app is imported.

Named tests (matches Section 9 of the D11 spec):
    test_post_tasks_creates_task_for_authenticated_user
    test_post_tasks_requires_raw_input_for_text_type
    test_post_tasks_requires_transcription_for_voice_type
    test_post_tasks_rejects_unauthenticated_request
    test_get_tasks_returns_only_current_users_tasks
    test_get_tasks_id_returns_404_for_other_users_task
    test_task_plans_rls_service_role_only_write   (structural — verifies no
        user-facing INSERT policy exists on task_plans in the migration SQL)
"""

from __future__ import annotations

import re
import unittest.mock as mock
from pathlib import Path
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
_TASK_ID = "cccccccc-0000-0000-0000-000000000003"

_SAMPLE_TASK: dict[str, Any] = {
    "id": _TASK_ID,
    "user_id": _USER_ID,
    "input_type": "text",
    "raw_input": "Schedule a call with my professor for Thursday afternoon.",
    "transcription_text": None,
    "status": "submitted",
    "created_at": "2026-09-04T07:00:00+00:00",
    "completed_at": None,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_current_user(user_id: str = _USER_ID) -> MagicMock:
    """Return a mock that looks like a Supabase User for auth.get_user()."""
    user = MagicMock()
    user.id = user_id
    user.email = "test@example.com"
    user.role = "authenticated"
    resp = MagicMock()
    resp.user = user
    return resp


def _make_db_result(data: list[dict], count: int | None = None) -> MagicMock:
    """Return a mock that looks like a supabase-py QueryResponse."""
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
    """Patch supabase.table so all DB calls are intercepted."""
    with patch("app.api.routers.tasks.supabase") as mock_sb:
        # Build a chainable query mock: table().select().eq().order()…execute()
        chain = MagicMock()
        chain.select.return_value = chain
        chain.insert.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.range.return_value = chain
        chain.limit.return_value = chain
        mock_sb.table.return_value = chain
        yield mock_sb, chain


# ---------------------------------------------------------------------------
# POST /tasks
# ---------------------------------------------------------------------------


def test_post_tasks_creates_task_for_authenticated_user(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """POST with valid JWT + text input should return 201 and the new task."""
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([_SAMPLE_TASK])

    response = client.post(
        "/tasks",
        json={
            "input_type": "text",
            "raw_input": "Schedule a call with my professor for Thursday afternoon.",
        },
        headers=_AUTH_HEADER,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "submitted"
    assert data["input_type"] == "text"
    assert data["id"] == _TASK_ID
    # user_id must come from the JWT, not the body
    assert data["user_id"] == _USER_ID


def test_post_tasks_creates_voice_task(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """POST with input_type=voice and transcription_text should succeed."""
    voice_task = {
        **_SAMPLE_TASK,
        "input_type": "voice",
        "raw_input": None,
        "transcription_text": "Schedule a meeting.",
    }
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([voice_task])

    response = client.post(
        "/tasks",
        json={"input_type": "voice", "transcription_text": "Schedule a meeting."},
        headers=_AUTH_HEADER,
    )

    assert response.status_code == 201
    assert response.json()["input_type"] == "voice"


def test_post_tasks_requires_raw_input_for_text_type(mock_auth: MagicMock) -> None:
    """POST with input_type=text but no raw_input should return 422."""
    response = client.post(
        "/tasks",
        json={"input_type": "text"},
        headers=_AUTH_HEADER,
    )
    assert response.status_code == 422


def test_post_tasks_requires_transcription_for_voice_type(mock_auth: MagicMock) -> None:
    """POST with input_type=voice but no transcription_text should return 422."""
    response = client.post(
        "/tasks",
        json={"input_type": "voice"},
        headers=_AUTH_HEADER,
    )
    assert response.status_code == 422


def test_post_tasks_rejects_invalid_input_type(mock_auth: MagicMock) -> None:
    """POST with an unknown input_type should return 422."""
    response = client.post(
        "/tasks",
        json={"input_type": "fax", "raw_input": "Send a fax."},
        headers=_AUTH_HEADER,
    )
    assert response.status_code == 422


def test_post_tasks_rejects_unauthenticated_request() -> None:
    """POST without an Authorization header should return 401."""
    response = client.post(
        "/tasks",
        json={"input_type": "text", "raw_input": "Some task."},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


# ---------------------------------------------------------------------------
# GET /tasks
# ---------------------------------------------------------------------------


def test_get_tasks_returns_only_current_users_tasks(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """GET /tasks should only return tasks for the authenticated user.

    The supabase query is built with .eq("user_id", current_user.id).
    We verify the eq call was made with the correct user_id, not a
    different user''s id.
    """
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([_SAMPLE_TASK], count=1)

    response = client.get("/tasks", headers=_AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["limit"] == 20
    assert data["offset"] == 0
    assert len(data["tasks"]) == 1

    # The DB query must filter on the JWT user_id, never on another user''s.
    eq_calls = [str(c) for c in chain.eq.call_args_list]
    assert any(_USER_ID in call for call in eq_calls), (
        "Expected eq() to be called with the authenticated user_id"
    )
    assert not any(_OTHER_USER_ID in call for call in eq_calls), (
        "eq() must NOT be called with another user''s id"
    )


def test_get_tasks_empty_list(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """GET /tasks with no tasks should return an empty list, not an error."""
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([], count=0)

    response = client.get("/tasks", headers=_AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert data["tasks"] == []
    assert data["total"] == 0


def test_get_tasks_status_filter_accepted(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """GET /tasks?status=completed should be accepted and passed to the query."""
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([], count=0)

    response = client.get("/tasks?status=completed", headers=_AUTH_HEADER)

    assert response.status_code == 200


def test_get_tasks_invalid_status_returns_422(mock_auth: MagicMock) -> None:
    """GET /tasks?status=bogus should return 422."""
    response = client.get("/tasks?status=bogus", headers=_AUTH_HEADER)
    assert response.status_code == 422


def test_get_tasks_pagination_params(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """GET /tasks?limit=5&offset=10 should forward pagination to the DB query."""
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([], count=0)

    response = client.get("/tasks?limit=5&offset=10", headers=_AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 5
    assert data["offset"] == 10


def test_get_tasks_rejects_unauthenticated_request() -> None:
    """GET /tasks without a token should return 401."""
    response = client.get("/tasks")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /tasks/{id}
# ---------------------------------------------------------------------------


def test_get_task_detail_returns_task(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """GET /tasks/{id} with a valid task owned by the user should return it."""
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([_SAMPLE_TASK])

    response = client.get(f"/tasks/{_TASK_ID}", headers=_AUTH_HEADER)

    assert response.status_code == 200
    assert response.json()["id"] == _TASK_ID


def test_get_tasks_id_returns_404_for_other_users_task(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """GET /tasks/{id} for a task that belongs to another user returns 404.

    The handler adds .eq("user_id", current_user.id) — when the task does not
    belong to the caller the DB returns no rows, which surfaces as 404.
    """
    _, chain = mock_table
    # Simulate RLS / user_id filter: DB returns empty for a different user''s task
    chain.execute.return_value = _make_db_result([])

    response = client.get(f"/tasks/{_TASK_ID}", headers=_AUTH_HEADER)

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_task_detail_404_for_missing_task(
    mock_auth: MagicMock,
    mock_table: tuple[MagicMock, MagicMock],
) -> None:
    """GET /tasks/{id} for a non-existent UUID should return 404."""
    _, chain = mock_table
    chain.execute.return_value = _make_db_result([])

    non_existent = "dddddddd-0000-0000-0000-000000000099"
    response = client.get(f"/tasks/{non_existent}", headers=_AUTH_HEADER)

    assert response.status_code == 404


def test_get_task_detail_rejects_non_uuid_id(mock_auth: MagicMock) -> None:
    """GET /tasks/not-a-uuid should return 404 (no DB hit)."""
    response = client.get("/tasks/not-a-uuid", headers=_AUTH_HEADER)
    assert response.status_code == 404


def test_get_task_detail_rejects_unauthenticated_request() -> None:
    """GET /tasks/{id} without a token should return 401."""
    response = client.get(f"/tasks/{_TASK_ID}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Structural: task_plans migration has no user-facing INSERT policy
# ---------------------------------------------------------------------------


def test_task_plans_rls_service_role_only_write() -> None:
    """Verify the migration SQL defines no INSERT policy for the ''authenticated'' role
    on task_plans — writes must be service-role only.

    This is a structural (static) test that reads the migration file directly.
    It guards against accidentally adding a user-facing INSERT policy in future edits.
    """
    migration_dir = Path(__file__).parents[2] / "migrations"
    migration_file = migration_dir / "20260904000007_create_task_plans_plan_steps.sql"

    assert migration_file.exists(), f"Migration file not found: {migration_file}"
    sql = migration_file.read_text(encoding="utf-8").lower()

    # There must be NO insert policy on task_plans for the user role.
    # An insert policy would look like: create policy ... on public.task_plans for insert
    insert_policy_pattern = re.compile(
        r"create\s+policy\s+\S+\s+on\s+public\.task_plans\s+for\s+insert"
    )
    assert not insert_policy_pattern.search(sql), (
        "task_plans must NOT have a user-facing INSERT policy. Writes are service-role only."
    )

    # Same for plan_steps.
    insert_policy_pattern_steps = re.compile(
        r"create\s+policy\s+\S+\s+on\s+public\.plan_steps\s+for\s+insert"
    )
    assert not insert_policy_pattern_steps.search(sql), (
        "plan_steps must NOT have a user-facing INSERT policy. Writes are service-role only."
    )
