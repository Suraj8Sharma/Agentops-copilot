# LangGraph Planner Skeleton — Technical Spec (D13)

**Project:** AgentOps Copilot
**Plan reference:** D13 — "LangGraph skeleton — intent_classify → plan → risk_tag nodes" (Section 14)
**Owner / track:** Suraj — backend
**Branch:** `feature/langgraph-skeleton`
**Files (new / modified):**
- `backend/app/agents/state.py` (new — AgentState TypedDict)
- `backend/app/agents/nodes.py` (new — node functions: intent_classify, plan, risk_tag)
- `backend/app/agents/graph.py` (new — LangGraph StateGraph definition, linear 3-node chain)
- `backend/app/agents/runner.py` (new — entry-point that boots the graph for a task)
- `backend/app/risk/risk_rules.py` (new — `lookup(tool_name, mcp_server)` against the seeded `risk_rules` table)
- `backend/app/api/routers/tasks.py` (modify — POST /tasks triggers the skeleton graph after DB insert)
- `backend/requirements.txt` (add `langgraph`)

**Status going into this spec:** D11 complete (`POST /tasks` writes status `submitted`; `task_plans` and `plan_steps` tables exist). D12 complete (`risk_rules` table seeded with rows — no Python lookup function written yet). The `agents/` directory has only an empty `__init__.py`.

---

## 1. Objective

Build and wire the **first three nodes only** of the planner graph (Section 8.1):

```
intent_classify → plan → risk_tag
```

This is a skeleton: the goal is to prove the graph shape, state-passing between nodes, and the DB writes for `task_plans` / `plan_steps` all work correctly — not to produce an intelligent planner. No LLM calls happen today; `intent_classify` and `plan` use deterministic stand-in logic so the pipeline is testable without any external API key.

