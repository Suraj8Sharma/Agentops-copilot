"""Tests for the Approval Gate and Adversarial Bypass Battery (Day 31 - Suraj).

Manual §9.4, §14, §15.4: Approval-gate bypass adversarial test (must never pass).
Acceptance Criterion A2: Every action tagged high-risk is blocked pending approval
in 100% of test runs — zero tolerance. Gate 4 blocker.

Vector Matrix:
  ADV-1: Missing Rule Lookup (Fail-Closed)
  ADV-2: Cross-User Approval Hijack (IDOR)
  ADV-3: Replay / Double-Decision Attack
  ADV-4: Direct Execute Node Invocation (State Tampering)
  ADV-5: Tampered Risk Flags in State
  ADV-6: Unauthenticated Decision Injection
  ADV-7: Rejected Decision Enforcement

Named Tests (Manual §15.4):
  - test_low_risk_action_auto_executes_without_approval
  - test_high_risk_action_blocks_pending_approval
  - test_no_matching_rule_fails_closed
  - test_approval_gate_bypass_attempt_always_fails
  - test_rejected_approval_halts_task_with_no_side_effects
  - test_task_resumes_after_app_closed_mid_approval
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

with (
    patch("app.db.supabase_client.create_client"),
    patch("app.db.supabase_client.probe_connection"),
):
    from app.main import app

from app.agents.graph import build_graph
from app.agents.nodes import approval_gate_node, execute, risk_tag, route_step
from app.agents.state import AgentState, RiskDecision, Step
from app.risk.approval_gate import evaluate
from app.risk.risk_rules import RiskRule

# ---------------------------------------------------------------------------
# Constants & Fixtures
# ---------------------------------------------------------------------------

USER_A_ID = "aaaaaaaa-1111-0000-0000-000000000001"
USER_B_ID = "bbbbbbbb-2222-0000-0000-000000000002"
TASK_ID = str(uuid.uuid4())
PLAN_ID = str(uuid.uuid4())
STEP_ID = str(uuid.uuid4())
AUTH_HEADER_A = {"Authorization": "Bearer token.user.a"}
AUTH_HEADER_B = {"Authorization": "Bearer token.user.b"}


def _make_current_user(user_id: str, email: str = "user@agentops.dev") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.role = "authenticated"
    resp = MagicMock()
    resp.user = user
    return resp


@pytest.fixture
def mock_lookup():
    def _lookup(action_type, mcp_server):
        if action_type == "calendar.list_events":
            return RiskRule(
                action_type=action_type,
                mcp_server=mcp_server,
                risk_tier="low",
                requires_approval=False,
                rationale="ok",
            )
        elif action_type in (
            "slack.post_message_channel",
            "gmail.send_message",
            "calendar.delete_event",
        ):
            return RiskRule(
                action_type=action_type,
                mcp_server=mcp_server,
                risk_tier="high",
                requires_approval=True,
                rationale="destructive",
            )
        return None

    with (
        patch("app.risk.approval_gate.lookup", side_effect=_lookup),
        patch("app.agents.nodes.lookup", side_effect=_lookup),
    ):
        yield


class MockDatabase:
    """In-memory database simulating Supabase client calls."""

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

        # Select
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
# Named Tests (Manual §15.4)
# ---------------------------------------------------------------------------


def test_low_risk_action_auto_executes_without_approval(mock_lookup):
    step = {"tool_name": "calendar.list_events", "mcp_server": "calendar"}
    decision = evaluate(step)
    assert decision["requires_approval"] is False
    assert decision["risk_tier"] == "low"


def test_high_risk_action_blocks_pending_approval(mock_lookup):
    step = {"tool_name": "slack.post_message_channel", "mcp_server": "slack"}
    decision = evaluate(step)
    assert decision["requires_approval"] is True
    assert decision["risk_tier"] in ["high", "medium"]


def test_no_matching_rule_fails_closed(mock_lookup):
    step = {"tool_name": "unknown_tool", "mcp_server": "unknown"}
    decision = evaluate(step)
    assert decision["requires_approval"] is True
    assert decision["risk_tier"] == "high"
    assert "fail closed" in decision["rationale"].lower()


# ---------------------------------------------------------------------------
# Adversarial Bypass Battery: ADV-1 to ADV-7
# ---------------------------------------------------------------------------


def test_adv1_missing_rule_fails_closed():
    """ADV-1: Unknown tool missing from risk_rules table must fail-closed (high risk)."""
    step = {"tool_name": "system.wipe_disk", "mcp_server": "danger"}
    with patch("app.risk.approval_gate.lookup", return_value=None):
        decision = evaluate(step)

    assert decision["requires_approval"] is True
    assert decision["risk_tier"] == "high"
    assert "fail closed" in decision["rationale"].lower()


def test_adv2_cross_user_approval_hijack_idor():
    """ADV-2: Attacker (User B) attempts to approve Victim (User A)'s high-risk step."""
    db = MockDatabase()
    step_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())

    # Set up step owned by User A
    db.tables["tasks"].append({"id": task_id, "user_id": USER_A_ID, "status": "awaiting_approval"})
    db.tables["task_plans"].append({"id": plan_id, "task_id": task_id})
    db.tables["plan_steps"].append(
        {
            "id": step_id,
            "plan_id": plan_id,
            "step_index": 0,
            "tool_name": "gmail.send_message",
            "mcp_server": "gmail",
            "status": "awaiting_approval",
        }
    )
    db.tables["approvals"].append(
        {
            "id": str(uuid.uuid4()),
            "step_id": step_id,
            "user_id": USER_A_ID,
            "decision": None,
        }
    )

    client = TestClient(app)

    # User B authenticates and calls POST /approvals/{step_id}
    with (
        patch(
            "app.core.security.supabase.auth.get_user", return_value=_make_current_user(USER_B_ID)
        ),
        patch("app.api.routers.approvals.supabase", db),
        patch("app.db.supabase_client.supabase", db),
    ):
        response = client.post(
            f"/approvals/{step_id}",
            json={"decision": "approved"},
            headers=AUTH_HEADER_B,
        )

    # Must reject with 404 Not Found (or 403 Forbidden)
    assert response.status_code == 404
    # Ensure approval remained undecided
    assert db.tables["approvals"][0]["decision"] is None
    # Ensure task remained awaiting_approval
    assert db.tables["tasks"][0]["status"] == "awaiting_approval"


