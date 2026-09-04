"""Tests for backend/app/risk/risk_rules.py

Covers:
    test_lookup_returns_rule_for_known_action
    test_lookup_returns_none_for_unknown_action
    test_lookup_caches_after_first_call
    test_invalidate_cache_forces_reload
    test_all_10_seed_rows_are_reachable
    test_risk_rule_is_immutable
    test_migration_has_no_user_insert_policy  (structural SQL check)
    test_migration_has_10_seed_inserts        (structural SQL check)
"""

from __future__ import annotations

import re
import unittest.mock as mock
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: patch supabase client before importing anything that touches it
# ---------------------------------------------------------------------------
with mock.patch("app.db.supabase_client.create_client"):
    from app.risk.risk_rules import RiskRule, invalidate_cache, lookup

# ---------------------------------------------------------------------------
# Canonical seed rows (mirrors Section 2.2 of the D12 spec)
# ---------------------------------------------------------------------------

SEED_ROWS: list[tuple[str, str]] = [
    ("calendar.list_events", "calendar"),
    ("calendar.create_event_internal_only", "calendar"),
    ("calendar.create_event_external_attendee", "calendar"),
    ("calendar.delete_event", "calendar"),
    ("gmail.create_draft", "gmail"),
    ("gmail.send_message", "gmail"),
    ("github.create_issue", "github"),
    ("github.comment_on_issue", "github"),
    ("slack.post_message_dm", "slack"),
    ("slack.post_message_channel", "slack"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_rows() -> list[dict]:
    """Build a fake DB result matching all 10 seed rows."""
    tier_map = {
        "calendar.list_events": ("low", False),
        "calendar.create_event_internal_only": ("medium", False),
        "calendar.create_event_external_attendee": ("high", True),
        "calendar.delete_event": ("high", True),
        "gmail.create_draft": ("low", False),
        "gmail.send_message": ("high", True),
        "github.create_issue": ("medium", False),
        "github.comment_on_issue": ("medium", False),
        "slack.post_message_dm": ("medium", False),
        "slack.post_message_channel": ("high", True),
    }
    rows = []
    for (action_type, mcp_server), (tier, approval) in zip(
        SEED_ROWS, [tier_map[at] for at, _ in SEED_ROWS]
    ):
        rows.append(
            {
                "action_type": action_type,
                "mcp_server": mcp_server,
                "risk_tier": tier,
                "requires_approval": approval,
                "rationale": "test rationale",
            }
        )
    return rows


@pytest.fixture(autouse=True)
def reset_cache():
    """Ensure a clean cache before every test."""
    invalidate_cache()
    yield
    invalidate_cache()


def _patch_supabase(rows: list[dict]):
    """Return a context manager that patches the supabase singleton's table query."""
    mock_result = MagicMock()
    mock_result.data = rows

    mock_execute = MagicMock(return_value=mock_result)
    mock_select = MagicMock()
    mock_select.execute = mock_execute
    mock_table = MagicMock()
    mock_table.select = MagicMock(return_value=mock_select)

    return patch("app.risk.risk_rules.supabase"), mock_table, mock_execute


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLookupKnownAction:
    """test_lookup_returns_rule_for_known_action"""

    def test_gmail_send_message_is_high_requires_approval(self):
        mock_result = MagicMock()
        mock_result.data = _make_mock_rows()
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute.return_value = mock_result

        with patch("app.risk.risk_rules.supabase", mock_sb):
            rule = lookup("gmail.send_message", "gmail")

        assert rule is not None
        assert isinstance(rule, RiskRule)
        assert rule.risk_tier == "high"
        assert rule.requires_approval is True

    def test_calendar_list_events_is_low_no_approval(self):
        mock_result = MagicMock()
        mock_result.data = _make_mock_rows()
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute.return_value = mock_result

        with patch("app.risk.risk_rules.supabase", mock_sb):
            rule = lookup("calendar.list_events", "calendar")

        assert rule is not None
        assert rule.risk_tier == "low"
        assert rule.requires_approval is False


class TestLookupUnknownAction:
    """test_lookup_returns_none_for_unknown_action"""

    def test_unknown_action_returns_none(self):
        mock_result = MagicMock()
        mock_result.data = _make_mock_rows()
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute.return_value = mock_result

        with patch("app.risk.risk_rules.supabase", mock_sb):
            result = lookup("calendar.summon_dragon", "calendar")

        assert result is None

    def test_wrong_mcp_server_returns_none(self):
        """gmail.send_message on mcp_server='calendar' has no row."""
        mock_result = MagicMock()
        mock_result.data = _make_mock_rows()
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute.return_value = mock_result

        with patch("app.risk.risk_rules.supabase", mock_sb):
            result = lookup("gmail.send_message", "calendar")

        assert result is None


class TestCaching:
    """test_lookup_caches_after_first_call  /  test_invalidate_cache_forces_reload"""

    def test_supabase_called_once_for_multiple_lookups(self):
        mock_result = MagicMock()
        mock_result.data = _make_mock_rows()
        mock_execute = MagicMock(return_value=mock_result)
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute = mock_execute

        with patch("app.risk.risk_rules.supabase", mock_sb):
            lookup("gmail.send_message", "gmail")
            lookup("calendar.list_events", "calendar")
            lookup("github.create_issue", "github")

        assert mock_execute.call_count == 1, (
            "Supabase should be hit exactly once; subsequent lookups use the cache"
        )

    def test_invalidate_cache_forces_reload(self):
        mock_result = MagicMock()
        mock_result.data = _make_mock_rows()
        mock_execute = MagicMock(return_value=mock_result)
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute = mock_execute

        with patch("app.risk.risk_rules.supabase", mock_sb):
            lookup("gmail.send_message", "gmail")  # populates cache
            invalidate_cache()
            lookup("gmail.send_message", "gmail")  # must hit DB again

        assert mock_execute.call_count == 2, (
            "After invalidate_cache(), the next lookup must re-query Supabase"
        )


class TestAllSeedRowsReachable:
    """test_all_10_seed_rows_are_reachable"""

    @pytest.mark.parametrize("action_type,mcp_server", SEED_ROWS)
    def test_seed_row_is_reachable(self, action_type: str, mcp_server: str):
        mock_result = MagicMock()
        mock_result.data = _make_mock_rows()
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.execute.return_value = mock_result

        with patch("app.risk.risk_rules.supabase", mock_sb):
            rule = lookup(action_type, mcp_server)

        assert rule is not None, (
            f"lookup({action_type!r}, {mcp_server!r}) returned None - "
            "seed row is missing from the mock or the cache key is wrong"
        )
        assert rule.action_type == action_type
        assert rule.mcp_server == mcp_server
        assert rule.risk_tier in ("low", "medium", "high")
        assert isinstance(rule.requires_approval, bool)


class TestImmutability:
    """test_risk_rule_is_immutable"""

    def test_frozen_dataclass_raises_on_mutation(self):
        rule = RiskRule(
            action_type="gmail.send_message",
            mcp_server="gmail",
            risk_tier="high",
            requires_approval=True,
            rationale="test",
        )
        with pytest.raises(FrozenInstanceError):
            rule.risk_tier = "low"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Structural tests - inspect the migration SQL directly
# ---------------------------------------------------------------------------

MIGRATION_PATH = (
    Path(__file__).parent.parent.parent / "migrations" / "20260905000008_create_risk_rules.sql"
)


class TestMigrationSQL:
    """Structural checks that do not require a live DB."""

    def test_migration_file_exists(self):
        assert MIGRATION_PATH.exists(), f"Migration file not found: {MIGRATION_PATH}"

    def test_migration_has_no_insert_policy_for_client_role(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        # There should be NO 'for insert' policy (client must be blocked)
        assert "for insert" not in sql, (
            "Migration must NOT create an INSERT policy - "
            "risk_rules is service-role-only for writes"
        )

    def test_migration_has_exactly_10_seed_value_groups(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        # Count the number of opening parentheses that begin a VALUES tuple
        # Each seed row starts with a newline + 4-space indent + '('
        value_groups = re.findall(r"^\s+\(", sql, re.MULTILINE)
        # We expect exactly 10 rows in the INSERT block.
        assert len(value_groups) == 10, f"Expected 10 seed rows, found {len(value_groups)}"

    def test_migration_has_on_conflict_clause(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        assert "on conflict" in sql, "Migration must use ON CONFLICT DO NOTHING to be idempotent"

    def test_migration_enables_rls(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        assert "enable row level security" in sql

    def test_migration_has_unique_constraint(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        assert "unique" in sql, (
            "Migration must declare a UNIQUE constraint on (action_type, mcp_server)"
        )

    def test_migration_has_risk_tier_check(self):
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        assert "risk_tier" in sql and "check" in sql
