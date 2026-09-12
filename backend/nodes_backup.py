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
from app.db.supabase_client import supabase
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
    """Write one row to execution_logs (best-effort — never raises)."""
    try:
        row: dict[str, Any] = {
            "task_id": task_id,
            "agent_name": agent_name,
            "event_type": event_type,
            "payload": payload,
        }
        if step_id is not None:
            row["step_id"] = step_id
        if latency_ms is not None:
            row["latency_ms"] = latency_ms
        supabase.table("execution_logs").insert(row).execute()
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


def intent_classify(state: AgentState) -> dict[str, Any]:
    """Classify the user's raw_input into a one-of-N intent label.

    D13 stub: deterministic keyword matching.
    D18 replacement: Groq/Gemini LLM call with a classification prompt.
    """
    t0 = time.monotonic()
    raw = (state.get("raw_input") or "").lower()

    # Order matters: more specific or read-only intents are checked first
    # to avoid "show me my calendar" being swallowed by the schedule branch.
    if any(k in raw for k in ("issue", "bug", "ticket", "github")):
        intent = "file_issue"
    elif any(k in raw for k in ("check", "list", "show", "what", "when")):
        # Read-only queries — show/list calendar, check events, etc.
        intent = "read_calendar"
    elif any(k in raw for k in ("email", "send", "mail")):
        intent = "send_email"
    elif any(k in raw for k in ("schedule", "meeting", "call", "calendar", "event")):
        if any(k in raw for k in ("professor", "external", "outside", "@")):
            intent = "schedule_event_external"
        else:
            intent = "schedule_event"
    else:
        intent = "unclassified"

    latency_ms = int((time.monotonic() - t0) * 1000)
    _log_event(
        task_id=state["task_id"],
        agent_name="planner",
        event_type="plan_created",
        payload={"intent": intent, "source": "stub"},
        latency_ms=latency_ms,
    )
    logger.info("intent_classify: task_id=%s intent=%s", state["task_id"], intent)
    return {"intent": intent}


# ---------------------------------------------------------------------------
# Node: plan
# ---------------------------------------------------------------------------


def plan(state: AgentState) -> dict[str, Any]:
    """Produce a list[Step] from the intent and write a task_plans row.

    D13 stub: hardcoded lookup table keyed by intent label.
    D18 replacement: LLM structured output (JSON array of Steps).
    """
    t0 = time.monotonic()
    intent = state.get("intent", "unclassified")

    if intent == "unclassified":
        # Fail immediately — nothing to plan.
        _log_event(
            task_id=state["task_id"],
            agent_name="planner",
            event_type="error",
            payload={"reason": "could not classify intent", "source": "stub"},
        )
        try:
            supabase.table("tasks").update({"status": "failed"}).eq(
                "id", state["task_id"]
            ).execute()
        except Exception:
            logger.warning(
                "Failed to mark task failed [task_id=%s]", state["task_id"], exc_info=True
            )
        logger.warning("plan: unclassified intent for task_id=%s", state["task_id"])
        return {"plan": [], "plan_id": None, "error": "could not classify intent"}

    steps: list[Step] = _STUB_PLANS.get(intent, [])

    # --- DB write 1: UPDATE tasks.status → "planning" ---
    try:
        supabase.table("tasks").update({"status": "planning"}).eq("id", state["task_id"]).execute()
    except Exception:
        logger.warning(
            "Failed to set task status=planning [task_id=%s]",
            state["task_id"],
            exc_info=True,
        )

    # --- DB write 2: INSERT task_plans row ---
    plan_json = [dict(s) for s in steps]
    plan_id: str | None = None
    try:
        result = (
            supabase.table("task_plans")
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
        payload={"plan": plan_json, "source": "stub", "plan_id": plan_id},
        latency_ms=latency_ms,
    )
    return {"plan": steps, "plan_id": plan_id}


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
                    supabase.table("plan_steps")
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
            supabase.table("task_plans").update({"status": "active"}).eq("id", plan_id).execute()
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


