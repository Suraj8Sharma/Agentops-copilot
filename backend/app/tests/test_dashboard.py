"""Tests for GET /dashboard/metrics — D30.

Covers:
- Unauthenticated access returns 401.
- Empty database tables return safe default zero-series matching Flutter empty state.
- Aggregation of p95 latency from llm_usage_logs (in seconds).
- Calculation of token cost across Groq and Gemini calls.
- Calculation of accuracy from eval_runs pass/fail counts.
- Tracking of rate-limit fallback events.
- Custom days parameter support.
- Resilience against DB query failures.
"""

from __future__ import annotations

import unittest.mock as mock
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Bootstrap: patch supabase before importing app
# ---------------------------------------------------------------------------
with (
    mock.patch("app.db.supabase_client.create_client"),
    mock.patch("app.db.supabase_client.probe_connection"),
):
    from app.main import app

client = TestClient(app)

_AUTH_HEADER = {"Authorization": "Bearer valid.jwt.token"}
_USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------


def _make_current_user(user_id: str = _USER_ID) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = "suraj@agentops.dev"
    user.role = "authenticated"
    resp = MagicMock()
    resp.user = user
    return resp


@pytest.fixture
def mock_auth():
    """Patch supabase.auth.get_user so JWT verification succeeds."""
    with patch("app.core.security.supabase.auth.get_user") as m:
        m.return_value = _make_current_user()
        yield m


def _make_mock_supabase_admin(llm_data: list[dict], eval_data: list[dict]):
    """Creates a mock supabase_admin that returns llm_data or eval_data based on table name."""
    mock_client = MagicMock()

    def table_router(table_name: str):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.gte.return_value = chain
        chain.order.return_value = chain
        res = MagicMock()
        if table_name == "llm_usage_logs":
            res.data = llm_data
        elif table_name == "eval_runs":
            res.data = eval_data
        else:
            res.data = []
        chain.execute.return_value = res
        return chain

    mock_client.table.side_effect = table_router
    return mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_dashboard_metrics_unauthenticated_returns_401():
    """Request without Authorization header must return 401."""
    resp = client.get("/dashboard/metrics")
    assert resp.status_code == 401


