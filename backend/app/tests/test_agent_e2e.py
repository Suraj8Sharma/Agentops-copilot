"""End-to-End Agent-Loop Test Suite for AgentOps Copilot (Day 31 - Suraj).

Manual §8.1, §9, §9.4, §14, §15.4, Gate 4:
Comprehensive deterministic integration suite exercising the complete LangGraph agent loop.

Named Tests (Manual §15.4):
  - test_low_risk_action_auto_executes_without_approval
  - test_high_risk_action_blocks_pending_approval
  - test_rejected_approval_halts_task_with_no_side_effects
  - test_mixed_risk_multi_step_plan_orders_correctly
  - test_task_resumes_after_app_closed_mid_approval
  - test_e2e_text_task_completes_full_loop
  - test_e2e_voice_task_completes_full_loop

All external services (LLM, MCP servers, Supabase DB) are intercepted via offline mocks.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

with (
    patch("app.db.supabase_client.create_client"),
    patch("app.db.supabase_client.probe_connection"),
):
    from app.main import app

import app.agents.runner as agent_runner
from app.agents.graph import build_graph
from app.agents.nodes import approval_gate_node, execute
from app.agents.state import AgentState, RiskDecision, Step
from app.llm.types import LLMProvider, LLMResponse
from app.risk.approval_gate import evaluate
from app.risk.risk_rules import RiskRule

# ---------------------------------------------------------------------------
# Constants & Mock DB
# ---------------------------------------------------------------------------

USER_ID = "aaaaaaaa-1111-0000-0000-000000000001"
AUTH_HEADER = {"Authorization": "Bearer valid.jwt.token"}


def _make_current_user(user_id: str = USER_ID, email: str = "suraj@agentops.dev") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.role = "authenticated"
    resp = MagicMock()
    resp.user = user
    return resp


class MockDatabase:
    """In-memory database simulating Supabase queries."""

    def __init__(self):
        self.tables: dict[str, list[dict[str, Any]]] = {
            "tasks": [],
            "task_plans": [],
            "plan_steps": [],
            "approvals": [],
            "execution_logs": [],
        }

    def table(self, table_name: str):
        return MockTableQuery(self, table_name)


class MockTableQuery:
    def __init__(self, db: MockDatabase, table_name: str):
        self.db = db
        self.table_name = table_name
        self.filters = []
        self._insert_data = None
        self._update_data = None
        self._limit = None

    def select(self, *args, **kwargs):
        return self

    def insert(self, data):
        self._insert_data = data if isinstance(data, list) else [data]
        return self

    def update(self, data):
        self._update_data = data
        return self

    def eq(self, col, val):
        self.filters.append((col, "eq", val))
        return self

    def is_(self, col, val):
        self.filters.append((col, "is", val))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def order(self, *args, **kwargs):
        return self

    def execute(self):
        rows = self.db.tables.setdefault(self.table_name, [])

        if self._insert_data is not None:
            inserted = []
            for item in self._insert_data:
                row = dict(item)
                if "id" not in row:
                    row["id"] = str(uuid.uuid4())
                if "created_at" not in row:
                    row["created_at"] = "2026-09-28T12:00:00Z"
                if "completed_at" not in row:
                    row["completed_at"] = None
                if self.table_name == "approvals" and "decision" not in row:
                    row["decision"] = None
                rows.append(row)
                inserted.append(row)
            return MagicMock(data=inserted)

        if self._update_data is not None:
            updated = []
            for row in rows:
                if self._matches(row):
                    row.update(self._update_data)
                    updated.append(dict(row))
            return MagicMock(data=updated)

        results = [dict(row) for row in rows if self._matches(row)]
        if self._limit is not None:
            results = results[: self._limit]
        return MagicMock(data=results)

    def _matches(self, row):
        for col, op, val in self.filters:
            if op == "eq" and str(row.get(col)) != str(val):
                return False
            if op == "is":
                if val == "null" and row.get(col) is not None:
                    return False
                elif val != "null" and row.get(col) == val:
                    return False
        return True


# ---------------------------------------------------------------------------
# Test 1: Low-Risk Action Auto-Executes Without Approval
# ---------------------------------------------------------------------------


def test_low_risk_action_auto_executes_without_approval():
    """Asserts calendar.list_events evaluates to requires_approval=False,

    auto-executes straight to completion, and creates zero approval rows.
    """
    step = {"tool_name": "calendar.list_events", "mcp_server": "calendar"}
    rule = RiskRule(
        action_type="calendar.list_events",
        mcp_server="calendar",
        risk_tier="low",
        requires_approval=False,
        rationale="read-only",
    )

    with patch("app.risk.approval_gate.lookup", return_value=rule):
        decision = evaluate(step)

    assert decision["requires_approval"] is False
    assert decision["risk_tier"] == "low"

    task_id = str(uuid.uuid4())
    state = AgentState(
        task_id=task_id,
        user_id=USER_ID,
        raw_input="check calendar",
        input_type="text",
        intent="read_calendar",
        plan=[
            Step(
                tool_name="calendar.list_events",
                mcp_server="calendar",
                input_params={"date_range": "today"},
            )
        ],
        plan_id=str(uuid.uuid4()),
        risk_flags={0: decision},
        current_step_index=0,
        step_results={},
        retries={},
        error=None,
    )

    tool_res = {"status": "success", "output": {"items": []}, "error": None, "latency_ms": 50}
    db = MockDatabase()

    with (
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.agents.nodes.call_tool", return_value=tool_res) as mock_call,
    ):
        res = execute(state)

    assert mock_call.call_count == 1
    assert res["current_step_index"] == 1
    assert len(db.tables["approvals"]) == 0


# ---------------------------------------------------------------------------
# Test 2: High-Risk Action Blocks Pending Approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high_risk_action_blocks_pending_approval():
    """Asserts gmail.send_message evaluates to requires_approval=True,

    creates approval row, updates task status to awaiting_approval, and halts.
    """
    step = {"tool_name": "gmail.send_message", "mcp_server": "gmail"}
    rule = RiskRule(
        action_type="gmail.send_message",
        mcp_server="gmail",
        risk_tier="high",
        requires_approval=True,
        rationale="external send",
    )

    with patch("app.risk.approval_gate.lookup", return_value=rule):
        decision = evaluate(step)

    assert decision["requires_approval"] is True
    assert decision["risk_tier"] == "high"

    db = MockDatabase()
    task_id = str(uuid.uuid4())

    db.tables["tasks"].append(
        {
            "id": task_id,
            "user_id": USER_ID,
            "status": "planning",
            "raw_input": "Send email to team",
            "input_type": "text",
        }
    )

    plan_steps_json = [
        {
            "tool_name": "gmail.send_message",
            "mcp_server": "gmail",
            "input_params": {"to": ["team@corp.com"]},
        }
    ]

    async def _mock_route_llm(prompt, request_type, **kwargs):
        if request_type == "routing":
            return LLMResponse(
                text="send_email",
                provider=LLMProvider.GROQ,
                model="mock",
                tokens_in=10,
                tokens_out=10,
                latency_ms=5,
            )
        return LLMResponse(
            text=json.dumps(plan_steps_json),
            provider=LLMProvider.GROQ,
            model="mock",
            tokens_in=20,
            tokens_out=30,
            latency_ms=10,
        )

    checkpointer = MemorySaver()
    graph = build_graph(checkpointer=checkpointer)

    initial_state = AgentState(
        task_id=task_id,
        user_id=USER_ID,
        raw_input="Send email to team",
        input_type="text",
        intent="send_email",
        plan=[],
        plan_id=None,
        risk_flags={},
        current_step_index=0,
        step_results={},
        retries={},
        error=None,
    )

    config = {"configurable": {"thread_id": task_id}}

    with (
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.risk.approval_gate.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.agents.nodes.lookup", return_value=rule),
        patch("app.risk.approval_gate.lookup", return_value=rule),
        patch("app.llm.router.route_llm_call", side_effect=_mock_route_llm),
        patch("app.agents.nodes.call_tool") as mock_call,
    ):
        await graph.ainvoke(initial_state, config=config)

    # Asserts
    assert db.tables["tasks"][0]["status"] == "awaiting_approval"
    assert len(db.tables["plan_steps"]) == 1
    assert db.tables["plan_steps"][0]["status"] == "awaiting_approval"
    assert len(db.tables["approvals"]) == 1
    assert db.tables["approvals"][0]["step_id"] == db.tables["plan_steps"][0]["id"]
    assert db.tables["approvals"][0]["decision"] is None
    # Tool must NEVER have been called
    mock_call.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: Rejected Approval Halts Task with Zero Side Effects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejected_approval_halts_task_with_no_side_effects():
    """Asserts submitting decision='rejected' marks task failed,

    logs step_skipped, and guarantees call_tool() call_count == 0.
    """
    db = MockDatabase()
    task_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())

    db.tables["tasks"].append({"id": task_id, "user_id": USER_ID, "status": "awaiting_approval"})
    db.tables["task_plans"].append({"id": plan_id, "task_id": task_id})
    db.tables["plan_steps"].append(
        {
            "id": step_id,
            "plan_id": plan_id,
            "step_index": 0,
            "tool_name": "calendar.delete_event",
            "mcp_server": "calendar",
            "status": "awaiting_approval",
        }
    )
    db.tables["approvals"].append(
        {
            "id": str(uuid.uuid4()),
            "step_id": step_id,
            "user_id": USER_ID,
            "decision": None,
        }
    )

    state = AgentState(
        task_id=task_id,
        user_id=USER_ID,
        raw_input="delete meeting",
        input_type="text",
        intent="schedule_event",
        plan=[
            Step(
                tool_name="calendar.delete_event",
                mcp_server="calendar",
                input_params={"id": "evt1"},
            )
        ],
        plan_id=plan_id,
        risk_flags={
            0: RiskDecision(risk_tier="high", requires_approval=True, rationale="destructive")
        },
        current_step_index=0,
        step_results={},
        retries={},
        error=None,
    )

    with (
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.risk.approval_gate.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.risk.approval_gate.interrupt", return_value="rejected"),
        patch("app.mcp_clients.call_tool") as mock_call,
    ):
        res = approval_gate_node(state)

    assert res.get("error") == "human_rejected"
    assert db.tables["tasks"][0]["status"] == "failed"
    assert db.tables["plan_steps"][0]["status"] == "failed"
    mock_call.assert_not_called()

    # Verify event logged
    event_types = [log["event_type"] for log in db.tables["execution_logs"]]
    assert "step_skipped" in event_types


# ---------------------------------------------------------------------------
# Test 4: Mixed-Risk Multi-Step Plan Orders Correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_risk_multi_step_plan_orders_correctly():
    """Topological execution order:

    Step 0 (low): calendar.list_events -> auto-executes
    Step 1 (high): gmail.send_message -> halts awaiting approval
    Step 2 (medium): github.create_issue -> pending (not executed)
    Upon approval of Step 1 -> Step 1 executes -> Step 2 executes -> completes.
    """
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer=checkpointer)

    db = MockDatabase()
    task_id = str(uuid.uuid4())

    db.tables["tasks"].append({"id": task_id, "user_id": USER_ID, "status": "submitted"})

    mixed_steps_json = [
        {
            "tool_name": "calendar.list_events",
            "mcp_server": "calendar",
            "input_params": {"date_range": "today"},
        },
        {
            "tool_name": "gmail.send_message",
            "mcp_server": "gmail",
            "input_params": {"to": ["team@corp.com"]},
        },
        {
            "tool_name": "github.create_issue",
            "mcp_server": "github",
            "input_params": {"title": "Sync bug"},
        },
    ]

    async def _mock_route_llm(prompt, request_type, **kwargs):
        if request_type == "routing":
            return LLMResponse(
                text="schedule_event",
                provider=LLMProvider.GROQ,
                model="mock",
                tokens_in=10,
                tokens_out=10,
                latency_ms=5,
            )
        return LLMResponse(
            text=json.dumps(mixed_steps_json),
            provider=LLMProvider.GROQ,
            model="mock",
            tokens_in=20,
            tokens_out=30,
            latency_ms=10,
        )

    def _lookup_mixed(action_type, mcp_server):
        if action_type == "calendar.list_events":
            return RiskRule(
                action_type=action_type,
                mcp_server=mcp_server,
                risk_tier="low",
                requires_approval=False,
                rationale="read-only",
            )
        elif action_type == "gmail.send_message":
            return RiskRule(
                action_type=action_type,
                mcp_server=mcp_server,
                risk_tier="high",
                requires_approval=True,
                rationale="external email",
            )
        elif action_type == "github.create_issue":
            return RiskRule(
                action_type=action_type,
                mcp_server=mcp_server,
                risk_tier="medium",
                requires_approval=False,
                rationale="issue create",
            )
        return None

    initial_state = AgentState(
        task_id=task_id,
        user_id=USER_ID,
        raw_input="Sync meetings, email team and create issue",
        input_type="text",
        intent="schedule_event",
        plan=[],
        plan_id=None,
        risk_flags={},
        current_step_index=0,
        step_results={},
        retries={},
        error=None,
    )

    config = {"configurable": {"thread_id": task_id}}

    call_history: list[str] = []

    def mock_call_tool(tool_name, **kwargs):
        call_history.append(tool_name)
        return {"status": "success", "output": {"ok": True}, "error": None, "latency_ms": 25}

    # 1. Run Graph - Step 0 executes, Step 1 halts
    with (
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.risk.approval_gate.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.agents.nodes.lookup", side_effect=_lookup_mixed),
        patch("app.risk.approval_gate.lookup", side_effect=_lookup_mixed),
        patch("app.llm.router.route_llm_call", side_effect=_mock_route_llm),
        patch("app.agents.nodes.call_tool", side_effect=mock_call_tool),
    ):
        await graph.ainvoke(initial_state, config=config)

    # Step 0 finished, Step 1 halted at approval gate
    assert call_history == ["calendar.list_events"]
    assert db.tables["plan_steps"][0]["status"] == "done"
    assert db.tables["plan_steps"][1]["status"] == "awaiting_approval"
    assert db.tables["plan_steps"][2]["status"] == "pending"
    assert db.tables["tasks"][0]["status"] == "awaiting_approval"

    # 2. User approves Step 1
    with (
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.risk.approval_gate.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.agents.nodes.lookup", side_effect=_lookup_mixed),
        patch("app.risk.approval_gate.lookup", side_effect=_lookup_mixed),
        patch("app.agents.nodes.call_tool", side_effect=mock_call_tool),
    ):
        final_state = await graph.ainvoke(Command(resume="approved"), config=config)

    # Step 1 and Step 2 execute in topological order to completion
    assert call_history == [
        "calendar.list_events",
        "gmail.send_message",
        "github.create_issue",
    ]
    assert final_state["current_step_index"] == 3
    assert db.tables["plan_steps"][1]["status"] == "done"
    assert db.tables["plan_steps"][2]["status"] == "done"
    assert db.tables["tasks"][0]["status"] == "completed"


# ---------------------------------------------------------------------------
# Test 5: Checkpointer Resumption Across Simulated Process Crash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_resumes_after_app_closed_mid_approval():
    """Checkpointer survival across process restart / reload."""
    checkpointer = MemorySaver()
    graph_1 = build_graph(checkpointer=checkpointer)

    db = MockDatabase()
    task_id = str(uuid.uuid4())

    db.tables["tasks"].append({"id": task_id, "user_id": USER_ID, "status": "submitted"})

    plan_steps_json = [
        {
            "tool_name": "gmail.send_message",
            "mcp_server": "gmail",
            "input_params": {"to": ["team@corp.com"]},
        }
    ]

    async def _mock_route_llm(prompt, request_type, **kwargs):
        if request_type == "routing":
            return LLMResponse(
                text="send_email",
                provider=LLMProvider.GROQ,
                model="mock",
                tokens_in=10,
                tokens_out=10,
                latency_ms=5,
            )
        return LLMResponse(
            text=json.dumps(plan_steps_json),
            provider=LLMProvider.GROQ,
            model="mock",
            tokens_in=20,
            tokens_out=30,
            latency_ms=10,
        )

    rule = RiskRule(
        action_type="gmail.send_message",
        mcp_server="gmail",
        risk_tier="high",
        requires_approval=True,
        rationale="destructive",
    )

    initial_state = AgentState(
        task_id=task_id,
        user_id=USER_ID,
        raw_input="Send email to team",
        input_type="text",
        intent="send_email",
        plan=[],
        plan_id=None,
        risk_flags={},
        current_step_index=0,
        step_results={},
        retries={},
        error=None,
    )

    config = {"configurable": {"thread_id": task_id}}

    with (
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.risk.approval_gate.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.agents.nodes.lookup", return_value=rule),
        patch("app.risk.approval_gate.lookup", return_value=rule),
        patch("app.llm.router.route_llm_call", side_effect=_mock_route_llm),
    ):
        await graph_1.ainvoke(initial_state, config=config)

    assert db.tables["tasks"][0]["status"] == "awaiting_approval"
    assert db.tables["plan_steps"][0]["status"] == "awaiting_approval"

    # Simulate app close: discard graph_1 reference
    del graph_1
    fresh_graph = build_graph(checkpointer=checkpointer)

    tool_res = {"status": "success", "output": {"id": "sent_1"}, "error": None, "latency_ms": 90}

    with (
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.risk.approval_gate.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.agents.nodes.call_tool", return_value=tool_res) as mock_call,
    ):
        final_state = await fresh_graph.ainvoke(Command(resume="approved"), config=config)

    assert mock_call.call_count == 1
    assert final_state["current_step_index"] == 1
    assert db.tables["tasks"][0]["status"] == "completed"
    assert db.tables["plan_steps"][0]["status"] == "done"


# ---------------------------------------------------------------------------
# Test 6: Text Input Task Completes Full Loop (HTTP e2e)
# ---------------------------------------------------------------------------


def test_e2e_text_task_completes_full_loop():
    """Full HTTP e2e loop for low-risk text task.

    POST /tasks -> planner -> execute -> execution_logs -> completed.
    Acceptance Criterion A6: Latency < 8.0s.
    """
    db = MockDatabase()
    client = TestClient(app)

    llm_routing = LLMResponse(
        text="read_calendar",
        provider=LLMProvider.GROQ,
        model="mock",
        tokens_in=10,
        tokens_out=10,
        latency_ms=5,
    )
    plan_steps = [
        {
            "tool_name": "calendar.list_events",
            "mcp_server": "calendar",
            "input_params": {"date_range": "tomorrow"},
        }
    ]
    llm_planning = LLMResponse(
        text=json.dumps(plan_steps),
        provider=LLMProvider.GROQ,
        model="mock",
        tokens_in=20,
        tokens_out=30,
        latency_ms=10,
    )

    async def _mock_route_llm(prompt, request_type, **kwargs):
        if request_type == "routing":
            return llm_routing
        return llm_planning

    rule = RiskRule(
        action_type="calendar.list_events",
        mcp_server="calendar",
        risk_tier="low",
        requires_approval=False,
        rationale="read-only",
    )

    tool_resp = {
        "status": "success",
        "output": {"items": [{"id": "ev1", "summary": "Standup"}]},
        "error": None,
        "latency_ms": 65,
    }

    agent_runner._graph = build_graph(checkpointer=MemorySaver())

    t0 = time.monotonic()

    with (
        patch("app.core.security.supabase.auth.get_user", return_value=_make_current_user()),
        patch("app.api.routers.tasks.supabase", db),
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.agents.runner.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.db.supabase_client.supabase", db),
        patch("app.agents.nodes.lookup", return_value=rule),
        patch("app.risk.approval_gate.lookup", return_value=rule),
        patch("app.llm.router.route_llm_call", side_effect=_mock_route_llm),
        patch("app.agents.nodes.call_tool", return_value=tool_resp) as mock_call,
    ):
        response = client.post(
            "/tasks",
            json={"input_type": "text", "raw_input": "Check my calendar for meetings tomorrow"},
            headers=AUTH_HEADER,
        )

    duration = time.monotonic() - t0

    # 1. HTTP 201 Created
    assert response.status_code == 201
    task_id = response.json()["id"]

    # 2. Acceptance Criterion A6: Latency under 8.0s
    assert duration < 8.0

    # 3. Tool dispatched
    assert mock_call.call_count == 1

    # 4. Final DB status
    task_rows = [t for t in db.tables["tasks"] if t["id"] == task_id]
    assert len(task_rows) == 1
    assert task_rows[0]["status"] == "completed"

    # 5. Plan steps completed, zero approvals
    assert len(db.tables["plan_steps"]) == 1
    assert db.tables["plan_steps"][0]["status"] == "done"
    assert len(db.tables["approvals"]) == 0

    # 6. Audit trail in execution_logs
    logged_events = [log["event_type"] for log in db.tables["execution_logs"]]
    assert "plan_created" in logged_events
    assert "risk_tagged" in logged_events
    assert "step_started" in logged_events
    assert "step_completed" in logged_events


# ---------------------------------------------------------------------------
# Test 7: Voice Input Task Completes Full Loop (HTTP e2e)
# ---------------------------------------------------------------------------


def test_e2e_voice_task_completes_full_loop():
    """Full HTTP e2e loop for voice task.

    POST /tasks with transcription_text prioritized over raw_input audio uuid.
    """
    db = MockDatabase()
    client = TestClient(app)

    llm_routing = LLMResponse(
        text="file_issue",
        provider=LLMProvider.GROQ,
        model="mock",
        tokens_in=10,
        tokens_out=10,
        latency_ms=5,
    )
    plan_steps = [
        {
            "tool_name": "github.create_issue",
            "mcp_server": "github",
            "input_params": {"title": "App bug", "repo": "org/repo"},
        }
    ]
    llm_planning = LLMResponse(
        text=json.dumps(plan_steps),
        provider=LLMProvider.GROQ,
        model="mock",
        tokens_in=20,
        tokens_out=30,
        latency_ms=10,
    )

    async def _mock_route_llm(prompt, request_type, **kwargs):
        if request_type == "routing":
            return llm_routing
        return llm_planning

    rule = RiskRule(
        action_type="github.create_issue",
        mcp_server="github",
        risk_tier="low",
        requires_approval=False,
        rationale="issue create",
    )

    tool_resp = {
        "status": "success",
        "output": {"id": 101, "number": 42},
        "error": None,
        "latency_ms": 55,
    }

    agent_runner._graph = build_graph(checkpointer=MemorySaver())

    with (
        patch("app.core.security.supabase.auth.get_user", return_value=_make_current_user()),
        patch("app.api.routers.tasks.supabase", db),
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.agents.runner.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.db.supabase_client.supabase", db),
        patch("app.agents.nodes.lookup", return_value=rule),
        patch("app.risk.approval_gate.lookup", return_value=rule),
        patch("app.llm.router.route_llm_call", side_effect=_mock_route_llm),
        patch("app.agents.nodes.call_tool", return_value=tool_resp) as mock_call,
    ):
        response = client.post(
            "/tasks",
            json={
                "input_type": "voice",
                "raw_input": "audio_recording_4b8f.wav",
                "transcription_text": "List my open github issues",
            },
            headers=AUTH_HEADER,
        )

    assert response.status_code == 201
    task_id = response.json()["id"]

    assert mock_call.call_count == 1
    task_rows = [t for t in db.tables["tasks"] if t["id"] == task_id]
    assert len(task_rows) == 1
    assert task_rows[0]["status"] == "completed"
    assert db.tables["plan_steps"][0]["status"] == "done"


# ---------------------------------------------------------------------------
# Test 8: High-Risk Task HTTP E2E Approval Flow (Scenario B)
# ---------------------------------------------------------------------------


def test_e2e_high_risk_approval_flow():
    """Scenario B: High-Risk Task Full Lifecycle via HTTP API:

    1. POST /tasks -> enters awaiting_approval
    2. GET /approvals/pending -> returns pending approval
    3. POST /approvals/{step_id} with decision="approved" -> resumes and completes.
    """
    db = MockDatabase()
    client = TestClient(app)

    llm_routing = LLMResponse(
        text="send_email",
        provider=LLMProvider.GROQ,
        model="mock",
        tokens_in=10,
        tokens_out=10,
        latency_ms=5,
    )
    plan_steps = [
        {
            "tool_name": "gmail.send_message",
            "mcp_server": "gmail",
            "input_params": {"to": ["team@company.com"]},
        }
    ]
    llm_planning = LLMResponse(
        text=json.dumps(plan_steps),
        provider=LLMProvider.GROQ,
        model="mock",
        tokens_in=20,
        tokens_out=30,
        latency_ms=10,
    )

    async def _mock_route_llm(prompt, request_type, **kwargs):
        if request_type == "routing":
            return llm_routing
        return llm_planning

    rule = RiskRule(
        action_type="gmail.send_message",
        mcp_server="gmail",
        risk_tier="high",
        requires_approval=True,
        rationale="destructive",
    )

    tool_resp = {
        "status": "success",
        "output": {"id": "sent_msg_99"},
        "error": None,
        "latency_ms": 75,
    }

    shared_checkpointer = MemorySaver()
    agent_runner._graph = build_graph(checkpointer=shared_checkpointer)

    # 1. Submit High-Risk Task
    with (
        patch("app.core.security.supabase.auth.get_user", return_value=_make_current_user()),
        patch("app.api.routers.tasks.supabase", db),
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.agents.runner.supabase_admin", db),
        patch("app.risk.approval_gate.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.db.supabase_client.supabase", db),
        patch("app.agents.nodes.lookup", return_value=rule),
        patch("app.risk.approval_gate.lookup", return_value=rule),
        patch("app.llm.router.route_llm_call", side_effect=_mock_route_llm),
        patch("app.agents.nodes.call_tool", return_value=tool_resp) as mock_call,
    ):
        response = client.post(
            "/tasks",
            json={
                "input_type": "text",
                "raw_input": "Send an email to team@company.com with subject Meeting Notes",
            },
            headers=AUTH_HEADER,
        )

    assert response.status_code == 201
    task_id = response.json()["id"]

    # Graph halted at approval_gate
    assert mock_call.call_count == 0
    task_row = [t for t in db.tables["tasks"] if t["id"] == task_id][0]
    assert task_row["status"] == "awaiting_approval"
    assert len(db.tables["approvals"]) == 1
    step_id = db.tables["approvals"][0]["step_id"]

    # 2. Check pending approvals endpoint
    with (
        patch("app.core.security.supabase.auth.get_user", return_value=_make_current_user()),
        patch("app.api.routers.approvals.supabase", db),
    ):
        pending_resp = client.get("/approvals/pending", headers=AUTH_HEADER)

    assert pending_resp.status_code == 200
    pending_list = pending_resp.json()
    assert len(pending_list) == 1
    assert pending_list[0]["step_id"] == step_id
    assert pending_list[0]["tool_name"] == "gmail.send_message"

    # 3. User approves
    with (
        patch("app.core.security.supabase.auth.get_user", return_value=_make_current_user()),
        patch("app.api.routers.approvals.supabase", db),
        patch("app.db.supabase_client.supabase", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.agents.runner.supabase_admin", db),
        patch("app.risk.approval_gate.supabase_admin", db),
        patch("app.agents.nodes.lookup", return_value=rule),
        patch("app.risk.approval_gate.lookup", return_value=rule),
        patch("app.agents.nodes.call_tool", return_value=tool_resp) as mock_resume_call,
    ):
        decide_resp = client.post(
            f"/approvals/{step_id}",
            json={"decision": "approved"},
            headers=AUTH_HEADER,
        )

    assert decide_resp.status_code == 200
    assert mock_resume_call.call_count == 1
    assert db.tables["tasks"][0]["status"] == "completed"
    assert db.tables["plan_steps"][0]["status"] == "done"
    assert db.tables["approvals"][0]["decision"] == "approved"
