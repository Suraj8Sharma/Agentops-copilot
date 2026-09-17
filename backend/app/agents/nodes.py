"""LangGraph node functions for the AgentOps Copilot planner.

Nodes wired as of D14:

    intent_classify  →  plan  →  risk_tag  →  execute  →  END
                                              (low-risk steps only;
                                               high-risk steps skipped
                                               until approval_gate: D17)

intent_classify and plan use deterministic stub logic (no LLM — that is D18).
risk_tag performs a real DB read against the seeded risk_rules table.
execute calls official hosted remote MCP servers with the user's OAuth token.

Each node function:
  - Receives the full AgentState dict.
  - Returns a *partial* dict of the fields it mutates.
  - LangGraph merges the returned dict into the running state.
  - Writes one or more rows to execution_logs before any external effect.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agents.state import AgentState, RiskDecision, Step
from app.db.supabase_client import supabase_admin
from app.mcp_clients import call_tool
from app.risk.risk_rules import lookup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLANNER_VERSION = "skeleton-v0"


def _log_event(
    task_id: str,
    agent_name: str,
    event_type: str,
    payload: dict[str, Any],
    step_id: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Helper to write to execution_logs."""
    from app.db.supabase_client import supabase_admin

    row = {
        "task_id": task_id,
        "step_id": step_id,
        "agent_name": agent_name,
        "event_type": event_type,
        "payload": payload,
        "latency_ms": latency_ms,
    }
    try:
        supabase_admin.table("execution_logs").insert(row).execute()
    except Exception:
        # Log failures must never crash the planner — audit is best-effort.
        logger.warning(
            "execution_logs write failed [task_id=%s event_type=%s]",
            task_id,
            event_type,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Intent-to-plan stub mapping
# ---------------------------------------------------------------------------

# Maps stub intent labels to a fixed list of Steps.
# Replaced by a real LLM call on D18.
_STUB_PLANS: dict[str, list[Step]] = {
    "schedule_event": [
        Step(
            tool_name="calendar.create_event_internal_only",
            mcp_server="calendar",
            input_params={
                "title": "[placeholder] Meeting",
                "start": "TBD",
                "end": "TBD",
                "attendees": [],
            },
        )
    ],
    "schedule_event_external": [
        Step(
            tool_name="calendar.create_event_external_attendee",
            mcp_server="calendar",
            input_params={
                "title": "[placeholder] Meeting",
                "start": "TBD",
                "end": "TBD",
                "attendees": ["external@example.com"],
            },
        )
    ],
    "send_email": [
        Step(
            tool_name="gmail.send_message",
            mcp_server="gmail",
            input_params={
                "to": ["[placeholder]@example.com"],
                "subject": "[placeholder] Subject",
                "body": "[placeholder] Body",
            },
        )
    ],
    "file_issue": [
        Step(
            tool_name="github.create_issue",
            mcp_server="github",
            input_params={
                "repo": "[placeholder]/repo",
                "title": "[placeholder] Issue title",
                "body": "[placeholder] Issue body",
            },
        )
    ],
    "read_calendar": [
        Step(
            tool_name="calendar.list_events",
            mcp_server="calendar",
            input_params={"date_range": "TBD"},
        )
    ],
}


# ---------------------------------------------------------------------------
# Node: intent_classify
# ---------------------------------------------------------------------------


async def intent_classify(state: AgentState) -> dict[str, Any]:
    """Classify the user's raw_input into a one-of-N intent label.
    
    D18: Uses Groq/Gemini LLM call with a classification prompt.
    """
    from app.llm.router import route_llm_call

    t0 = time.monotonic()
    raw = (state.get("raw_input") or "").strip()
    
    if not raw:
        intent = "unclassified"
    else:
        valid_intents = list(_STUB_PLANS.keys())
        prompt = (
            f"You are the intent classification module of an AI agent.\n"
            f"Classify the user's request into EXACTLY ONE of the following intents: {valid_intents}\n"  # noqa: E501
            f"If the request does not clearly match any of these, output: unclassified\n"
            f"Respond with ONLY the raw intent string, nothing else. No markdown, no explanation.\n\n"  # noqa: E501
            f"User Request: {raw}"
        )
        
        try:
            llm_resp = await route_llm_call(prompt, request_type="routing")
            # Clean up response: lowercased, stripped, remove punctuation
            intent_out = llm_resp.text.strip().lower().replace("`", "").replace('"', "").replace("'", "")  # noqa: E501
            if intent_out in valid_intents:
                intent = intent_out
            else:
                logger.warning("intent_classify: LLM returned invalid intent %r, defaulting to unclassified", intent_out)  # noqa: E501
                intent = "unclassified"
        except Exception:
            logger.error("intent_classify: LLM call failed, defaulting to unclassified", exc_info=True)  # noqa: E501
            intent = "unclassified"

    latency_ms = int((time.monotonic() - t0) * 1000)
    _log_event(
        task_id=state["task_id"],
        agent_name="planner",
        event_type="plan_created",
        payload={"intent": intent, "source": "llm"},
        latency_ms=latency_ms,
    )
    logger.info("intent_classify: task_id=%s intent=%s", state["task_id"], intent)
    return {"intent": intent}


# ---------------------------------------------------------------------------
# Node: plan
# ---------------------------------------------------------------------------


async def plan(state: AgentState) -> dict[str, Any]:
    """Produce a list[Step] from the intent and write a task_plans row.

    D18: LLM structured output (JSON array of Steps).
    """
    import json

    from app.llm.router import route_llm_call

    t0 = time.monotonic()
    intent = state.get("intent", "unclassified")
    raw = state.get("raw_input", "")

    if intent == "unclassified":
        # Fail immediately — nothing to plan.
        _log_event(
            task_id=state["task_id"],
            agent_name="planner",
            event_type="error",
            payload={"reason": "could not classify intent", "source": "llm"},
        )
        try:
            supabase_admin.table("tasks").update({"status": "failed"}).eq(
                "id", state["task_id"]
            ).execute()
        except Exception:
            logger.warning(
                "Failed to mark task failed [task_id=%s]", state["task_id"], exc_info=True
            )
        logger.warning("plan: unclassified intent for task_id=%s", state["task_id"])
        return {"plan": [], "plan_id": None, "error": "could not classify intent"}

    # --- DB write 1: UPDATE tasks.status → "planning" ---
    try:
        supabase_admin.table("tasks").update({"status": "planning"}).eq("id", state["task_id"]).execute()  # noqa: E501
    except Exception:
        logger.warning(
            "Failed to set task status=planning [task_id=%s]",
            state["task_id"],
            exc_info=True,
        )

    # Get the template plan
    template_steps = _STUB_PLANS.get(intent, [])
    template_json = [dict(s) for s in template_steps]

    prompt = (
        f"You are the planning module of an AI agent.\n"
        f"The user's intent is '{intent}'.\n"
        f"The user's raw request is '{raw}'.\n\n"
        f"Here is the JSON template for the steps required for this intent:\n"
        f"{json.dumps(template_json, indent=2)}\n\n"
        f"Your task is to fill in the [placeholder] and TBD values with actual parameters extracted from the user's request. "  # noqa: E501
        f"For dates or times, format them appropriately or leave them as TBD if completely unspecified. "  # noqa: E501
        f"Output ONLY a raw JSON array matching this structure. Do NOT include markdown blocks like ```json ... ```, just the array itself."  # noqa: E501
    )

    plan_steps: list[Step] = []
    
    try:
        llm_resp = await route_llm_call(prompt, request_type="planning")
        raw_json = llm_resp.text.strip()
        # Clean markdown if present
        if raw_json.startswith("```json"):
            raw_json = raw_json[7:]
        if raw_json.startswith("```"):
            raw_json = raw_json[3:]
        if raw_json.endswith("```"):
            raw_json = raw_json[:-3]
        raw_json = raw_json.strip()
        
        parsed = json.loads(raw_json)
        if not isinstance(parsed, list):
            raise ValueError("LLM did not return a JSON array")
        
        for item in parsed:
            plan_steps.append(
                Step(
                    tool_name=item["tool_name"],
                    mcp_server=item["mcp_server"],
                    input_params=item.get("input_params", {}),
                )
            )
    except Exception:
        logger.error("plan: LLM generation failed or returned invalid JSON, falling back to template", exc_info=True)  # noqa: E501
        # Fall back to template plan if LLM goes crazy
        plan_steps = template_steps

    # --- DB write 2: INSERT task_plans row ---
    plan_json = [dict(s) for s in plan_steps]
    plan_id: str | None = None
    try:
        result = (
            supabase_admin.table("task_plans")
            .insert(
                {
                    "task_id": state["task_id"],
                    "planner_version": PLANNER_VERSION,
                    "plan_json": plan_json,
                    "status": "draft",
                }
            )
            .execute()
        )
        if result.data:
            plan_id = result.data[0]["id"]
            logger.info(
                "plan: task_plans row created plan_id=%s task_id=%s",
                plan_id,
                state["task_id"],
            )
    except Exception:
        logger.error(
            "plan: failed to insert task_plans [task_id=%s]",
            state["task_id"],
            exc_info=True,
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    _log_event(
        task_id=state["task_id"],
        agent_name="planner",
        event_type="plan_created",
        payload={"plan": plan_json, "source": "llm", "plan_id": plan_id},
        latency_ms=latency_ms,
    )
    return {"plan": plan_steps, "plan_id": plan_id}


# ---------------------------------------------------------------------------
# Node: risk_tag
# ---------------------------------------------------------------------------


def risk_tag(state: AgentState) -> dict[str, Any]:
    """Tag each step with a risk tier using the real risk_rules table.

    This node is NOT stubbed — the fail-closed lookup against the DB is
    correct from day one per Section 9.2 of the project spec.

    Also writes plan_steps rows and updates task_plans.status → "active".
    """
    t0 = time.monotonic()
    steps: list[Step] = state.get("plan") or []
    plan_id: str | None = state.get("plan_id")
    risk_flags: dict[int, RiskDecision] = {}

    for idx, step in enumerate(steps):
        rule = lookup(step["tool_name"], step["mcp_server"])

        if rule is None:
            # Fail-closed: unknown action defaults to high / requires_approval.
            decision = RiskDecision(
                risk_tier="high",
                requires_approval=True,
                rationale="no matching risk_rules entry — fail closed",
            )
            logger.warning(
                "risk_tag: no rule for tool=%s server=%s — defaulting to HIGH",
                step["tool_name"],
                step["mcp_server"],
            )
        else:
            decision = RiskDecision(
                risk_tier=rule.risk_tier,
                requires_approval=rule.requires_approval,
                rationale=rule.rationale,
            )

        risk_flags[idx] = decision

        # --- DB write: INSERT plan_steps row ---
        if plan_id:
            try:
                step_result = (
                    supabase_admin.table("plan_steps")
                    .insert(
                        {
                            "plan_id": plan_id,
                            "step_index": idx,
                            "tool_name": step["tool_name"],
                            "mcp_server": step["mcp_server"],
                            "input_params": step["input_params"],
                            "risk_tier": decision["risk_tier"],
                            "requires_approval": decision["requires_approval"],
                            "status": "pending",
                        }
                    )
                    .execute()
                )
                step_id = step_result.data[0]["id"] if step_result.data else None
            except Exception:
                logger.error(
                    "risk_tag: failed to insert plan_steps [plan_id=%s step=%d]",
                    plan_id,
                    idx,
                    exc_info=True,
                )
                step_id = None
        else:
            step_id = None

        _log_event(
            task_id=state["task_id"],
            agent_name="risk_gate",
            event_type="risk_tagged",
            payload={
                "step_index": idx,
                "tool_name": step["tool_name"],
                "mcp_server": step["mcp_server"],
                **decision,
            },
            step_id=step_id,
        )

    # --- DB write: UPDATE task_plans.status → "active" ---
    if plan_id:
        try:
            supabase_admin.table("task_plans").update({"status": "active"}).eq("id", plan_id).execute()  # noqa: E501
        except Exception:
            logger.warning(
                "risk_tag: failed to set task_plans active [plan_id=%s]",
                plan_id,
                exc_info=True,
            )

    latency_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "risk_tag: tagged %d steps for task_id=%s [%dms]",
        len(steps),
        state["task_id"],
        latency_ms,
    )
    return {"risk_flags": risk_flags}


# ---------------------------------------------------------------------------
# Node: execute
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2  # seconds; retry 1→2s, 2→4s, 3→8s


def route_step(state: AgentState) -> str:
    """Conditional router after risk_tag, execute, or approval_gate."""
    steps = state.get("plan") or []
    current = state.get("current_step_index", 0)

    # If all steps are done, task is completed
    if current >= len(steps):
        try:
            supabase_admin.table("tasks").update({"status": "completed"}).eq(
                "id", state["task_id"]
            ).execute()
        except Exception:
            pass
        return "END"

    risk_flags = state.get("risk_flags", {})
    decision = risk_flags.get(current, {})

    if decision.get("requires_approval", True):
        return "approval_gate"
    return "execute"


def approval_gate_node(state: AgentState) -> dict[str, Any]:
    """Halt the graph if human approval is needed."""
    from app.risk.approval_gate import gate

    steps = state.get("plan") or []
    current = state.get("current_step_index", 0)
    step = steps[current]

    risk_flags = state.get("risk_flags", {})
    decision = risk_flags.get(current, {})

    plan_id = state.get("plan_id")
    task_id = state["task_id"]

    # Get step_id from DB
    step_id = None
    if plan_id:
        try:
            res = (
                supabase_admin.table("plan_steps")
                .select("id")
                .eq("plan_id", plan_id)
                .eq("step_index", current)
                .execute()
            )
            if res.data:
                step_id = res.data[0]["id"]
        except Exception:
            pass

    # gate() will halt if requires_approval, and return decision when resumed
    user_decision = gate(
        step=step,
        decision=decision,
        task_id=task_id,
        user_id=state["user_id"],
        plan_id=plan_id,
        step_index=current,
        step_id=step_id,
    )

    if user_decision == "rejected":
        # log skip
        _log_event(
            task_id=task_id,
            agent_name="risk_gate",
            event_type="step_skipped",
            payload={"step_index": current, "reason": "human_rejected"},
            step_id=step_id,
        )
        try:
            supabase_admin.table("tasks").update({"status": "failed"}).eq("id", task_id).execute()
        except Exception:
            pass
        # returning error halts the graph implicitly
        return {"error": "human_rejected"}

    # If approved, route_step will naturally route it to execute because we don't
    # increment current_step_index here
    # Wait, if we return nothing, route_step will be called again.
    # But route_step checks requires_approval, which is still True!
    # If it's True, it will route to approval_gate AGAIN!
    # We must modify risk_flags or update the node logic.
    # Actually, we can return a modification to risk_flags:
    risk_flags_updated = dict(risk_flags)
    decision_updated = dict(decision)
    decision_updated["requires_approval"] = False
    risk_flags_updated[current] = decision_updated
    return {"risk_flags": risk_flags_updated}


def execute(state: AgentState) -> dict[str, Any]:
    """Execute exactly ONE step (current_step_index)."""
    if state.get("error"):
        return {}

    steps = state.get("plan") or []
    idx = state.get("current_step_index", 0)

    if idx >= len(steps):
        return {}

    step = steps[idx]
    plan_id = state.get("plan_id")
    task_id = state["task_id"]
    user_id = state["user_id"]

    idempotency_key = f"{plan_id}:{idx}"

    attempt = 0
    result = None
    retries = state.get("retries", {})

    while attempt < _MAX_RETRIES:
        attempt += 1
        _log_event(
            task_id=task_id,
            agent_name="executor",
            event_type="step_started",
            payload={
                "step_index": idx,
                "tool_name": step["tool_name"],
                "mcp_server": step["mcp_server"],
                "attempt": attempt,
            },
        )

        result = call_tool(
            tool_name=step["tool_name"],
            mcp_server=step["mcp_server"],
            input_params=step["input_params"],
            user_id=user_id,
            idempotency_key=idempotency_key,
            task_id=task_id,
        )

        if result["status"] == "success":
            break

        if result["status"] in ("rate_limited", "error") and attempt < _MAX_RETRIES:
            backoff = _RETRY_BACKOFF_BASE**attempt
            time.sleep(backoff)
        else:
            break

    # Write result to DB
    step_status = "completed" if result and result["status"] == "success" else "failed"
    _log_event(
        task_id=task_id,
        agent_name="executor",
        event_type="step_completed" if step_status == "completed" else "step_failed",
        payload={
            "step_index": idx,
            "tool_name": step["tool_name"],
            "status": step_status,
            "output": result.get("output") if result else None,
            "error": result.get("error") if result else "no result",
            "latency_ms": result.get("latency_ms") if result else None,
            "attempts": attempt,
        },
        latency_ms=result.get("latency_ms") if result else None,
    )

    if plan_id:
        try:
            supabase_admin.table("plan_steps").update(
                {
                    "status": step_status,
                    "result": result.get("output") if result else None,
                    "error_message": result.get("error") if result else "no result",
                }
            ).eq("plan_id", plan_id).eq("step_index", idx).execute()
        except Exception:
            pass

    step_results = dict(state.get("step_results", {}))
    step_results[idx] = result

    retries_out = dict(retries)
    retries_out[idx] = attempt - 1

    if step_status == "failed":
        try:
            supabase_admin.table("tasks").update({"status": "failed"}).eq("id", task_id).execute()
        except Exception:
            pass
        return {"step_results": step_results, "retries": retries_out, "error": "step_failed"}

    return {"step_results": step_results, "retries": retries_out, "current_step_index": idx + 1}
