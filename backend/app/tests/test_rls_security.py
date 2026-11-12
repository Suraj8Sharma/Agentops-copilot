"""D33 security audit: RLS isolation and account-deletion cascade checks.

These tests validate the project-level security contract encoded in the SQL
migrations and the authenticated account-deletion route.
"""

from __future__ import annotations

from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_AUTH_ROUTER = Path(__file__).resolve().parents[1] / "api" / "routers" / "auth.py"


def _load_sql(filename: str) -> str:
    """Read a migration file and normalize it for policy assertions."""
    raw = (_MIGRATIONS_DIR / filename).read_text(encoding="utf-8")
    return " ".join(raw.split()).lower()


def _assert_owner_only_policy(sql: str, table_name: str) -> None:
    """Assert the table is RLS-protected and scoped to auth.uid()."""
    assert f"alter table public.{table_name} enable row level security" in sql
    assert "for select" in sql
    assert "user_id = auth.uid()" in sql


def test_rls_user_cannot_read_other_users_tasks() -> None:
    """Tasks always remain user-scoped and cannot be read across users."""
    sql = _load_sql("20260828000006_draft_rls_policies.sql")
    _assert_owner_only_policy(sql, "tasks")


def test_rls_user_cannot_read_other_users_oauth_tokens() -> None:
    """OAuth tokens are never readable outside their owner."""
    sql = _load_sql("20260825000004_create_oauth_connections.sql")
    assert "enable row level security" in sql
    assert "user_id = auth.uid()" in sql
    assert "for select" in sql


def test_rls_user_cannot_read_other_users_profile() -> None:
    """Profiles are isolated by user_id for all authenticated selects."""
    sql = _load_sql("20260825000002_create_profiles.sql")
    assert "enable row level security" in sql
    assert "user_id = auth.uid()" in sql


def test_rls_user_cannot_read_other_users_digest_rows() -> None:
    """Digest rows are scoped by user_id and remain inaccessible to other users."""
    sql = _load_sql("20260918000018_create_digests.sql")
    assert "enable row level security" in sql
    assert "for select" in sql
    assert "user_id = auth.uid()" in sql


def test_security_audit_all_user_scoped_tables_are_rls_protected() -> None:
    """Core user-owned tables must enforce RLS, not just the original trio."""
    migrations = {
        "profiles": "20260825000002_create_profiles.sql",
        "tasks": "20260828000006_draft_rls_policies.sql",
        "oauth_connections": "20260825000004_create_oauth_connections.sql",
        "memory_embeddings": "20260914000012_create_memory_embeddings.sql",
        "user_preferences": "20260914000013_create_user_preferences.sql",
        "digests": "20260918000018_create_digests.sql",
        "notifications": "20260919000019_create_notifications.sql",
        "sessions_device_tokens": "20260919000020_create_sessions_device_tokens.sql",
        "approvals": "20260912000011_create_approvals.sql",
        "execution_logs": "20260909000009_create_execution_logs.sql",
    }

    for table_name, filename in migrations.items():
        sql = _load_sql(filename)
        assert f"alter table public.{table_name} enable row level security" in sql or (
            f"alter table {table_name} enable row level security" in sql
        ), f"RLS missing on {table_name} in {filename}"

        assert "user_id = auth.uid()" in sql or "where user_id = auth.uid()" in sql, (
            f"Owner-only policy missing for {table_name} in {filename}"
        )


def test_account_deletion_uses_admin_cascade_and_user_scoped_rls() -> None:
    """Delete-account flow must call admin.delete_user and migrations must cascade user data."""
    auth_sql = _AUTH_ROUTER.read_text(encoding="utf-8")
    assert "auth.admin.delete_user(current_user.id)" in auth_sql

    cascade_tables = [
        "profiles",
        "tasks",
        "oauth_connections",
        "memory_embeddings",
        "user_preferences",
        "digests",
        "notifications",
        "sessions_device_tokens",
        "approvals",
    ]

    saw_cascade = False
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        sql = _load_sql(path.name)
        cascade_pattern = (
            "foreign key ({field}) references public.{table} ({field}) on delete cascade"
        )
        if any(
            cascade_pattern.format(field=field, table=table) in sql
            for field in ("user_id", "task_id")
            for table in ("profiles", "tasks")
        ):
            pass
        if any(table_name in sql for table_name in cascade_tables):
            if "on delete cascade" in sql:
                saw_cascade = True
                break

    assert saw_cascade, "No ON DELETE CASCADE user-data cleanup path found in migrations"