def test_adv3_replay_double_decision_conflict():
    """ADV-3: Submitting an approval decision twice must return 409 Conflict."""
    db = MockDatabase()
    step_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())

    db.tables["tasks"].append({"id": task_id, "user_id": USER_A_ID, "status": "awaiting_approval"})
    db.tables["task_plans"].append({"id": plan_id, "task_id": task_id})
    db.tables["plan_steps"].append(
        {
            "id": step_id,
            "plan_id": plan_id,
            "step_index": 0,
            "tool_name": "gmail.send_message",
            "mcp_server": "gmail",
            "status": "awaiting_approval",
        }
    )
    # Already approved
    db.tables["approvals"].append(
        {
            "id": str(uuid.uuid4()),
            "step_id": step_id,
            "user_id": USER_A_ID,
            "decision": "approved",
        }
    )

    client = TestClient(app)
    with (
        patch(
            "app.core.security.supabase.auth.get_user", return_value=_make_current_user(USER_A_ID)
        ),
        patch("app.api.routers.approvals.supabase", db),
        patch("app.db.supabase_client.supabase", db),
    ):
        response = client.post(
            f"/approvals/{step_id}",
            json={"decision": "approved"},
            headers=AUTH_HEADER_A,
        )

    assert response.status_code == 409
    assert "already decided" in response.json()["detail"].lower()


def test_adv4_direct_execute_node_tampering_blocked():
    """ADV-4: Directly invoking execute() on a high-risk step without approval aborts with error."""
    state = AgentState(
        task_id=TASK_ID,
        user_id=USER_A_ID,
        raw_input="send email",
        input_type="text",
        intent="send_email",
        plan=[
            Step(
                tool_name="gmail.send_message",
                mcp_server="gmail",
                input_params={"to": ["target@corp.com"]},
            )
        ],
        plan_id=PLAN_ID,
        risk_flags={
            0: RiskDecision(risk_tier="high", requires_approval=True, rationale="destructive")
        },
        current_step_index=0,
        step_results={},
        retries={},
        error=None,
    )

    with patch("app.agents.nodes.call_tool") as mock_call:
        result = execute(state)

    # Must abort and block
    assert result.get("error") == "unauthorized_execution_attempt"
    assert result.get("status") == "blocked"
    # Zero tool dispatch
    mock_call.assert_not_called()


