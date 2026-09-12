import os
import sys

# 1. Update nodes.py
nodes_file = "app/agents/nodes.py"
with open(nodes_file, "r") as f:
    nodes_code = f.read()

# We want to replace the `execute` node entirely and add `approval_gate_node` and `route_step`.
execute_start = nodes_code.find("def execute(state: AgentState) -> dict[str, Any]:")
if execute_start == -1:
    print("Could not find execute in nodes.py")
    sys.exit(1)

new_execute_and_gate_code = """
def route_step(state: AgentState) -> str:
    \"\"\"Conditional router after risk_tag, execute, or approval_gate.\"\"\"
    steps = state.get("plan") or []
    current = state.get("current_step_index", 0)
    
    # If all steps are done, task is completed
    if current >= len(steps):
        try:
            supabase.table("tasks").update({"status": "completed"}).eq("id", state["task_id"]).execute()
        except Exception:
            pass
        return "END"
        
    risk_flags = state.get("risk_flags", {})
    decision = risk_flags.get(current, {})
    
    if decision.get("requires_approval", True):
        return "approval_gate"
    return "execute"

def approval_gate_node(state: AgentState) -> dict[str, Any]:
    \"\"\"Halt the graph if human approval is needed.\"\"\"
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
            res = supabase.table("plan_steps").select("id").eq("plan_id", plan_id).eq("step_index", current).execute()
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
        step_id=step_id
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
            supabase.table("tasks").update({"status": "failed"}).eq("id", task_id).execute()
        except:
            pass
        # returning error halts the graph implicitly
        return {"error": "human_rejected"}
        
    # If approved, route_step will naturally route it to execute because we don't increment current_step_index here
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
    \"\"\"Execute exactly ONE step (current_step_index).\"\"\"
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
            supabase.table("plan_steps").update(
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
            supabase.table("tasks").update({"status": "failed"}).eq("id", task_id).execute()
        except:
            pass
        return {"step_results": step_results, "retries": retries_out, "error": "step_failed"}
        
    return {
        "step_results": step_results,
        "retries": retries_out,
        "current_step_index": idx + 1
    }
"""

nodes_code = nodes_code[:execute_start] + new_execute_and_gate_code

# We must also replace the `lookup` inside risk_tag with `evaluate`.
old_risk_tag_start = nodes_code.find("rule = lookup(step[\\\"tool_name\\\"], step[\\\"mcp_server\\\"])")
old_risk_tag_end = nodes_code.find("risk_flags[idx] = decision") + len("risk_flags[idx] = decision")

new_risk_tag_code = """from app.risk.approval_gate import evaluate
        decision = evaluate(step)
        risk_flags[idx] = decision"""

if old_risk_tag_start != -1:
    nodes_code = nodes_code[:old_risk_tag_start] + new_risk_tag_code + nodes_code[old_risk_tag_end:]

with open(nodes_file, "w") as f:
    f.write(nodes_code)

# 2. Update graph.py
graph_file = "app/agents/graph.py"
new_graph_code = """
from __future__ import annotations
from langgraph.graph import END, StateGraph
from app.agents.nodes import execute, intent_classify, plan, risk_tag, route_step, approval_gate_node
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
    
    builder.add_conditional_edges("risk_tag", route_step, {"approval_gate": "approval_gate", "execute": "execute", "END": END})
    builder.add_conditional_edges("approval_gate", route_step, {"approval_gate": "approval_gate", "execute": "execute", "END": END})
    builder.add_conditional_edges("execute", route_step, {"approval_gate": "approval_gate", "execute": "execute", "END": END})
    
    return builder.compile(checkpointer=checkpointer)
"""
with open(graph_file, "w") as f:
    f.write(new_graph_code)

# 3. Update runner.py
runner_file = "app/agents/runner.py"
new_runner_code = """
from __future__ import annotations
import logging
import contextlib
from typing import AsyncIterator

from app.core.config import settings
from app.agents.graph import build_graph
from app.agents.state import AgentState
from app.core.security import CurrentUser
from app.db.supabase_client import supabase
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from langgraph.types import Command

logger = logging.getLogger(__name__)

_pool = None
_checkpointer = None
_graph = None

@contextlib.asynccontextmanager
async def checkpointer_lifespan() -> AsyncIterator[None]:
    global _pool, _checkpointer, _graph
    logger.info("Setting up langgraph Postgres checkpointer...")
    pool = AsyncConnectionPool(
        conninfo=settings.LANGGRAPH_CHECKPOINTER_DB_URI,
        max_size=10,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0
        }
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
    initial_state = AgentState(
        task_id=task_id,
        user_id=user.id,
        raw_input=_fetch_raw_input(task_id),
        input_type="text",
        intent="",
        plan=[],
        plan_id=None,
        risk_flags={},
        error=None,
    )
    try:
        final_state = await _graph.ainvoke(
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
            supabase.table("tasks").update({"status": "failed"}).eq("id", task_id).execute()
        except Exception:
            pass

async def resume_planner(task_id: str, decision: str) -> None:
    try:
        await _graph.ainvoke(
            Command(resume=decision),
            config={"configurable": {"thread_id": task_id}},
        )
    except Exception:
        logger.error("resume_planner: unhandled exception", exc_info=True)

def _fetch_raw_input(task_id: str) -> str:
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
            return row.get("transcription_text") or row.get("raw_input") or ""
    except Exception:
        pass
    return ""
"""
with open(runner_file, "w") as f:
    f.write(new_runner_code)

# 4. Update main.py to use checkpointer_lifespan
main_file = "app/main.py"
with open(main_file, "r") as f:
    main_code = f.read()
    
# Replace lifespan
start_lifespan = main_code.find("@asynccontextmanager")
end_lifespan = main_code.find("app = FastAPI(")

new_lifespan_code = """
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("AgentOps Copilot API starting up.")
    probe_connection()
    from app.agents.runner import checkpointer_lifespan
    async with checkpointer_lifespan():
        logger.info("Startup complete - server ready.")
        yield
    logger.info("AgentOps Copilot API shutting down.")

"""
main_code = main_code[:start_lifespan] + new_lifespan_code + main_code[end_lifespan:]

with open(main_file, "w") as f:
    f.write(main_code)

print("Patch applied successfully.")