**Explicitly not built today:**
- The `execute` node
- The `approval_gate` node
- The conditional fork on `requires_approval` (Section 8.1's full diagram)
- Any live LLM call (Groq/Gemini) — that's the D18 LLM Router
- `POST /approvals/{step_id}` — that's D17

The graph **terminates after `risk_tag`** for now. There is nothing downstream yet to hand off to.

---

## 2. LangGraph State Schema

`backend/app/agents/state.py`:

```python
from typing import TypedDict, Optional

class Step(TypedDict):
    tool_name: str
    mcp_server: str        # "calendar" | "gmail" | "github" | "slack"
    input_params: dict

class RiskDecision(TypedDict):
    risk_tier: str          # "low" | "medium" | "high"
    requires_approval: bool
    rationale: str

class AgentState(TypedDict):
    task_id: str            # Also the LangGraph checkpointer thread_id
    user_id: str
    raw_input: str
    input_type: str         # "text" | "voice"
    intent: str
    plan: list[Step]
    plan_id: Optional[str]  # UUID of the task_plans row, set after plan node
    risk_flags: dict[int, RiskDecision]
    error: Optional[str]
```

Only the fields these three nodes actually touch are included. `current_step_index`, `step_results`, `approval_status`, and `retries` from the full Section 8.1 schema are deferred to whichever day introduces the node that first reads or writes them (`execute` → D14–16, `approval_gate` → D17).

---

## 3. Node Sequence & Graph Edges

```
intent_classify
      │
      ▼
    plan
      │
      ▼
  risk_tag
      │
      ▼
   (end)
```

Straight-line `StateGraph`, no conditional edges yet. `risk_tag` is the graph's exit node for D13.

### 3.1 Node: `intent_classify`

- **Input:** `state.raw_input`, `state.input_type`
- **Action (D13 stub — no LLM):** Deterministic keyword match against `raw_input` (e.g. contains "email"/"send" → `"send_email"`; contains "schedule"/"meeting"/"call" → `"schedule_event"`; contains "issue"/"bug" → `"file_issue"`; else → `"unclassified"`). This exists purely to give `plan` something non-trivial to branch on — replaced by a real LLM call on D18.
- **Output:** Sets `state.intent`.
- **Execution log event:** `plan_created` with payload `{"intent": intent, "source": "stub"}`.

### 3.2 Node: `plan`

- **Input:** `state.intent`, `state.user_id`
- **Action (D13 stub — no LLM):** A small hardcoded lookup table mapping `intent` → a fixed `list[Step]` template (e.g. `"schedule_event"` → one `calendar.create_event` step with placeholder `input_params`; `"send_email"` → one `gmail.send_message` step; `"unclassified"` → empty plan + `state.error = "could not classify intent"`).
- **DB writes:**
  1. INSERT into `task_plans` → `{task_id, planner_version: "skeleton-v0", plan_json, status: "draft"}` → capture returned `id` as `state.plan_id`.
  2. UPDATE `tasks.status = "planning"`.
- **Output:** Sets `state.plan`.
- **Execution log event:** `plan_created` with the full stub plan JSON, payload flagged `"source": "stub"`.

### 3.3 Node: `risk_tag`

- **Input:** `state.plan`
- **Action:** For each step, call the new `app.risk.risk_rules.lookup(tool_name, mcp_server)` function against the real, D12-seeded `risk_rules` table (this is a genuine DB read, not stubbed — the fail-closed behavior needs to be real from day one per Section 9.2). Returns `RiskDecision`; defaults to `{risk_tier: "high", requires_approval: true, rationale: "no matching risk_rules entry — fail closed"}` on no match.
- **DB writes:** For each step, INSERT into `plan_steps` → `{plan_id, step_index, tool_name, mcp_server, input_params, risk_tier, requires_approval, status: "pending"}`. UPDATE `task_plans.status = "active"`.
- **Output:** Sets `state.risk_flags`.
- **Execution log events:** One `risk_tagged` row per step.
- **Note:** `tasks.status` stays at `"planning"` after this node — there is no `execute` or `approval_gate` node yet to advance it further. This is expected and matches the day-by-day gap the manual builds in deliberately (Section 13: "a screen's build day and its wire-to-real-data day are sometimes weeks apart... not slippage" — same principle applies to the planner's phases).

---

## 4. `risk_rules.py` — New in D13

`backend/app/risk/risk_rules.py`:

```python
def lookup(tool_name: str, mcp_server: str) -> RiskDecision:
    """Flat read against the risk_rules table. No LLM. Fail-closed on no match."""
    ...
```

This function did not exist after D12 (D12 was seeding the table only — a transcription task, not a logic task). It is genuinely new work today, and it is the one piece of "real" logic in an otherwise stub-driven day, because `risk_tag`'s fail-closed behavior needs to be correct immediately, not deferred.

---

## 5. Endpoint: `POST /tasks` — Modified

After the existing DB insert, add:

```python
background_tasks.add_task(run_planner, task_id=result.data[0]["id"], user=current_user)
```

`run_planner` (in `backend/app/agents/runner.py`) boots the graph and calls `graph.invoke(initial_state, config={"configurable": {"thread_id": task_id}})`. The graph runs `intent_classify → plan → risk_tag` and stops.

**Signature change:** Add `background_tasks: BackgroundTasks` as a FastAPI dependency parameter. Response shape unchanged (`TaskOut`, 201 Created) — the graph runs asynchronously after the response is already sent.

No new `GET /tasks/{id}/plan` endpoint today — that's reasonable to build once there's more than a risk-tagged, going-nowhere plan to show (tie it to D14+ once `execute` exists, or pull it forward later if you want to visually confirm `risk_tag` output sooner).

---

## 6. Database Interactions

No new migrations required — D11 and D12 migrations already cover `task_plans`, `plan_steps`, `risk_rules`.

| Table | When | Client |
|---|---|---|
| `tasks` | `status` → `"planning"` in `plan` node | service-role |
| `task_plans` | One INSERT in `plan` node, one UPDATE in `risk_tag` | service-role |
| `plan_steps` | N INSERTs in `risk_tag` node | service-role |
| `execution_logs` | One row per node event | service-role |

**Checkpointer:** In-memory (`MemorySaver`) is sufficient for D13 — there's no pause/resume behavior yet since `approval_gate` doesn't exist. A Postgres-backed checkpointer is correctly deferred to D17.

---

## 7. Config / Env

**No new environment variables required today.** `GROQ_API_KEY` and `GEMINI_API_KEY` stay marked "required from D18" in `.env.example` — unchanged.

Reused from prior days: `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` for the service-role client (D8).

---

## 8. Security Notes

- `user_id` comes from the JWT via `get_current_user`, never from the request body.
- The stub `intent_classify` / `plan` logic contains no external input execution — it only produces `input_params` JSON, which is not called against any real service today (MCP clients don't exist until D14–16).
- `risk_tag`'s fail-closed default is real and enforced today, even though nothing executes yet — this is intentionally not stubbed, since it's cheap to get right now and Section 9.2 treats it as non-negotiable from the moment any risk-tagging exists.

---

## 9. Out of Scope for D13

- LLM Router (Groq/Gemini) — **D18**
- Real `intent_classify` / `plan` LLM calls — **D18** (today's versions are deterministic stubs)
- `execute` node, real MCP tool calls — **D14 (Calendar) → D16 (GitHub/Slack)**
- `approval_gate` node, `approvals` table writes, `POST /approvals/{step_id}` — **D17**
- Postgres-backed LangGraph checkpointer — **D17**
- `GET /tasks/{id}/plan` endpoint — safe to pull forward, but not required by D13's line item; natural home is once `execute` exists

---

## 10. Acceptance / Test Criteria

- `test_graph_runs_three_nodes_in_order`: Invoking the graph with a valid initial state runs `intent_classify → plan → risk_tag` in order and terminates without error.
- `test_intent_classify_stub_maps_known_keywords`: Raw input containing scheduling language sets `state.intent = "schedule_event"`; email language sets `"send_email"`; unmatched input sets `"unclassified"`.
- `test_plan_writes_task_plans_row`: After the `plan` node runs, one `task_plans` row exists for the task with `status = "draft"` then `"active"` after `risk_tag`.
- `test_plan_sets_task_status_to_planning`: `tasks.status` transitions from `submitted` → `planning` and stays there after the graph completes (no further node exists to advance it).
- `test_risk_tag_writes_plan_steps_with_correct_tiers`: For a known `tool_name`/`mcp_server` pair in the seeded `risk_rules` table, the resulting `plan_steps` row's `risk_tier` and `requires_approval` match the DB row exactly.
- `test_risk_tag_fails_closed_on_unknown_action`: A step with a `tool_name` not present in `risk_rules` results in `risk_tier = "high"`, `requires_approval = true`.
- `test_execution_logs_written_per_node`: After a run, `execution_logs` contains at least one row each for `plan_created` (x2 — intent + plan) and `risk_tagged` (one per step), all linked to the correct `task_id`.
- `test_unclassified_intent_sets_task_error`: An input that stub-classifies as `"unclassified"` results in `state.error` set and `tasks.status = "failed"`.

---

## 11. Dependencies

- **D11 complete** — `task_plans`, `plan_steps` tables exist; `POST /tasks` writes a `tasks` row with `status = "submitted"`.
- **D12 complete** — `risk_rules` table seeded (the lookup function itself is new today, per Section 4 above).
- **D5 complete** — `get_current_user` JWT dependency available in `app.core.security`.
- **D8 complete** — Supabase service-role client pattern established.
- **New Python packages:** `langgraph>=0.2` only — no `langchain-groq` / `langchain-google-genai` needed until D18.