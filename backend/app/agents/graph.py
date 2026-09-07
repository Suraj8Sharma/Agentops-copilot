"""LangGraph StateGraph definition for the AgentOps Copilot planner.

D13 skeleton: a straight-line 3-node graph.

    intent_classify → plan → risk_tag → END

No conditional edges exist yet.  The fork on ``requires_approval`` (execute
vs. approval_gate) is added when those nodes are built on D14-17.

Usage::

    from app.agents.graph import build_graph

    graph = build_graph()
    final_state = graph.invoke(initial_state, config={"configurable": {"thread_id": task_id}})
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.nodes import intent_classify, plan, risk_tag
from app.agents.state import AgentState


def build_graph() -> StateGraph:
    """Construct and compile the D13 skeleton graph.

    Returns:
        A compiled LangGraph ``CompiledGraph`` ready for ``.invoke()``.
    """
    builder = StateGraph(AgentState)

    # ── Nodes ────────────────────────────────────────────────────────────────
    builder.add_node("intent_classify", intent_classify)
    builder.add_node("plan", plan)
    builder.add_node("risk_tag", risk_tag)

    # ── Edges (straight-line for D13) ────────────────────────────────────────
    builder.set_entry_point("intent_classify")
    builder.add_edge("intent_classify", "plan")
    builder.add_edge("plan", "risk_tag")
    builder.add_edge("risk_tag", END)

    return builder.compile()
