"""Tests for the D14 execute node and Calendar MCP client.

All external calls (Supabase, httpx) are mocked — no live DB or network needed.

Test map vs. spec acceptance criteria (d14-calendar-execute.md):
  test_execute_node_runs_low_risk_calendar_tool      → AC-1
  test_execute_node_skips_high_risk_step             → AC-2
  test_mcp_calendar_client_idempotency               → AC-3
  test_execution_logs_latency                        → AC-4
  test_execute_skips_when_state_error_set            → guard added in execute
  test_execute_marks_task_failed_on_mcp_error        → retry/failure path
  test_execute_retries_on_transient_error            → retry backoff
  test_graph_runs_four_nodes_in_order                → D14 graph shape
  test_calendar_client_returns_error_on_no_token     → missing token path
  test_calendar_client_handles_401_unauthorized      → expired token path
  test_calendar_client_handles_429_rate_limited      → rate limit path
  test_calendar_client_handles_timeout               → timeout path
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TASK_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())
PLAN_ID = str(uuid.uuid4())
STEP_ID = str(uuid.uuid4())
GOOGLE_TOKEN = "ya29.test_google_token"


def _make_state(
    plan: list | None = None,
    risk_flags: dict | None = None,
    error: str | None = None,
    plan_id: str = PLAN_ID,
) -> dict[str, Any]:
    """Build a minimal AgentState dict for the execute node."""
    return {
        "task_id": TASK_ID,
        "user_id": USER_ID,
        "raw_input": "test input",
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


def _low_risk_step():
    from app.agents.state import Step

    return Step(
        tool_name="calendar.list_events",
        mcp_server="calendar",
        input_params={"date_range": "2026-09-08"},
    )


def _high_risk_step():
    from app.agents.state import Step

    return Step(
        tool_name="calendar.delete_event",
        mcp_server="calendar",
        input_params={"event_id": "abc123"},
    )


def _make_supabase_mock():
    """Supabase mock that handles table().update().eq().execute() chains."""
    mock = MagicMock()

    def table_side_effect(name):
        t = MagicMock()

        def update_side_effect(payload):
            u = MagicMock()
            eq_mock = MagicMock()
            eq_mock.execute.return_value = MagicMock(data=[])
            u.eq.return_value = eq_mock
            return u

        def select_side_effect(*args, **kwargs):
            # oauth_connections fetch
            s = MagicMock()
            s.eq.return_value = s
            s.limit.return_value = s
            s.execute.return_value = MagicMock(data=[{"access_token": GOOGLE_TOKEN}])
            return s

        def insert_side_effect(payload):
            i = MagicMock()
            i.execute.return_value = MagicMock(data=[{"id": STEP_ID}])
            return i

        t.update.side_effect = update_side_effect
        t.select.side_effect = select_side_effect
        t.insert.side_effect = insert_side_effect
        return t

    mock.table.side_effect = table_side_effect
    return mock


def _make_httpx_response(status_code: int = 200, json_body: dict | None = None):
    """Build a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_body or {
        "jsonrpc": "2.0",
        "id": f"{PLAN_ID}:0",
        "result": {"events": []},
    }
    return resp


# ---------------------------------------------------------------------------
# AC-1: execute node runs a low-risk step and writes to execution_logs
# ---------------------------------------------------------------------------


def test_execute_node_runs_low_risk_calendar_tool():
    """Low-risk step calls the calendar MCP client and logs success."""
    from app.agents.nodes import execute

    step = _low_risk_step()
    state = _make_state(
        plan=[step],
        risk_flags={0: {"risk_tier": "low", "requires_approval": False, "rationale": "read-only"}},
    )

    mock_supabase = _make_supabase_mock()
    mock_response = _make_httpx_response(
        200,
        {
            "jsonrpc": "2.0",
            "id": f"{PLAN_ID}:0",
            "result": {"events": [{"id": "evt1", "summary": "Team standup"}]},
        },
    )

    with (
        patch("app.agents.nodes.supabase_admin", mock_supabase),
        patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
        patch("httpx.post", return_value=mock_response),
    ):
        result = execute(state)

    assert result["step_results"][0]["status"] == "success"
    assert result["step_results"][0]["output"] == {
        "events": [{"id": "evt1", "summary": "Team standup"}]
    }
    assert result["step_results"][0]["latency_ms"] >= 0


# ---------------------------------------------------------------------------
# AC-2: execute node skips high-risk steps
# ---------------------------------------------------------------------------


def test_execute_node_skips_high_risk_step():
    """High-risk step (requires_approval=True) must route to approval_gate."""
    from app.agents.nodes import route_step

    step = _high_risk_step()
    state = _make_state(
        plan=[step],
        risk_flags={
            0: {"risk_tier": "high", "requires_approval": True, "rationale": "destructive"}
        },
    )

    next_node = route_step(state)
    assert next_node == "approval_gate"


