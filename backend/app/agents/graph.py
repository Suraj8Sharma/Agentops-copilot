from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.nodes import (
    approval_gate_node,
    execute,
    intent_classify,
    plan,
    risk_tag,
    route_step,
)
from app.agents.state import AgentState


def build_graph(checkpointer=None) -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("intent_classify", intent_classify)
    builder.add_node("plan", plan)
    builder.add_node("risk_tag", risk_tag)
    builder.add_node("approval_gate", approval_gate_node)
    builder.add_node("execute", execute)

    builder.set_entry_point("intent_classify")
    builder.add_edge("intent_classify", "plan")
    builder.add_edge("plan", "risk_tag")

    builder.add_conditional_edges(
        "risk_tag", route_step, {"approval_gate": "approval_gate", "execute": "execute", "END": END}
    )
    builder.add_conditional_edges(
        "approval_gate",
        route_step,
        {"approval_gate": "approval_gate", "execute": "execute", "END": END},
    )
    builder.add_conditional_edges(
        "execute", route_step, {"approval_gate": "approval_gate", "execute": "execute", "END": END}
    )

    return builder.compile(checkpointer=checkpointer)