def execute(state: AgentState) -> dict[str, Any]:
    """Execute all low-risk plan steps via official hosted remote MCP servers.

    High-risk steps (requires_approval=True) are skipped here — they will be
    handled by the approval_gate node (D17).  For now they are logged as
    'awaiting_approval' and left in pending status.

    Each low-risk step:
      - Calls the appropriate MCP client (routed by mcp_server field).
      - Retries up to 3 times on transient errors (exponential backoff).
      - Writes an execution_logs row before and after the MCP call.
      - Updates plan_steps.status to 'completed' or 'failed'.

    Final tasks.status:
      - 'completed'  — all non-approval steps finished successfully.
      - 'failed'     — any step failed after all retries.
      - 'planning'   — at least one step is awaiting_approval (D17 will advance).
    """
    steps: list[Step] = state.get("plan") or []
    risk_flags: dict[int, Any] = state.get("risk_flags") or {}
    plan_id: str | None = state.get("plan_id")
    task_id: str = state["task_id"]
    user_id: str = state["user_id"]

    # If a prior node already set an error (e.g. unclassified intent in plan),
    # skip execution entirely — tasks.status is already "failed".
    if state.get("error"):
        logger.info(
            "execute: skipping — state.error already set [task_id=%s error=%s]",
            task_id,
            state["error"],
        )
        return {"step_results": {}, "retries": {}, "current_step_index": 0}

    step_results: dict[int, Any] = {}
    retries: dict[int, int] = {}
    has_failure = False
    has_pending_approval = False

    for idx, step in enumerate(steps):
        idempotency_key = f"{plan_id}:{idx}"
        risk = risk_flags.get(idx, {})

        # --- Skip high-risk steps: approval required (D17) -------------------
        if risk.get("requires_approval", True):
            has_pending_approval = True
            logger.info(
                "execute: step %d requires approval — skipping [task_id=%s tool=%s]",
                idx,
                task_id,
                step["tool_name"],
            )
            _log_event(
                task_id=task_id,
                agent_name="executor",
                event_type="step_awaiting_approval",
                payload={"step_index": idx, "tool_name": step["tool_name"]},
            )
            continue

        # --- Execute with retry -----------------------------------------------
        attempt = 0
        result: dict[str, Any] | None = None

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
            )

            if result["status"] == "success":
                break

            # Transient: retry on rate_limited or timeout
            if result["status"] in ("rate_limited", "error") and attempt < _MAX_RETRIES:
                backoff = _RETRY_BACKOFF_BASE**attempt
                logger.warning(
                    "execute: step %d attempt %d/%d failed [%s] — retrying in %ds",
                    idx,
                    attempt,
                    _MAX_RETRIES,
                    result.get("error"),
                    backoff,
                )
                retries[idx] = attempt
                time.sleep(backoff)
            else:
                break

        retries[idx] = attempt - 1  # retries = extra attempts beyond the first

        # --- Write result to DB -----------------------------------------------
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

        # Update plan_steps row
        if plan_id:
            try:
                supabase.table("plan_steps").update(
                    {
                        "status": step_status,
                        "result": result.get("output") if result else None,
                        "error_message": result.get("error") if result else "no result",
                    }
                ).eq("plan_id", plan_id).eq("step_index", idx).execute()
            except Exception:
                logger.warning(
                    "execute: failed to update plan_steps [plan_id=%s step=%d]",
                    plan_id,
                    idx,
                    exc_info=True,
                )

        step_results[idx] = result
        if step_status == "failed":
            has_failure = True
            logger.error(
                "execute: step %d failed after %d attempts [task_id=%s tool=%s error=%s]",
                idx,
                attempt,
                task_id,
                step["tool_name"],
                result.get("error") if result else "unknown",
            )
            break  # halt on first failure — do not run subsequent steps

    # --- Update tasks.status -------------------------------------------------
    if has_failure:
        final_status = "failed"
    elif has_pending_approval:
        # Leave at "planning" — approval_gate (D17) will advance to "completed"
        final_status = "planning"
    else:
        final_status = "completed"

    try:
        supabase.table("tasks").update({"status": final_status}).eq("id", task_id).execute()
    except Exception:
        logger.warning(
            "execute: failed to update tasks.status [task_id=%s]", task_id, exc_info=True
        )

    logger.info(
        "execute: finished task_id=%s status=%s steps_run=%d",
        task_id,
        final_status,
        len(step_results),
    )
    return {
        "step_results": step_results,
        "retries": retries,
        "current_step_index": len(steps) - 1,
    }

