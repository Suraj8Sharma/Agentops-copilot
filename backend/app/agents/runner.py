"""Planner runner — entry-point called from the FastAPI background task.

``run_planner`` is the single function that:
  1. Builds the compiled graph (cached at module level after first call).
  2. Constructs the initial AgentState from the task row and current user.
  3. Invokes the graph synchronously (safe inside a FastAPI BackgroundTask
     since it runs in a thread-pool worker, not the event loop).
  4. Catches any unhandled exception and marks the task as failed so the
     user never sees a permanently-stuck "submitted" task.

The graph runs: intent_classify → plan → risk_tag → END  (D13 skeleton).
"""

from __future__ import annotations

import logging

from app.agents.graph import build_graph
from app.agents.state import AgentState
from app.core.security import CurrentUser
from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level compiled graph — built once, reused across requests.
# ---------------------------------------------------------------------------
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------


def run_planner(task_id: str, user: CurrentUser) -> None:
    """Invoke the planner graph for the given task.

    Called as a FastAPI ``BackgroundTask`` after ``POST /tasks`` inserts
    the task row.  The caller (``POST /tasks``) has already returned a 201
    response to the client before this function runs.

    Args:
        task_id: UUID string of the tasks row (status = "submitted").
        user:    The authenticated CurrentUser whose JWT created this task.
    """
    logger.info("run_planner: starting [task_id=%s user_id=%s]", task_id, user.id)

    initial_state = AgentState(
        task_id=task_id,
        user_id=user.id,
        raw_input=_fetch_raw_input(task_id),
        input_type="text",      # voice tasks always arrive with transcription_text
                                # already populated — treated as text here for D13
        intent="",
        plan=[],
        plan_id=None,
        risk_flags={},
        error=None,
    )

    try:
        final_state = _get_graph().invoke(
            initial_state,
            config={"configurable": {"thread_id": task_id}},
        )
        if final_state.get("error"):
            logger.warning(
                "run_planner: graph completed with error [task_id=%s error=%s]",
                task_id,
                final_state["error"],
            )
        else:
            logger.info(
                "run_planner: graph completed successfully [task_id=%s]",
                task_id,
            )
    except Exception:
        logger.error(
            "run_planner: unhandled exception [task_id=%s]",
            task_id,
            exc_info=True,
        )
        # Best-effort: mark the task failed so it does not stay "submitted".
        try:
            supabase.table("tasks").update({"status": "failed"}).eq(
                "id", task_id
            ).execute()
        except Exception:
            logger.error(
                "run_planner: also failed to mark task as failed [task_id=%s]",
                task_id,
                exc_info=True,
            )


def _fetch_raw_input(task_id: str) -> str:
    """Retrieve raw_input / transcription_text from the tasks row.

    Falls back to an empty string if the row cannot be fetched — the
    intent_classify node will classify it as "unclassified" and the plan
    node will handle that gracefully.
    """
    try:
        result = (
            supabase.table("tasks")
            .select("raw_input, transcription_text, input_type")
            .eq("id", task_id)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            # Prefer transcription_text for voice tasks (already populated by STT client).
            return row.get("transcription_text") or row.get("raw_input") or ""
    except Exception:
        logger.warning(
            "_fetch_raw_input: could not fetch task row [task_id=%s]",
            task_id,
            exc_info=True,
        )
    return ""