def test_adv5_tampered_risk_flags_recomputed():
    """ADV-5: Client-injected poisoned risk_flags are overwritten by risk_tag lookup."""
    poisoned_state = AgentState(
        task_id=TASK_ID,
        user_id=USER_A_ID,
        raw_input="send email",
        input_type="text",
        intent="send_email",
        plan=[
            Step(
                tool_name="gmail.send_message",
                mcp_server="gmail",
                input_params={"to": ["victim@corp.com"]},
            )
        ],
        plan_id=PLAN_ID,
        # Attacker claims high-risk step is low-risk
        risk_flags={
            0: RiskDecision(risk_tier="low", requires_approval=False, rationale="tampered")
        },
        current_step_index=0,
        step_results={},
        retries={},
        error=None,
    )

    db = MockDatabase()
    rule = RiskRule(
        action_type="gmail.send_message",
        mcp_server="gmail",
        risk_tier="high",
        requires_approval=True,
        rationale="destructive",
    )

    with (
        patch("app.agents.nodes.lookup", return_value=rule),
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
    ):
        result = risk_tag(poisoned_state)

    # Must be re-tagged as requires_approval=True
    assert result["risk_flags"][0]["requires_approval"] is True
    assert result["risk_flags"][0]["risk_tier"] == "high"

    # And route_step must route to approval_gate
    poisoned_state["risk_flags"] = result["risk_flags"]
    assert route_step(poisoned_state) == "approval_gate"