# ---------------------------------------------------------------------------
# AC-3: idempotency key is sent in the MCP request
# ---------------------------------------------------------------------------


def test_mcp_calendar_client_idempotency():
    """calendar.call() passes the idempotency key in the request headers."""
    from app.mcp_clients.calendar import call

    mock_supabase = _make_supabase_mock()
    mock_response = _make_httpx_response()

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
        patch("httpx.post", return_value=mock_response) as mock_post,
    ):
        idempotency_key = f"{PLAN_ID}:0"
        call(
            tool_name="calendar.list_events",
            input_params={"date_range": "2026-09-08"},
            user_id=USER_ID,
            idempotency_key=idempotency_key,
        )

    call_kwargs = mock_post.call_args
    sent_headers = call_kwargs.kwargs["headers"]
    assert sent_headers["X-Idempotency-Key"] == idempotency_key
    assert sent_headers["Authorization"] == f"Bearer {GOOGLE_TOKEN}"


# ---------------------------------------------------------------------------
# AC-4: latency_ms is recorded in the MCP response envelope
# ---------------------------------------------------------------------------


def test_execution_logs_latency():
    """calendar.call() returns a non-negative latency_ms in the envelope."""
    from app.mcp_clients.calendar import call

    mock_supabase = _make_supabase_mock()
    mock_response = _make_httpx_response()

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
        patch("httpx.post", return_value=mock_response),
    ):
        result = call(
            tool_name="calendar.list_events",
            input_params={},
            user_id=USER_ID,
            idempotency_key=f"{PLAN_ID}:0",
        )

    assert "latency_ms" in result
    assert isinstance(result["latency_ms"], int)
    assert result["latency_ms"] >= 0


# ---------------------------------------------------------------------------
# guard: execute exits early if state.error already set
# ---------------------------------------------------------------------------


def test_execute_skips_when_state_error_set():
    """If plan node set state.error, execute must not touch tasks.status."""
    from app.agents.nodes import execute

    state = _make_state(error="could not classify intent")
    mock_supabase = _make_supabase_mock()

    with patch("app.agents.nodes.supabase_admin", mock_supabase), patch("httpx.post") as mock_post:
        result = execute(state)

    mock_post.assert_not_called()
    assert result == {}


# ---------------------------------------------------------------------------
# failure path: execute marks task failed after MCP error
# ---------------------------------------------------------------------------


def test_execute_marks_task_failed_on_mcp_error():
    """A permanent MCP error after all retries marks tasks.status = 'failed'."""
    from app.agents.nodes import execute

    step = _low_risk_step()
    state = _make_state(
        plan=[step],
        risk_flags={0: {"risk_tier": "low", "requires_approval": False, "rationale": "ok"}},
    )

    mock_supabase = _make_supabase_mock()
    error_response = _make_httpx_response(500, {})
    error_response.is_success = False

    updated_statuses = []

    def table_side_effect(name):
        t = MagicMock()

        def update_side_effect(payload):
            u = MagicMock()
            eq_mock = MagicMock()
            eq_mock.execute.return_value = MagicMock(data=[])
            u.eq.return_value = eq_mock
            if name == "tasks":
                updated_statuses.append(payload.get("status"))
            return u

        def select_side_effect(*args, **kwargs):
            s = MagicMock()
            s.eq.return_value = s
            s.limit.return_value = s
            s.execute.return_value = MagicMock(data=[{"access_token": GOOGLE_TOKEN}])
            return s

        t.update.side_effect = update_side_effect
        t.select.side_effect = select_side_effect
        t.insert.return_value = MagicMock(execute=MagicMock(return_value=MagicMock(data=[])))
        return t

    mock_supabase.table.side_effect = table_side_effect

    with (
        patch("app.agents.nodes.supabase_admin", mock_supabase),
        patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
        patch("httpx.post", return_value=error_response),
        patch("time.sleep"),
    ):  # skip backoff in tests
        result = execute(state)

    assert result["step_results"][0]["status"] == "error"
    assert "failed" in updated_statuses


# ---------------------------------------------------------------------------
# retry path: execute retries on transient errors
# ---------------------------------------------------------------------------


def test_execute_retries_on_transient_error():
    """Execute retries up to 3 times on rate_limited, succeeds on 3rd attempt."""
    from app.agents.nodes import execute

    step = _low_risk_step()
    state = _make_state(
        plan=[step],
        risk_flags={0: {"risk_tier": "low", "requires_approval": False, "rationale": "ok"}},
    )

    mock_supabase = _make_supabase_mock()

    rate_limited = _make_httpx_response(429, {})
    rate_limited.is_success = False
    success = _make_httpx_response(200, {"jsonrpc": "2.0", "id": "x", "result": {"events": []}})

    call_count = {"n": 0}

    def httpx_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            return rate_limited
        return success

    with (
        patch("app.agents.nodes.supabase_admin", mock_supabase),
        patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
        patch("httpx.post", side_effect=httpx_side_effect),
        patch("time.sleep"),
    ):
        result = execute(state)

    assert call_count["n"] == 3
    assert result["step_results"][0]["status"] == "success"


