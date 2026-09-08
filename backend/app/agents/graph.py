"""LangGraph StateGraph definition for the AgentOps Copilot planner.

D14 graph — four nodes, straight-line with execute added:

    intent_classify → plan → risk_tag → execute → END

The execute node internally handles the approval fork:
  - Low-risk steps  → called immediately via MCP clients.
  - High-risk steps → logged as awaiting_approval, skipped for now.

The full conditional fork (execute vs. approval_gate) is added in D17 when
the approval_gate node and POST /approvals/{step_id} endpoint are built.

Usage::

    from app.agents.graph import build_graph

    graph = build_graph()
    final_state = graph.invoke(
        initial_state,
        config={"configurable": {"thread_id": task_id}},
    )
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.nodes import execute, intent_classify, plan, risk_tag
from app.agents.state import AgentState


def build_graph() -> StateGraph:
    """Construct and compile the D14 planner graph.

    Returns:
        A compiled LangGraph ``CompiledGraph`` ready for ``.invoke()``.
    """
    builder = StateGraph(AgentState)

    # ── Nodes ────────────────────────────────────────────────────────────────
    builder.add_node("intent_classify", intent_classify)
    builder.add_node("plan", plan)
    builder.add_node("risk_tag", risk_tag)
    builder.add_node("execute", execute)

    # ── Edges ─────────────────────────────────────────────────────────────────
    # Straight-line for D14. The approval_gate conditional fork is D17.
    builder.set_entry_point("intent_classify")
    builder.add_edge("intent_classify", "plan")
    builder.add_edge("plan", "risk_tag")
    builder.add_edge("risk_tag", "execute")
    builder.add_edge("execute", END)

    return builder.compile()
