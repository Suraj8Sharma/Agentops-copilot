"""RLS policy definition checks — D27 §4.3

Spec: D27 §4.3 — RLS isolation (4 tests)
Manual: §14, §7 Group D (RLS)

Strategy
--------
These tests read the migration SQL files and assert the policy expressions
are written correctly. They do NOT require a live Supabase connection.

This proves the policies are defined as intended. Runtime two-user isolation
testing (proving one user cannot read another user's rows via a live DB) is
deferred to the optional Week-5 upgrade.

Helper: SQL is stripped of -- comments, whitespace-collapsed, and lowercased
before matching, so minor formatting changes do not break assertions.
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


def _load_sql(filename: str) -> str:
    """Load a migration file, strip line comments, collapse whitespace, lowercase."""
    path = _MIGRATIONS_DIR / filename
    assert path.exists(), f"Migration file not found: {path}"
    raw = path.read_text(encoding="utf-8")
    # Remove SQL line comments
    no_comments = re.sub(r"--[^\n]*", " ", raw)
    # Collapse whitespace
    collapsed = re.sub(r"\s+", " ", no_comments)
    return collapsed.lower().strip()


def _contains(sql: str, pattern: str) -> bool:
    """Case-insensitive substring check (sql is already lowercased)."""
    return pattern.lower() in sql


# ---------------------------------------------------------------------------
# Migration filenames
# ---------------------------------------------------------------------------

_OAUTH_MIGRATION = "20260825000004_create_oauth_connections.sql"
_RLS_MIGRATION = "20260828000006_draft_rls_policies.sql"

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_rls_enabled_on_oauth_connections() -> None:
    """oauth_connections must have RLS enabled (enable row level security present).

    Without this, all RLS policies are ignored and every user can read every row.
    """
    sql = _load_sql(_OAUTH_MIGRATION)

    assert _contains(sql, "enable row level security"), (
        f"Expected 'enable row level security' in {_OAUTH_MIGRATION}; "
        "RLS policies are useless without it."
    )


def test_oauth_connections_select_policy_is_owner_only() -> None:
    """The SELECT policy on oauth_connections must restrict to user_id = auth.uid().

    This ensures a user can only read their own OAuth connection rows.
    """
    sql = _load_sql(_OAUTH_MIGRATION)

    # Must have a SELECT policy
    assert _contains(sql, "for select"), f"No SELECT policy found in {_OAUTH_MIGRATION}"

    # The policy expression must be owner-only
    assert _contains(sql, "user_id = auth.uid()"), (
        f"SELECT policy must use 'user_id = auth.uid()' in {_OAUTH_MIGRATION}"
    )


def test_oauth_connections_no_insert_policy_for_authenticated() -> None:
    """oauth_connections must NOT have an INSERT policy for the authenticated role.

    INSERT is service-role only — the backend writes tokens after the OAuth
    callback. A client-side INSERT policy would allow any authenticated user
    to write arbitrary token rows, bypassing the callback flow.

    Also asserts no 'for all' policy exists, since 'for all' implicitly
    includes INSERT.
    """
    sql = _load_sql(_OAUTH_MIGRATION)

    # No INSERT policy should exist (service-role bypasses RLS entirely)
    assert not _contains(sql, "for insert"), (
        f"oauth_connections must NOT have a client-facing INSERT policy in {_OAUTH_MIGRATION}. "
        "INSERT must be service-role only."
    )

    # No 'for all' policy either (it silently includes INSERT)
    assert not _contains(sql, "for all"), (
        f"oauth_connections must NOT have a 'for all' policy in {_OAUTH_MIGRATION}. "
        "'for all' implicitly grants INSERT to authenticated users."
    )


def test_tasks_select_policy_is_owner_only() -> None:
    """The SELECT policy on tasks must restrict to user_id = auth.uid().

    Tasks contain the user's agent instructions and plan outputs —
    cross-user reads would be a critical data leak.
    """
    sql = _load_sql(_RLS_MIGRATION)

    # Must have a SELECT policy for tasks
    assert _contains(sql, "tasks_owner_select"), (
        f"No tasks_owner_select policy found in {_RLS_MIGRATION}"
    )

    # The policy expression must be owner-only
    # We check the tasks block specifically by confirming the pattern appears
    # after the 'tasks' table section heading
    tasks_block_start = sql.find("tasks")
    assert tasks_block_start != -1, f"'tasks' not found in {_RLS_MIGRATION}"

    tasks_section = sql[tasks_block_start:]
    assert _contains(tasks_section, "user_id = auth.uid()"), (
        f"tasks SELECT policy must use 'user_id = auth.uid()' in {_RLS_MIGRATION}"
    )
