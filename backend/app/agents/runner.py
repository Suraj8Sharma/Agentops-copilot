from __future__ import annotations

import contextlib
import logging
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool

from app.agents.graph import build_graph
from app.agents.state import AgentState
from app.core.config import settings
from app.core.security import CurrentUser
from app.db.supabase_client import supabase_admin

logger = logging.getLogger(__name__)

_pool = None
_checkpointer = None
_graph = None


def get_graph():
    """Return the active compiled graph, falling back to an in-memory checkpointer."""
    global _graph
    if _graph is None:
        from langgraph.checkpoint.memory import MemorySaver

        _graph = build_graph(checkpointer=MemorySaver())
    return _graph


@contextlib.asynccontextmanager
async def checkpointer_lifespan() -> AsyncIterator[None]:
    global _pool, _checkpointer, _graph
    logger.info("Setting up langgraph Postgres checkpointer...")
    pool = AsyncConnectionPool(
        conninfo=settings.LANGGRAPH_CHECKPOINTER_DB_URI,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": None},
    )
    await pool.wait()
    _pool = pool
    _checkpointer = AsyncPostgresSaver(pool)
    await _checkpointer.setup()

    _graph = build_graph(checkpointer=_checkpointer)

    yield

    await pool.close()
    _pool = None
    _checkpointer = None
    _graph = None


async def run_planner(task_id: str, user: CurrentUser) -> None:
    logger.info("run_planner: starting [task_id=%s user_id=%s]", task_id, user.id)
    raw_input, input_type = _fetch_task_input(task_id)
    initial_state = AgentState(
        task_id=task_id,
        user_id=user.id,
        raw_input=raw_input,
        input_type=input_type,
        intent="",
        plan=[],
        plan_id=None,
        risk_flags={},
        current_step_index=0,
        step_results={},
        retries={},
        error=None,
    )
    try:
        graph = get_graph()
        final_state = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": task_id}},
        )
        if final_state.get("error"):
            logger.warning("run_planner: graph completed with error")
        else:
            logger.info("run_planner: graph completed successfully")
    except Exception:
        logger.error("run_planner: unhandled exception", exc_info=True)
        try:
            supabase_admin.table("tasks").update({"status": "failed"}).eq("id", task_id).execute()
        except Exception:
            pass


async def resume_planner(task_id: str, decision: str) -> None:
    try:
        graph = get_graph()
        await graph.ainvoke(
            Command(resume=decision),
            config={"configurable": {"thread_id": task_id}},
        )
    except Exception:
        logger.error("resume_planner: unhandled exception", exc_info=True)


def _fetch_task_input(task_id: str) -> tuple[str, str]:
    from app.db.supabase_client import supabase_admin

    try:
        result = (
            supabase_admin.table("tasks")
            .select("raw_input, transcription_text, input_type")
            .eq("id", task_id)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            raw = row.get("transcription_text") or row.get("raw_input") or ""
            input_type = row.get("input_type") or "text"
            return raw, input_type
    except Exception:
        pass
    return "", "text"


def _fetch_raw_input(task_id: str) -> str:
    raw, _ = _fetch_task_input(task_id)
    return raw
