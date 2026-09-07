"""LangGraph node functions for the D13 planner skeleton.

Three nodes are wired today:

    intent_classify  → plan  → risk_tag

None of these nodes make LLM calls (that is D18).  intent_classify and plan
use deterministic stub logic so the full pipeline can be tested without any
external API key.  risk_tag performs a real DB read against the seeded
risk_rules table — the fail-closed behaviour must be correct from day one.

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
        supabase.table("tasks").update({"status": "planning"}).eq(
            "id", state["task_id"]
        ).execute()
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
            supabase.table("task_plans").update({"status": "active"}).eq(
                "id", plan_id
            ).execute()
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
