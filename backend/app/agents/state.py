"""LangGraph agent state for AgentOps Copilot planner.

This TypedDict is the single shared bag-of-state that flows through every
node in the planner graph.  Only the fields consumed by the D13 skeleton
nodes (intent_classify, plan, risk_tag) are included.

Fields added in D14 (execute node):
  - current_step_index  → which step is currently executing
  - step_results        → output of each completed step
  - retries             → per-step retry counter

Fields needed by later nodes are intentionally absent:
  - approval_status     → D17 (approval_gate node)
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict


class Step(TypedDict):
    """A single tool-call step in the generated plan."""

    tool_name: str  # e.g. "gmail.send_message"
    mcp_server: str  # "calendar" | "gmail" | "github" | "slack"
    input_params: dict  # provider-specific payload (placeholder values in D13)


class RiskDecision(TypedDict):
    """Output of the risk_rules lookup for one plan step."""

    risk_tier: str  # "low" | "medium" | "high"
    requires_approval: bool
    rationale: str


class AgentState(TypedDict):
    """Full shared state bag for the LangGraph planner.

    Passed into the graph via ``graph.invoke(initial_state, ...)``.
    Each node receives the current state and returns a dict of the
    fields it wants to update — LangGraph merges them.
    """

    task_id: str  # UUID of the tasks row; also the checkpointer thread_id
    user_id: str  # UUID of the owning user (from verified JWT)
    raw_input: str  # User's original text (or STT transcript for voice)
    input_type: str  # "text" | "voice"

    # Set by intent_classify node
    intent: str

    # Set by plan node
    plan: list[Step]
    plan_id: Optional[str]  # UUID of the task_plans row written by plan node

    # Set by risk_tag node
    risk_flags: dict[int, RiskDecision]  # step_index → RiskDecision

    # Set by execute node (D14)
    current_step_index: int  # which step is currently running
    step_results: dict[int, Any]  # step_index → MCP response output
    retries: dict[int, int]  # step_index → retry count (max 3)

    # Set on unrecoverable failure; halts the graph and marks task failed
    error: Optional[str]