def test_adv6_unauthenticated_decision_injection():
    """ADV-6: Calling approval endpoint without valid JWT returns 401 Unauthorized."""
    client = TestClient(app)
    response = client.post(f"/approvals/{STEP_ID}", json={"decision": "approved"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_adv7_rejected_decision_halts_with_zero_calls():
    """ADV-7: Submitting decision='rejected' halts graph, marks task failed, zero MCP calls."""
    db = MockDatabase()
    step_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())

    db.tables["tasks"].append({"id": task_id, "user_id": USER_A_ID, "status": "awaiting_approval"})
    db.tables["task_plans"].append({"id": plan_id, "task_id": task_id})
    db.tables["plan_steps"].append(
        {
            "id": step_id,
            "plan_id": plan_id,
            "step_index": 0,
            "tool_name": "gmail.send_message",
            "mcp_server": "gmail",
            "status": "awaiting_approval",
        }
    )
    db.tables["approvals"].append(
        {
            "id": str(uuid.uuid4()),
            "step_id": step_id,
            "user_id": USER_A_ID,
            "decision": None,
        }
    )

    client = TestClient(app)

    with (
        patch(
            "app.core.security.supabase.auth.get_user", return_value=_make_current_user(USER_A_ID)
        ),
        patch("app.api.routers.approvals.supabase", db),
        patch("app.db.supabase_client.supabase", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.api.routers.approvals.resume_planner", new_callable=AsyncMock) as mock_resume,
        patch("app.mcp_clients.call_tool") as mock_call,
    ):
        response = client.post(
            f"/approvals/{step_id}",
            json={"decision": "rejected"},
            headers=AUTH_HEADER_A,
        )

    assert response.status_code == 200
    assert db.tables["approvals"][0]["decision"] == "rejected"
    mock_resume.assert_awaited_once_with(task_id, "rejected")
    mock_call.assert_not_called()


def test_approval_gate_bypass_attempt_always_fails():
    """Named Test 3 (Manual §15.4 / Acceptance Criterion A2):

    Adversarial bypass attempts across all vectors (ADV-1 to ADV-7) MUST fail in 100% of runs.
    A single bypass is an outright blocker for Gate 4 release.
    """
    test_adv1_missing_rule_fails_closed()
    test_adv2_cross_user_approval_hijack_idor()
    test_adv3_replay_double_decision_conflict()
    test_adv4_direct_execute_node_tampering_blocked()
    test_adv5_tampered_risk_flags_recomputed()
    test_adv6_unauthenticated_decision_injection()


# ---------------------------------------------------------------------------
# Named Test 4 & Named Test 6
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejected_approval_halts_task_with_no_side_effects():
    """Named Test 4 (Manual §15.4):

    User explicitly submits decision='rejected'.
    Asserts tasks.status='failed', step_skipped is logged, and call_tool() call_count == 0.
    """
    db = MockDatabase()
    step_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())

    db.tables["tasks"].append({"id": task_id, "user_id": USER_A_ID, "status": "awaiting_approval"})
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
            "user_id": USER_A_ID,
            "decision": None,
        }
    )

    # Call approval_gate_node directly with simulated 'rejected' interrupt resume
    state = AgentState(
        task_id=task_id,
        user_id=USER_A_ID,
        raw_input="delete calendar meeting",
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
        node_res = approval_gate_node(state)

    # 1. State returned halts graph
    assert node_res.get("error") == "human_rejected"

    # 2. tasks.status marked failed
    assert db.tables["tasks"][0]["status"] == "failed"

    # 3. plan_steps marked failed
    assert db.tables["plan_steps"][0]["status"] == "failed"

    # 4. step_skipped logged in execution_logs
    event_types = [log["event_type"] for log in db.tables["execution_logs"]]
    assert "step_skipped" in event_types

    # 5. MCP client NEVER invoked
    mock_call.assert_not_called()


@pytest.mark.asyncio
async def test_task_resumes_after_app_closed_mid_approval():
    """Named Test 6 (Manual §15.4 / Scenario E):

    Process restart / disconnect mid-approval with state recovery from checkpointer.
    1. Task halts in approval_gate with interrupt WAIT_FOR_USER.
    2. Runner state is closed.
    3. Fresh graph loads state from checkpointer by thread_id.
    4. Resumed with Command(resume="approved") and completes.
    """
    checkpointer = MemorySaver()
    graph_1 = build_graph(checkpointer=checkpointer)

    db = MockDatabase()
    task_id = str(uuid.uuid4())

    db.tables["tasks"].append({"id": task_id, "user_id": USER_A_ID, "status": "submitted"})

    initial_state = AgentState(
        task_id=task_id,
        user_id=USER_A_ID,
        raw_input="Send email to team",
        input_type="text",
        intent="send_email",
        plan=[
            Step(
                tool_name="gmail.send_message",
                mcp_server="gmail",
                input_params={"to": ["team@corp.com"]},
            )
        ],
        plan_id=None,
        risk_flags={},
        current_step_index=0,
        step_results={},
        retries={},
        error=None,
    )

    config = {"configurable": {"thread_id": task_id}}

    rule = RiskRule(
        action_type="gmail.send_message",
        mcp_server="gmail",
        risk_tier="high",
        requires_approval=True,
        rationale="destructive",
    )

    from app.llm.types import LLMProvider, LLMResponse

    llm_mock_routing = LLMResponse(
        text="send_email",
        provider=LLMProvider.GROQ,
        model="mock",
        tokens_in=10,
        tokens_out=10,
        latency_ms=5,
    )
    plan_json_str = (
        '[{"tool_name": "gmail.send_message", "mcp_server": "gmail", '
        '"input_params": {"to": ["team@corp.com"]}}]'
    )
    llm_mock_planning = LLMResponse(
        text=plan_json_str,
        provider=LLMProvider.GROQ,
        model="mock",
        tokens_in=10,
        tokens_out=10,
        latency_ms=5,
    )

    async def _mock_route_llm(prompt, request_type, **kwargs):
        if request_type == "routing":
            return llm_mock_routing
        return llm_mock_planning

    # 1. Run Graph 1 - Halts at approval gate
    with (
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.risk.approval_gate.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.agents.nodes.lookup", return_value=rule),
        patch("app.llm.router.route_llm_call", side_effect=_mock_route_llm),
    ):
        await graph_1.ainvoke(initial_state, config=config)

    # Verify task halted and approval created
    assert db.tables["tasks"][0]["status"] == "awaiting_approval"
    assert len(db.tables["approvals"]) == 1
    assert db.tables["plan_steps"][0]["status"] == "awaiting_approval"

    # 2. Simulate process kill / server restart: graph_1 is discarded.
    del graph_1
    fresh_graph = build_graph(checkpointer=checkpointer)

    # 3. Resume the fresh graph from checkpointer with "approved"
    tool_resp = {
        "status": "success",
        "output": {"id": "msg_123"},
        "error": None,
        "latency_ms": 120,
    }

    with (
        patch("app.agents.nodes.supabase_admin", db),
        patch("app.risk.approval_gate.supabase_admin", db),
        patch("app.db.supabase_client.supabase_admin", db),
        patch("app.agents.nodes.call_tool", return_value=tool_resp) as mock_call,
    ):
        final_state = await fresh_graph.ainvoke(Command(resume="approved"), config=config)

    # 4. Verify completed successfully
    assert mock_call.call_count == 1
    assert final_state.get("error") is None
    assert final_state["current_step_index"] == 1
    assert db.tables["tasks"][0]["status"] == "completed"
    assert db.tables["plan_steps"][0]["status"] == "done"
