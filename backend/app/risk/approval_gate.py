import logging

from langgraph.types import interrupt

from app.agents.state import RiskDecision
from app.db.supabase_client import supabase_admin
from app.risk.risk_rules import lookup

logger = logging.getLogger(__name__)


def evaluate(step: dict) -> RiskDecision:
    """Looks up risk_rules by (step.tool_name, step.mcp_server)."""
    tool_name = step.get("tool_name")
    mcp_server = step.get("mcp_server")

    rule = lookup(tool_name, mcp_server)
    if rule:
        decision = RiskDecision(
            risk_tier=rule.risk_tier,
            requires_approval=rule.requires_approval,
            rationale=rule.rationale,
        )
    else:
        decision = RiskDecision(
            risk_tier="high",
            requires_approval=True,
            rationale="no matching risk_rules entry - fail closed",
        )

    return decision


def gate(
    step: dict,
    decision: RiskDecision,
    task_id: str,
    user_id: str,
    plan_id: str,
    step_index: int,
    step_id: str,
) -> str:
    """
    If requires_approval is False, returns 'approved'.
    If True, creates an approval request, halts via interrupt, and returns the human decision.
    """
    if not decision["requires_approval"]:
        return "approved"

    from app.agents.nodes import _log_event

    # Check if we already created an approval request (since interrupt reruns the node on resume)
    try:
        existing = supabase_admin.table("approvals").select("*").eq("step_id", step_id).execute()
        if not existing.data:
            _log_event(
                task_id=task_id,
                agent_name="risk_gate",
                event_type="approval_requested",
                payload={
                    "step_index": step_index,
                    "tool_name": step.get("tool_name"),
                    "mcp_server": step.get("mcp_server"),
                    "risk_tier": decision["risk_tier"],
                    "rationale": decision["rationale"],
                },
                step_id=step_id,
            )

            supabase_admin.table("approvals").insert(
                {
                    "step_id": step_id,
                    "user_id": user_id,
                }
            ).execute()

            supabase_admin.table("tasks").update({"status": "awaiting_approval"}).eq(
                "id", task_id
            ).execute()

            if step_id:
                supabase_admin.table("plan_steps").update({"status": "awaiting_approval"}).eq(
                    "id", step_id
                ).execute()
    except Exception as e:
        logger.error(f"gate: failed to process approvals [step_id={step_id}]", exc_info=True)
        raise e

    # Halts the LangGraph run at this node
    user_decision = interrupt("WAIT_FOR_USER")

    return user_decision
