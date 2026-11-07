"""MCP Integration test suite for AgentOps Copilot.

Manual §14, §15.4 (D29, Suraj): MCP integration test suite.
Satisfies the failure handling, timeout, router, and resilience named tests:
  - test_mcp_server_timeout_handled_gracefully
  - test_mcp_server_down_marks_task_failed_not_hung

Also verifies cross-provider routing (Calendar, Gmail, GitHub, Slack),
idempotency guarantees, and approval gate safety for high-risk actions.

All external calls (Supabase, httpx) are mocked — 100% offline, zero live network/secrets.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import httpx

from app.agents.nodes import execute, route_step
from app.agents.state import Step
from app.mcp_clients import call_tool

TASK_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())
PLAN_ID = str(uuid.uuid4())
STEP_ID = str(uuid.uuid4())
IDEMPOTENCY_KEY = f"{PLAN_ID}:0"
GOOGLE_TOKEN = "ya29.test_valid_mcp_token"

REFRESH_PATCH = "app.mcp_clients.google_token_refresh.supabase_admin"
DB_CLIENT_PATCH = "app.db.supabase_client.supabase_admin"


def _make_state(
    plan: list[Step] | None = None,
    risk_flags: dict[int, Any] | None = None,
    error: str | None = None,
    plan_id: str = PLAN_ID,
) -> dict[str, Any]:
    """Build a minimal AgentState dict for execution node testing."""
    return {
        "task_id": TASK_ID,
        "user_id": USER_ID,
        "raw_input": "schedule an sync and notify team",
        "input_type": "text",
        "intent": "schedule_event",
        "plan": plan or [],
        "plan_id": plan_id,
        "risk_flags": risk_flags or {},
        "current_step_index": 0,
        "step_results": {},
        "retries": {},
        "error": error,
    }


def _make_supabase_mock(token: str = GOOGLE_TOKEN) -> MagicMock:
    """Build a mock Supabase client for execution logging and state updates."""
    mock = MagicMock()

    def table_side_effect(name: str):
        t = MagicMock()

        def select_side_effect(*args, **kwargs):
            s = MagicMock()
            s.eq.return_value = s
            s.limit.return_value = s
            s.execute.return_value = MagicMock(
                data=[
                    {
                        "access_token": token,
                        "refresh_token": None,
                        "expires_at": "2099-01-01T00:00:00+00:00",
                        "status": "active",
                    }
                ]
            )
            return s

        def update_side_effect(payload: dict[str, Any]):
            u = MagicMock()
            eq_mock = MagicMock()
            eq_mock.execute.return_value = MagicMock(data=[])
            u.eq.return_value = eq_mock
            return u

        def insert_side_effect(payload: dict[str, Any]):
            i = MagicMock()
            i.execute.return_value = MagicMock(data=[{"id": STEP_ID}])
            return i

        t.select.side_effect = select_side_effect
        t.update.side_effect = update_side_effect
        t.insert.side_effect = insert_side_effect
        return t

    mock.table.side_effect = table_side_effect
    return mock


# ---------------------------------------------------------------------------
# Manual §15.4 Named Test 8
# ---------------------------------------------------------------------------


def test_mcp_server_timeout_handled_gracefully():
    """Manual §15.4 named test: MCP call exceeding timeout returns clean error envelope.

    Asserts:
      - Traps httpx.TimeoutException without crashing or bubbling uncaught exception
      - Returns envelope with status: 'error' and error: 'timeout'
      - Records TIMEOUT error event in execution_logs
      - Latency is measured
    """
    mock_sb = MagicMock()
    inserted_logs = []

    def table_side_effect(name: str):
        t = MagicMock()
        if name == "execution_logs":

            def insert_log(payload: dict[str, Any]):
                inserted_logs.append(payload)
                i = MagicMock()
                i.execute.return_value = MagicMock(data=[{"id": str(uuid.uuid4())}])
                return i

            t.insert.side_effect = insert_log
        else:
            s = MagicMock()
            s.eq.return_value = s
            s.limit.return_value = s
            s.execute.return_value = MagicMock(
                data=[
                    {
                        "access_token": GOOGLE_TOKEN,
                        "refresh_token": None,
                        "expires_at": "2099-01-01T00:00:00+00:00",
                        "status": "active",
                    }
                ]
            )
            t.select.side_effect = lambda *a, **kw: s
        return t

    mock_sb.table.side_effect = table_side_effect

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_sb),
        patch(DB_CLIENT_PATCH, mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.post", side_effect=httpx.TimeoutException("Read timed out after 15s")),
    ):
        result = call_tool(
            tool_name="calendar.create_event_internal_only",
            mcp_server="calendar",
            input_params={"summary": "Hanging event", "start": {}, "end": {}},
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )

    assert result["status"] == "error"
    assert result["output"] is None
    assert result["error"] == "timeout"
    assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0

    # Verify execution_logs received error event
    timeout_logs = [
        log
        for log in inserted_logs
        if log.get("payload", {}).get("error_code") == "TIMEOUT"
        or log.get("payload", {}).get("message") == "timeout"
    ]
    assert len(timeout_logs) >= 1


# ---------------------------------------------------------------------------
# Manual §15.4 Named Test 9
# ---------------------------------------------------------------------------


def test_mcp_server_down_marks_task_failed_not_hung():
    """Manual §15.4 named test: downed MCP server marks task failed, never hangs.

    Asserts:
      - Execute loop attempts retries up to _MAX_RETRIES
      - Updates plan_steps.status = 'failed'
      - Updates tasks.status = 'failed' in database
      - Logs step_failed event in execution_logs
      - Returns {'error': 'step_failed'} immediately halting graph
    """
    step = Step(
        tool_name="calendar.create_event_internal_only",
        mcp_server="calendar",
        input_params={"summary": "Downed server test"},
    )
    state = _make_state(
        plan=[step],
        risk_flags={
            0: {"risk_tier": "medium", "requires_approval": False, "rationale": "auto-exec"}
        },
    )

    task_updates = []
    plan_step_updates = []
    execution_log_events = []

    mock_sb = MagicMock()

    def table_side_effect(name: str):
        t = MagicMock()
        if name == "tasks":

            def update_task(payload: dict[str, Any]):
                task_updates.append(payload)
                eq_mock = MagicMock()
                eq_mock.execute.return_value = MagicMock(data=[])
                return eq_mock

            t.update.side_effect = update_task
        elif name == "plan_steps":

            def update_step(payload: dict[str, Any]):
                plan_step_updates.append(payload)
                eq1 = MagicMock()
                eq2 = MagicMock()
                eq2.execute.return_value = MagicMock(data=[])
                eq1.eq.return_value = eq2
                return eq1

            t.update.side_effect = update_step
        elif name == "execution_logs":

            def insert_log(payload: dict[str, Any]):
                execution_log_events.append(payload.get("event_type"))
                i = MagicMock()
                i.execute.return_value = MagicMock(data=[{"id": str(uuid.uuid4())}])
                return i

            t.insert.side_effect = insert_log
        return t

    mock_sb.table.side_effect = table_side_effect

    # Downed MCP server response (HTTP 502 Bad Gateway)
    down_response = {
        "status": "error",
        "output": None,
        "error": "HTTP 502 Bad Gateway from provider",
        "latency_ms": 45,
    }

    with (
        patch("app.agents.nodes.supabase_admin", mock_sb),
        patch(DB_CLIENT_PATCH, mock_sb),
        patch("app.agents.nodes.call_tool", return_value=down_response) as mock_call,
        patch("time.sleep"),  # skip delay in tests
    ):
        result = execute(state)

    # 1. Verified retried max times (3 attempts)
    assert mock_call.call_count == 3

    # 2. Verified task marked failed
    assert any(upd.get("status") == "failed" for upd in task_updates)

    # 3. Verified plan_step marked failed
    assert any(upd.get("status") == "failed" for upd in plan_step_updates)

    # 4. Verified step_failed logged
    assert "step_failed" in execution_log_events

    # 5. Verified clean error return that halts graph rather than hanging
    assert result.get("error") == "step_failed"
    assert result["step_results"][0]["status"] == "error"


# ---------------------------------------------------------------------------
# Router & Cross-Provider Integration Tests
# ---------------------------------------------------------------------------


def test_call_tool_routes_all_supported_servers():
    """call_tool routes cleanly to calendar, gmail, github, and slack."""
    success_envelope = {
        "status": "success",
        "output": {"ok": True},
        "error": None,
        "latency_ms": 10,
    }

    with (
        patch("app.mcp_clients.calendar.call", return_value=success_envelope) as m_cal,
        patch("app.mcp_clients.gmail.call", return_value=success_envelope) as m_gmail,
        patch("app.mcp_clients.github.call", return_value=success_envelope) as m_gh,
        patch("app.mcp_clients.slack.call", return_value=success_envelope) as m_slack,
    ):
        # 1. Calendar
        res_cal = call_tool("calendar.list_events", "calendar", {}, USER_ID, "p:0", TASK_ID)
        assert res_cal["status"] == "success"
        m_cal.assert_called_once()

        # 2. Gmail
        res_gmail = call_tool("gmail.create_draft", "gmail", {}, USER_ID, "p:1", TASK_ID)
        assert res_gmail["status"] == "success"
        m_gmail.assert_called_once()

        # 3. GitHub
        res_gh = call_tool("github.list_issues", "github", {}, USER_ID, "p:2", TASK_ID)
        assert res_gh["status"] == "success"
        m_gh.assert_called_once()

        # 4. Slack
        res_slack = call_tool("slack.list_channels", "slack", {}, USER_ID, "p:3", TASK_ID)
        assert res_slack["status"] == "success"
        m_slack.assert_called_once()


def test_call_tool_unknown_mcp_server_returns_error():
    """call_tool returns error envelope immediately when provider is unknown."""
    result = call_tool(
        tool_name="notion.create_page",
        mcp_server="notion",
        input_params={"title": "Roadmap"},
        user_id=USER_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        task_id=TASK_ID,
    )

    assert result["status"] == "error"
    assert result["output"] is None
    assert "no MCP client registered for provider 'notion'" in result["error"]
    assert result["latency_ms"] == 0


def test_slack_post_message_channel_respects_approval_gate():
    """High-risk Slack channel broadcast must route to approval_gate (Acceptance A2)."""
    step = Step(
        tool_name="slack.post_message_channel",
        mcp_server="slack",
        input_params={"channel": "C123", "text": "Company announcement"},
    )
    state = _make_state(
        plan=[step],
        risk_flags={
            0: {
                "risk_tier": "high",
                "requires_approval": True,
                "rationale": "Broad channel visibility",
            }
        },
    )

    next_node = route_step(state)
    assert next_node == "approval_gate"


def test_slack_retry_is_idempotent_no_duplicate():
    """Retrying slack mutation returns cached output if step is already done."""
    from app.mcp_clients.slack import call as slack_call

    cached = {"ts": "1234567890.123456", "channel": "C123"}
    chain = MagicMock()
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = MagicMock(data={"status": "done", "output": cached})

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value = chain

    with (
        patch("app.mcp_clients.slack.supabase", mock_sb),
        patch("httpx.post") as mock_post,
    ):
        result = slack_call(
            tool_name="slack.post_message_dm",
            input_params={"user": "U123", "text": "Ping"},
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )

    mock_post.assert_not_called()
    assert result["status"] == "success"
    assert result["output"]["ts"] == "1234567890.123456"
