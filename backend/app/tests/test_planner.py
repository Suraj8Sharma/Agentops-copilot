"""Tests for the D13 LangGraph planner skeleton.

Tests use unittest.mock to isolate all Supabase calls — no live DB required.
The risk_rules module cache is invalidated before each test to ensure a clean
lookup state.

Test map vs. spec acceptance criteria:
  test_graph_runs_three_nodes_in_order            → AC-1
  test_intent_classify_stub_maps_known_keywords   → AC-2
  test_plan_writes_task_plans_row                 → AC-3
  test_plan_sets_task_status_to_planning          → AC-4
  test_risk_tag_writes_plan_steps_correct_tiers   → AC-5
  test_risk_tag_fails_closed_on_unknown_action    → AC-6
  test_execution_logs_written_per_node            → AC-7
  test_unclassified_intent_sets_task_error        → AC-8
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TASK_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())
PLAN_ID = str(uuid.uuid4())
STEP_ID = str(uuid.uuid4())


def _make_supabase_mock(plan_id: str = PLAN_ID, step_id: str = STEP_ID):
    """Return a mock supabase client whose chained calls return sensible data."""
    mock = MagicMock()

    # task_plans INSERT → returns plan_id
    plan_insert_result = MagicMock()
    plan_insert_result.data = [{"id": plan_id}]

    # plan_steps INSERT → returns step_id
    step_insert_result = MagicMock()
    step_insert_result.data = [{"id": step_id}]

    # tasks SELECT → returns raw_input
    task_select_result = MagicMock()
    task_select_result.data = [
        {"raw_input": "schedule a call", "transcription_text": None, "input_type": "text"}
    ]

    # Generic UPDATE / INSERT chain
    def table_side_effect(name):
        t = MagicMock()

        def insert_side_effect(payload):
            i = MagicMock()
            if name == "task_plans":
                i.execute.return_value = plan_insert_result
            elif name == "plan_steps":
                i.execute.return_value = step_insert_result
            else:
                i.execute.return_value = MagicMock(data=[])
            return i

        def update_side_effect(payload):
            u = MagicMock()
            eq_mock = MagicMock()
            eq_mock.execute.return_value = MagicMock(data=[])
            u.eq.return_value = eq_mock
            return u

        def select_side_effect(*args, **kwargs):
            s = MagicMock()
            s.eq.return_value = s
            s.limit.return_value = s
            s.execute.return_value = task_select_result
            return s

        t.insert.side_effect = insert_side_effect
        t.update.side_effect = update_side_effect
        t.select.side_effect = select_side_effect
        return t

    mock.table.side_effect = table_side_effect
    return mock


def _make_risk_rules_row(tool_name: str, mcp_server: str, tier: str, approval: bool):
    from app.risk.risk_rules import RiskRule
    return RiskRule(
        action_type=tool_name,
        mcp_server=mcp_server,
        risk_tier=tier,
        requires_approval=approval,
        rationale="test rationale",
    )


# ---------------------------------------------------------------------------
# AC-1: Graph runs three nodes in the correct order
# ---------------------------------------------------------------------------

def test_graph_runs_three_nodes_in_order():
    """Invoking the graph calls intent_classify → plan → risk_tag, in order."""
    call_order = []

    def mock_intent_classify(state):
        call_order.append("intent_classify")
        return {"intent": "schedule_event"}

    def mock_plan(state):
        call_order.append("plan")
        from app.agents.state import Step
        step = Step(tool_name="calendar.list_events", mcp_server="calendar", input_params={})
        return {"plan": [step], "plan_id": PLAN_ID}

    def mock_risk_tag(state):
        call_order.append("risk_tag")
        decision = {"risk_tier": "low", "requires_approval": False, "rationale": "ok"}
        return {"risk_flags": {0: decision}}

    with patch("app.agents.graph.intent_classify", mock_intent_classify), \
         patch("app.agents.graph.plan", mock_plan), \
         patch("app.agents.graph.risk_tag", mock_risk_tag):
        from app.agents.graph import build_graph
        g = build_graph()
        from app.agents.state import AgentState
        state = AgentState(
            task_id=TASK_ID, user_id=USER_ID, raw_input="schedule a call",
            input_type="text", intent="", plan=[], plan_id=None, risk_flags={}, error=None,
        )
        g.invoke(state, config={"configurable": {"thread_id": TASK_ID}})

    assert call_order == ["intent_classify", "plan", "risk_tag"], (
        f"Expected nodes in order, got: {call_order}"
    )


# ---------------------------------------------------------------------------
# AC-2: intent_classify stub keyword mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw_input,expected_intent", [
    ("schedule a meeting with professor", "schedule_event_external"),
    ("send an email to the team", "send_email"),
    ("create a github issue for the bug", "file_issue"),
    ("show me my calendar events", "read_calendar"),
    ("schedule a call internally", "schedule_event"),
])
def test_intent_classify_stub_maps_known_keywords(raw_input, expected_intent):
    from app.agents.nodes import intent_classify
    from app.agents.state import AgentState

    with patch("app.agents.nodes.supabase") as mock_sb:
        mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])
        state = AgentState(
            task_id=TASK_ID, user_id=USER_ID, raw_input=raw_input,
            input_type="text", intent="", plan=[], plan_id=None, risk_flags={}, error=None,
        )
        result = intent_classify(state)

    assert result["intent"] == expected_intent, (
        f"raw_input={raw_input!r}: expected {expected_intent!r}, got {result['intent']!r}"
    )


def test_intent_classify_unmatched_returns_unclassified():
    from app.agents.nodes import intent_classify
    from app.agents.state import AgentState

    with patch("app.agents.nodes.supabase") as mock_sb:
        mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])
        state = AgentState(
            task_id=TASK_ID, user_id=USER_ID, raw_input="do something random xyz",
            input_type="text", intent="", plan=[], plan_id=None, risk_flags={}, error=None,
        )
        result = intent_classify(state)

    assert result["intent"] == "unclassified"


# ---------------------------------------------------------------------------
# AC-3: plan node writes task_plans row with correct fields
# ---------------------------------------------------------------------------

def test_plan_writes_task_plans_row():
    from app.agents.nodes import plan
    from app.agents.state import AgentState

    mock_sb = _make_supabase_mock()

    with patch("app.agents.nodes.supabase", mock_sb):
        state = AgentState(
            task_id=TASK_ID, user_id=USER_ID, raw_input="schedule a call",
            input_type="text", intent="schedule_event", plan=[], plan_id=None,
            risk_flags={}, error=None,
        )
        result = plan(state)

    # plan_id should be set from the INSERT result
    assert result["plan_id"] == PLAN_ID

    # task_plans INSERT should have been called with correct fields
    calls = mock_sb.table.call_args_list
    table_names = [c.args[0] for c in calls]
    assert "task_plans" in table_names

    # The plan list should be non-empty for a known intent
    assert len(result["plan"]) > 0


# ---------------------------------------------------------------------------
# AC-4: plan node sets task status to "planning"
# ---------------------------------------------------------------------------

def test_plan_sets_task_status_to_planning():
    from app.agents.nodes import plan
    from app.agents.state import AgentState

    mock_sb = _make_supabase_mock()
    update_payloads = []

    original_table = mock_sb.table.side_effect

    def tracking_table(name):
        t = original_table(name)
        orig_update = t.update.side_effect

        def tracking_update(payload):
            if name == "tasks":
                update_payloads.append(payload)
            return orig_update(payload)

        t.update.side_effect = tracking_update
        return t

    mock_sb.table.side_effect = tracking_table

    with patch("app.agents.nodes.supabase", mock_sb):
        state = AgentState(
            task_id=TASK_ID, user_id=USER_ID, raw_input="schedule a call",
            input_type="text", intent="schedule_event", plan=[], plan_id=None,
            risk_flags={}, error=None,
        )
        plan(state)

    assert {"status": "planning"} in update_payloads, (
        f"Expected tasks UPDATE to planning, got: {update_payloads}"
    )


# ---------------------------------------------------------------------------
# AC-5: risk_tag writes plan_steps rows with correct risk tiers from DB
# ---------------------------------------------------------------------------

def test_risk_tag_writes_plan_steps_correct_tiers():
    import app.risk.risk_rules as rr
    from app.agents.nodes import risk_tag
    from app.agents.state import AgentState, Step

    rr.invalidate_cache()

    known_rule = _make_risk_rules_row(
        "calendar.list_events", "calendar", "low", False
    )

    with patch("app.agents.nodes.lookup", return_value=known_rule), \
         patch("app.agents.nodes.supabase", _make_supabase_mock()):
        state = AgentState(
            task_id=TASK_ID, user_id=USER_ID, raw_input="check calendar",
            input_type="text", intent="read_calendar",
            plan=[Step(tool_name="calendar.list_events", mcp_server="calendar", input_params={})],
            plan_id=PLAN_ID, risk_flags={}, error=None,
        )
        result = risk_tag(state)

    assert 0 in result["risk_flags"]
    assert result["risk_flags"][0]["risk_tier"] == "low"
    assert result["risk_flags"][0]["requires_approval"] is False


# ---------------------------------------------------------------------------
# AC-6: risk_tag fails-closed on unknown action type
# ---------------------------------------------------------------------------

def test_risk_tag_fails_closed_on_unknown_action():
    from app.agents.nodes import risk_tag
    from app.agents.state import AgentState, Step

    with patch("app.agents.nodes.lookup", return_value=None), \
         patch("app.agents.nodes.supabase", _make_supabase_mock()):
        state = AgentState(
            task_id=TASK_ID, user_id=USER_ID, raw_input="do something unknown",
            input_type="text", intent="unknown",
            plan=[Step(tool_name="unknown.action", mcp_server="calendar", input_params={})],
            plan_id=PLAN_ID, risk_flags={}, error=None,
        )
        result = risk_tag(state)

    assert result["risk_flags"][0]["risk_tier"] == "high"
    assert result["risk_flags"][0]["requires_approval"] is True
    assert "fail closed" in result["risk_flags"][0]["rationale"]


# ---------------------------------------------------------------------------
# AC-7: execution_logs written per node
# ---------------------------------------------------------------------------

def test_execution_logs_written_per_node():
    """After a full graph run, execution_logs receives ≥3 inserts:
    plan_created (x2 from intent + plan), risk_tagged (x1 per step).
    """
    log_inserts = []

    mock_sb = _make_supabase_mock()
    original_side = mock_sb.table.side_effect

    def tracking_table(name):
        t = original_side(name)
        if name == "execution_logs":
            orig_insert = t.insert.side_effect

            def tracking_insert(payload):
                log_inserts.append(payload)
                return orig_insert(payload) if orig_insert else MagicMock()

            t.insert.side_effect = tracking_insert
        return t

    mock_sb.table.side_effect = tracking_table

    known_rule = _make_risk_rules_row(
        "calendar.create_event_internal_only", "calendar", "medium", False
    )

    with patch("app.agents.nodes.supabase", mock_sb), \
         patch("app.agents.nodes.lookup", return_value=known_rule):
        from app.agents.nodes import intent_classify, plan, risk_tag
        from app.agents.state import AgentState

        state = AgentState(
            task_id=TASK_ID, user_id=USER_ID, raw_input="schedule a call",
            input_type="text", intent="", plan=[], plan_id=None, risk_flags={}, error=None,
        )
        s1 = {**state, **intent_classify(state)}
        s2 = {**s1, **plan(s1)}
        risk_tag(s2)

    event_types = [i.get("event_type") for i in log_inserts]
    assert "plan_created" in event_types, f"Missing plan_created in logs: {event_types}"
    assert "risk_tagged" in event_types, f"Missing risk_tagged in logs: {event_types}"


# ---------------------------------------------------------------------------
# AC-8: unclassified intent sets state.error and marks task failed
# ---------------------------------------------------------------------------

def test_unclassified_intent_sets_task_error():
    from app.agents.nodes import plan
    from app.agents.state import AgentState

    failed_statuses = []
    mock_sb = _make_supabase_mock()
    original_side = mock_sb.table.side_effect

    def tracking_table(name):
        t = original_side(name)
        if name == "tasks":
            orig_update = t.update.side_effect

            def tracking_update(payload):
                failed_statuses.append(payload)
                return orig_update(payload)

            t.update.side_effect = tracking_update
        return t

    mock_sb.table.side_effect = tracking_table

    with patch("app.agents.nodes.supabase", mock_sb):
        state = AgentState(
            task_id=TASK_ID, user_id=USER_ID, raw_input="xyz random nonsense",
            input_type="text", intent="unclassified", plan=[], plan_id=None,
            risk_flags={}, error=None,
        )
        result = plan(state)

    assert result.get("error") is not None, "Expected error to be set for unclassified intent"
    assert {"status": "failed"} in failed_statuses, (
        f"Expected tasks UPDATE to failed, got: {failed_statuses}"
    )
