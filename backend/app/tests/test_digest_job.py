"""Tests for the digest generation job — D23.

Covers:
    test_digest_job_writes_row_for_user_with_completed_tasks
        Given completed tasks in a window, asserts a digests row is inserted
        with the correct user_id, period_type, and tasks_included.

    test_digest_job_skips_user_with_no_completed_tasks_in_window
        Given zero completed tasks in the window, asserts NO digest row is
        inserted (empty-digest guard).

    test_digest_job_returns_count_of_rows_written
        Verifies the return value equals the number of digest rows inserted.

    test_build_summary_formats_correctly
        Unit-tests the deterministic template builder directly.

    test_build_summary_truncates_long_input
        Verifies long raw_input values are truncated to ~40 chars.

All tests mock the Supabase client — no real network calls, no DB touched.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from app.jobs.digest_job import _build_summary, run_digest_job

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WINDOW_START = datetime(2026, 9, 17, 0, 0, 0, tzinfo=timezone.utc)
_WINDOW_END = datetime(2026, 9, 18, 0, 0, 0, tzinfo=timezone.utc)

_USER_A = "aaaaaaaa-0000-0000-0000-000000000001"
_USER_B = "bbbbbbbb-0000-0000-0000-000000000002"
_TASK_1 = "cccccccc-0000-0000-0000-000000000003"
_TASK_2 = "dddddddd-0000-0000-0000-000000000004"

_COMPLETED_TASKS = [
    {"id": _TASK_1, "user_id": _USER_A, "raw_input": "Push hotfix to prod"},
    {"id": _TASK_2, "user_id": _USER_A, "raw_input": "Review open PRs"},
]

_MULTI_USER_TASKS = [
    {"id": _TASK_1, "user_id": _USER_A, "raw_input": "Push hotfix to prod"},
    {"id": _TASK_2, "user_id": _USER_B, "raw_input": "Review open PRs"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_query_result(data: list[dict]) -> MagicMock:
    """Return a mock that looks like a supabase-py QueryResponse."""
    result = MagicMock()
    result.data = data
    return result


def _make_supabase_mock(query_data: list[dict]) -> MagicMock:
    """Return a mock supabase client where table().select()...execute() returns query_data."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.insert.return_value = chain
    chain.execute.return_value = _make_query_result(query_data)

    mock_sb = MagicMock()
    mock_sb.table.return_value = chain
    return mock_sb, chain


# ---------------------------------------------------------------------------
# _build_summary unit tests
# ---------------------------------------------------------------------------


def test_build_summary_formats_correctly() -> None:
    """Deterministic template: '{n} tasks completed: snippet1, snippet2'."""
    tasks = [
        {"raw_input": "Push hotfix to prod"},
        {"raw_input": "Review open PRs"},
    ]
    summary = _build_summary(tasks)
    assert summary == "2 tasks completed: Push hotfix to prod, Review open PRs"


def test_build_summary_truncates_long_input() -> None:
    """raw_input longer than 40 chars is truncated with an ellipsis."""
    long_input = "A" * 60
    tasks = [{"raw_input": long_input}]
    summary = _build_summary(tasks)
    assert "A" * 40 + "…" in summary
    assert len(summary) < 60 + 30  # well under untruncated length


def test_build_summary_handles_none_input() -> None:
    """Tasks with no raw_input get a '(no input)' placeholder."""
    tasks = [{"raw_input": None}]
    summary = _build_summary(tasks)
    assert "(no input)" in summary


def test_build_summary_singular_grammar() -> None:
    """Single task uses 'task' not 'tasks'."""
    tasks = [{"raw_input": "Deploy service"}]
    summary = _build_summary(tasks)
    assert summary.startswith("1 task completed")


# ---------------------------------------------------------------------------
# run_digest_job tests
# ---------------------------------------------------------------------------


def test_digest_job_writes_row_for_user_with_completed_tasks() -> None:
    """Given completed tasks in the window, one digest row is inserted per user."""
    mock_sb, chain = _make_supabase_mock(_COMPLETED_TASKS)

    # Second call to execute() (the INSERT) should also succeed
    insert_result = MagicMock()
    insert_result.data = [{"id": "new-digest-id"}]

    # execute() called twice: SELECT tasks, then INSERT digest
    chain.execute.side_effect = [
        _make_query_result(_COMPLETED_TASKS),  # SELECT
        insert_result,                          # INSERT
    ]

    with patch("app.jobs.digest_job.supabase", mock_sb):
        rows_written = run_digest_job("daily", _WINDOW_START, _WINDOW_END)

    assert rows_written == 1

    # Verify the INSERT was called with the right payload shape
    insert_calls = chain.insert.call_args_list
    assert len(insert_calls) == 1
    payload = insert_calls[0].args[0]
    assert payload["user_id"] == _USER_A
    assert payload["period_type"] == "daily"
    assert _TASK_1 in json.loads(payload["tasks_included"])
    assert _TASK_2 in json.loads(payload["tasks_included"])
    assert "2 tasks completed" in payload["summary_text"]


def test_digest_job_skips_user_with_no_completed_tasks_in_window() -> None:
    """If zero completed tasks are returned, no digest row is written."""
    mock_sb, chain = _make_supabase_mock([])

    with patch("app.jobs.digest_job.supabase", mock_sb):
        rows_written = run_digest_job("daily", _WINDOW_START, _WINDOW_END)

    assert rows_written == 0
    # INSERT must never have been called
    chain.insert.assert_not_called()


def test_digest_job_returns_count_of_rows_written() -> None:
    """run_digest_job returns the exact number of digest rows inserted."""
    mock_sb, chain = _make_supabase_mock(_MULTI_USER_TASKS)

    insert_result = MagicMock()
    insert_result.data = [{"id": "new-digest-id"}]

    chain.execute.side_effect = [
        _make_query_result(_MULTI_USER_TASKS),  # SELECT
        insert_result,                           # INSERT user A
        insert_result,                           # INSERT user B
    ]

    with patch("app.jobs.digest_job.supabase", mock_sb):
        rows_written = run_digest_job("weekly", _WINDOW_START, _WINDOW_END)

    # Two users → two digest rows
    assert rows_written == 2


def test_digest_job_writes_correct_period_type() -> None:
    """The period_type in the inserted row matches the argument passed."""
    mock_sb, chain = _make_supabase_mock(_COMPLETED_TASKS)

    insert_result = MagicMock()
    insert_result.data = [{"id": "new-id"}]
    chain.execute.side_effect = [
        _make_query_result(_COMPLETED_TASKS),
        insert_result,
    ]

    with patch("app.jobs.digest_job.supabase", mock_sb):
        run_digest_job("weekly", _WINDOW_START, _WINDOW_END)

    payload = chain.insert.call_args_list[0].args[0]
    assert payload["period_type"] == "weekly"


def test_digest_job_handles_db_query_failure_gracefully() -> None:
    """If the SELECT fails, job logs the error and returns 0 without crashing."""
    mock_sb = MagicMock()
    mock_sb.table.side_effect = Exception("DB connection lost")

    with patch("app.jobs.digest_job.supabase", mock_sb):
        rows_written = run_digest_job("daily", _WINDOW_START, _WINDOW_END)

    assert rows_written == 0