# ---------------------------------------------------------------------------
# D14 graph shape: four nodes run in order
def test_graph_runs_nodes_in_order():
    """Graph calls intent_classify → plan → risk_tag → route_step → execute in order."""
    call_order = []

    def mock_intent_classify(state):
        call_order.append("intent_classify")
        return {"intent": "read_calendar"}

    def mock_plan(state):
        call_order.append("plan")
        from app.agents.state import Step

        return {
            "plan": [
                Step(tool_name="calendar.list_events", mcp_server="calendar", input_params={})
            ],
            "plan_id": PLAN_ID,
        }

    def mock_risk_tag(state):
        call_order.append("risk_tag")
        return {
            "risk_flags": {0: {"risk_tier": "low", "requires_approval": False, "rationale": "ok"}}
        }

    def mock_execute(state):
        call_order.append("execute")
        return {"step_results": {0: "done"}, "retries": {0: 0}, "current_step_index": 1}

    def mock_route_step(state):
        call_order.append("route_step")
        current = state.get("current_step_index", 0)
        if current >= 1:
            return "END"
        return "execute"

    from unittest.mock import patch

    with (
        patch("app.agents.graph.intent_classify", mock_intent_classify),
        patch("app.agents.graph.plan", mock_plan),
        patch("app.agents.graph.risk_tag", mock_risk_tag),
        patch("app.agents.graph.execute", mock_execute),
        patch("app.agents.graph.route_step", mock_route_step),
    ):
        from langgraph.checkpoint.memory import MemorySaver

        from app.agents.graph import build_graph

        graph = build_graph(checkpointer=MemorySaver())
        initial: dict[str, Any] = {
            "task_id": TASK_ID,
            "user_id": USER_ID,
            "raw_input": "check my calendar",
            "input_type": "text",
            "intent": "",
            "plan": [],
            "plan_id": None,
            "risk_flags": {},
            "current_step_index": 0,
            "step_results": {},
            "retries": {},
            "error": None,
        }
        graph.invoke(initial, config={"configurable": {"thread_id": TASK_ID}})

    assert call_order == [
        "intent_classify",
        "plan",
        "risk_tag",
        "route_step",
        "execute",
        "route_step",
    ]


# ---------------------------------------------------------------------------


def test_calendar_client_returns_error_on_no_token():
    """calendar.call() returns error envelope when no token is in the DB."""
    from app.mcp_clients.calendar import call

    mock_supabase = MagicMock()
    # Simulate no token found
    no_data = MagicMock()
    no_data.data = []
    chain = MagicMock()
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = no_data
    mock_supabase.table.return_value.select.return_value = chain

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
        patch("httpx.post") as mock_post,
    ):
        result = call("calendar.list_events", {}, USER_ID, f"{PLAN_ID}:0")

    mock_post.assert_not_called()
    assert result["status"] == "error"
    assert "token" in result["error"]


# ---------------------------------------------------------------------------
# calendar client: 401 unauthorized
# ---------------------------------------------------------------------------


def test_calendar_client_handles_401_unauthorized():
    """calendar.call() returns error on 401 — token expired or revoked."""
    from app.mcp_clients.calendar import call

    mock_supabase = _make_supabase_mock()
    resp_401 = _make_httpx_response(401)
    resp_401.is_success = False

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
        patch("httpx.post", return_value=resp_401),
    ):
        result = call("calendar.list_events", {}, USER_ID, f"{PLAN_ID}:0")

    assert result["status"] == "error"
    assert "unauthorized" in result["error"]


# ---------------------------------------------------------------------------
# calendar client: 429 rate limited
# ---------------------------------------------------------------------------


def test_calendar_client_handles_429_rate_limited():
    """calendar.call() returns rate_limited status on HTTP 429."""
    from app.mcp_clients.calendar import call

    mock_supabase = _make_supabase_mock()
    resp_429 = _make_httpx_response(429)
    resp_429.is_success = False

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
        patch("httpx.post", return_value=resp_429),
    ):
        result = call("calendar.list_events", {}, USER_ID, f"{PLAN_ID}:0")

    assert result["status"] == "rate_limited"


# ---------------------------------------------------------------------------
# calendar client: timeout
# ---------------------------------------------------------------------------


def test_calendar_client_handles_timeout():
    """calendar.call() returns error envelope on httpx.TimeoutException."""
    import httpx as httpx_mod

    from app.mcp_clients.calendar import call

    mock_supabase = _make_supabase_mock()

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
        patch("httpx.post", side_effect=httpx_mod.TimeoutException("timed out")),
    ):
        result = call("calendar.list_events", {}, USER_ID, f"{PLAN_ID}:0")

    assert result["status"] == "error"
    assert result["error"] == "timeout"