def test_get_dashboard_metrics_empty_db_returns_safe_defaults(mock_auth):
    """When DB has zero rows, return 7 safe points of 0.0 without errors."""
    mock_sb = _make_mock_supabase_admin([], [])

    with patch("app.api.routers.dashboard.supabase_admin", mock_sb):
        resp = client.get("/dashboard/metrics", headers=_AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()

    assert "latency" in data
    assert "cost" in data
    assert "accuracy" in data
    assert "summary" in data
    assert "fallback_events" in data

    assert len(data["latency"]) == 7
    assert len(data["cost"]) == 7
    assert len(data["accuracy"]) == 7

    # All points default to 0.0 safely
    assert all(pt["value"] == 0.0 for pt in data["latency"])
    assert all(pt["value"] == 0.0 for pt in data["cost"])
    assert all(pt["value"] == 0.0 for pt in data["accuracy"])

    summary = data["summary"]
    assert summary["p95_latency"] == 0.0
    assert summary["total_cost"] == 0.0
    assert summary["avg_accuracy"] == 0.0
    assert summary["fallback_events_count"] == 0
    assert data["fallback_events"] == 0


def test_get_dashboard_metrics_aggregates_latency_p95(mock_auth):
    """Latency in seconds and p95 across the window are computed accurately."""
    now = datetime.now(timezone.utc)
    today_iso = now.isoformat()

    # Latencies in ms: 1000ms (1.0s), 2000ms (2.0s), 5000ms (5.0s)
    llm_rows = [
        {
            "created_at": today_iso,
            "latency_ms": 1000,
            "tokens_in": 100,
            "tokens_out": 50,
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
            "rate_limit_hit": False,
        },
        {
            "created_at": today_iso,
            "latency_ms": 2000,
            "tokens_in": 200,
            "tokens_out": 100,
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
            "rate_limit_hit": False,
        },
        {
            "created_at": today_iso,
            "latency_ms": 5000,
            "tokens_in": 500,
            "tokens_out": 250,
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
            "rate_limit_hit": False,
        },
    ]

    mock_sb = _make_mock_supabase_admin(llm_rows, [])

    with patch("app.api.routers.dashboard.supabase_admin", mock_sb):
        resp = client.get("/dashboard/metrics", headers=_AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()

    # For 3 values [1.0, 2.0, 5.0], ceil(3 * 0.95) - 1 = 3 - 1 = index 2 -> 5.0s
    summary = data["summary"]
    assert summary["p95_latency"] == 5.0
    # Today's point should also show 5.0
    today_pt = data["latency"][-1]
    assert today_pt["value"] == 5.0


def test_get_dashboard_metrics_calculates_cost_and_fallback(mock_auth):
    """Tokens are translated to cost based on model rates, and fallback events counted."""
    now = datetime.now(timezone.utc)
    today_iso = now.isoformat()

    # Groq llama-3.3-70b-versatile: 0.59 / 1M input, 0.79 / 1M output
    # 1,000,000 in, 1,000,000 out -> $0.59 + $0.79 = $1.38
    llm_rows = [
        {
            "created_at": today_iso,
            "latency_ms": 800,
            "tokens_in": 1_000_000,
            "tokens_out": 1_000_000,
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "rate_limit_hit": False,
        },
        {
            "created_at": today_iso,
            "latency_ms": 1200,
            "tokens_in": 500_000,
            "tokens_out": 500_000,
            "provider": "gemini",
            "model": "gemini-1.5-flash",
            "rate_limit_hit": True,  # Fallback event!
        },
    ]

    mock_sb = _make_mock_supabase_admin(llm_rows, [])

    with patch("app.api.routers.dashboard.supabase_admin", mock_sb):
        resp = client.get("/dashboard/metrics", headers=_AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()

    # Groq cost = $1.38
    # Gemini flash (0.075 in, 0.30 out per 1M): 0.5 * 0.075 + 0.5 * 0.30 = 0.0375 + 0.15 = 0.1875
    # Total = 1.38 + 0.1875 = 1.5675 -> rounded to 1.57
    assert data["summary"]["total_cost"] == 1.57
    assert data["cost"][-1]["value"] == 1.57
    assert data["summary"]["fallback_events_count"] == 1
    assert data["fallback_events"] == 1


def test_get_dashboard_metrics_calculates_accuracy_from_eval_runs(mock_auth):
    """Eval runs pass_count and fail_count are converted into accuracy percentage."""
    now = datetime.now(timezone.utc)
    today_iso = now.isoformat()

    eval_rows = [
        {
            "run_date": today_iso,
            "suite_name": "planner_eval",
            "pass_count": 90,
            "fail_count": 10,
            "avg_latency_ms": 1500,
        },
        {
            "run_date": today_iso,
            "suite_name": "router_eval",
            "pass_count": 95,
            "fail_count": 5,
            "avg_latency_ms": 800,
        },
    ]

    mock_sb = _make_mock_supabase_admin([], eval_rows)

    with patch("app.api.routers.dashboard.supabase_admin", mock_sb):
        resp = client.get("/dashboard/metrics", headers=_AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()

    # Total passes = 185, total cases = 200 -> 185 / 200 = 92.5%
    assert data["summary"]["avg_accuracy"] == 92.5
    assert data["accuracy"][-1]["value"] == 92.5


def test_get_dashboard_metrics_custom_days_param(mock_auth):
    """days query parameter controls the length of the time series."""
    mock_sb = _make_mock_supabase_admin([], [])

    with patch("app.api.routers.dashboard.supabase_admin", mock_sb):
        resp = client.get("/dashboard/metrics?days=14", headers=_AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()

    assert len(data["latency"]) == 14
    assert len(data["cost"]) == 14
    assert len(data["accuracy"]) == 14


def test_get_dashboard_metrics_handles_db_error_gracefully(mock_auth):
    """If DB queries fail, the endpoint returns safe empty metrics rather than 500."""
    mock_sb = MagicMock()
    mock_sb.table.side_effect = RuntimeError("Database connection timed out")

    with patch("app.api.routers.dashboard.supabase_admin", mock_sb):
        resp = client.get("/dashboard/metrics", headers=_AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["latency"]) == 7
    assert data["summary"]["total_cost"] == 0.0
