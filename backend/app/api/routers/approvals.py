import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.agents.runner import resume_planner
from app.core.security import CurrentUser, get_current_user
from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]


@router.get("/pending")
def pending_approvals(user: CurrentUser = Depends(get_current_user)):
    """Return the authenticated user's undecided approval steps."""
    try:
        approvals = (
            supabase.table("approvals")
            .select("*")
            .eq("user_id", user.id)
            .is_("decision", "null")
            .order("created_at", desc=False)
            .execute()
        )
        pending = []
        for approval in approvals.data or []:
            step_result = (
                supabase.table("plan_steps")
                .select("*")
                .eq("id", approval["step_id"])
                .limit(1)
                .execute()
            )
            if not step_result.data:
                continue
            step = step_result.data[0]
            plan_result = (
                supabase.table("task_plans")
                .select("task_id")
                .eq("id", step["plan_id"])
                .limit(1)
                .execute()
            )
            if not plan_result.data:
                continue
            if step.get("status") != "awaiting_approval":
                continue
            pending.append(
                {
                    "step_id": step["id"],
                    "task_id": plan_result.data[0]["task_id"],
                    "tool_name": step["tool_name"],
                    "mcp_server": step["mcp_server"],
                    "risk_tier": step["risk_tier"],
                    "requires_approval": step["requires_approval"],
                    "input_params": step.get("input_params") or {},
                    "explanation_text": approval.get("explanation_text"),
                    "status": step["status"],
                }
            )
        return pending
    except Exception as exc:
        logger.error(
            "DB error listing pending approvals for user_id=%s: %s", user.id, exc
        )
        raise HTTPException(
            status_code=500, detail="Failed to retrieve pending approvals."
        ) from exc


@router.post("/{step_id}")
async def decide_approval(
    step_id: str,
    decision: ApprovalDecision,
    user: CurrentUser = Depends(get_current_user),
):
    # Verify the approvals row for step_id belongs to user
    res = (
        supabase.table("approvals")
        .select("*")
        .eq("step_id", step_id)
        .eq("user_id", user.id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    approval = res.data[0]

    # Verify the row is currently pending
    if approval.get("decision") is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Approval already decided"
        )

    # Update approvals
    update_res = (
        supabase.table("approvals")
        .update(
            {
                "decision": decision.decision,
                "decided_at": "now()",
            }
        )
        .eq("id", approval["id"])
        .is_("decision", "null")
        .execute()
    )

    if not update_res.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approval was already decided.",
        )

    updated_approval = update_res.data[0]

    # Wait, the spec says "compute response_time_ms from created_at".
    # Supabase "now()" is a string. Actually we can let Postgres do it:
    # "response_time_ms = EXTRACT(EPOCH FROM (now() - created_at)) * 1000"
    # Wait, it's easier to do this in python if we have the created_at timestamp.
    # We can just let python do it or use a simple update.

    try:
        from datetime import datetime, timezone

        created_at_str = approval.get("created_at")
        if created_at_str:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            response_time_ms = int((now - created_at).total_seconds() * 1000)

            updated_approval = (
                supabase.table("approvals")
                .update(
                    {
                        "decision": decision.decision,
                        "decided_at": now.isoformat(),
                        "response_time_ms": response_time_ms,
                    }
                )
                .eq("id", approval["id"])
                .execute()
                .data[0]
            )
        else:
            updated_approval = (
                supabase.table("approvals")
                .update({"decision": decision.decision, "decided_at": "now()"})
                .eq("id", approval["id"])
                .execute()
                .data[0]
            )
    except Exception as e:
        logger.warning(f"Failed to compute response_time_ms: {e}")
        updated_approval = (
            supabase.table("approvals")
            .update({"decision": decision.decision, "decided_at": "now()"})
            .eq("id", approval["id"])
            .execute()
            .data[0]
        )

    # Find the task_id to resume the graph.
    # The step belongs to plan_steps, which belongs to task_plans, which belongs to tasks.
    # Let's query task_id.
    plan_step_res = (
        supabase.table("plan_steps")
        .select("plan_id, step_index, tool_name, mcp_server")
        .eq("id", step_id)
        .execute()
    )
    if not plan_step_res.data:
        raise HTTPException(status_code=500, detail="Plan step not found")
    plan_id = plan_step_res.data[0]["plan_id"]
    step_info = plan_step_res.data[0]

    task_plan_res = supabase.table("task_plans").select("task_id").eq("id", plan_id).execute()
    if not task_plan_res.data:
        raise HTTPException(status_code=500, detail="Task plan not found")
    task_id = task_plan_res.data[0]["task_id"]

    # Log the approval decision itself to execution_logs before resuming the graph
    from app.agents.nodes import _log_event

    _log_event(
        task_id=task_id,
        agent_name="risk_gate",
        event_type="approval_decided",
        payload={
            "step_index": step_info["step_index"],
            "tool_name": step_info["tool_name"],
            "mcp_server": step_info["mcp_server"],
            "decision": decision.decision,
        },
        step_id=step_id,
    )

    # Resume the LangGraph checkpoint
    await resume_planner(task_id, decision.decision)

    # Fetch task status to return
    task_res = supabase.table("tasks").select("status").eq("id", task_id).execute()
    task_status = task_res.data[0]["status"] if task_res.data else "unknown"

    return {"approval": updated_approval, "task_status": task_status}
