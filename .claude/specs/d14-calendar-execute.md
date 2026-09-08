# LangGraph Execute Node & Calendar MCP — Technical Spec (D14)

**Project:** AgentOps Copilot
**Plan reference:** D14 — "MCP client — Google Calendar (create/list events)"
**Owner / track:** Suraj — backend
**Branch:** `feature/d14-calendar-execute`
**Files (new / modified):**
- `backend/app/mcp_clients/calendar.py` (new — Google Calendar MCP client implementing the standard contract)
- `backend/app/agents/nodes.py` (modify — add `execute` node)
- `backend/app/agents/graph.py` (modify — add conditional edge from `risk_tag` to `execute` for low-risk steps)
- `backend/app/api/routers/tasks.py` (modify — potentially minor updates if needed)

**Status going into this spec:** D13 complete (the LangGraph skeleton runs `intent_classify → plan → risk_tag`). `task_plans`, `plan_steps`, and `execution_logs` tables are ready.

---

## 1. Objective

Build the **execute node** of the LangGraph planner and the **first MCP client (Google Calendar)**. 
Today, we are extending the graph to execute steps that do not require approval (low-risk steps).

**Explicitly not built today:**
- Gmail, GitHub, Slack MCP clients (D15-16).
- The `approval_gate` node (D17).
- Real LLM calls (D18).

---

## 2. MCP Client Contract

`backend/app/mcp_clients/calendar.py` must implement the standard envelope defined in Section 8.2:

- **Input:** `tool_name` (e.g. `calendar.create_event`), `mcp_server` (`calendar`), `input_params` (JSON), `idempotency_key` (`plan_id:step_index`).
- **Output:** `{ status: "success" | "error" | "rate_limited", output: dict, error: dict, latency_ms: int }`

Supported tools for D14 (Section 8.3):
- `calendar.list_events` (low risk)
- `calendar.find_free_slots` (low risk)
- `calendar.create_event_internal_only` (medium risk, auto-executes)
- `calendar.create_event_external_attendee` (high risk, requires approval)
- `calendar.update_event` (medium risk)
- `calendar.delete_event` (high risk)

---

## 3. Node Sequence & Graph Edges

```text
intent_classify
      │
      ▼
    plan
      │
      ▼
  risk_tag
      │
      ▼
[conditional]
      │
      ├── no approval needed ──▶ execute
      │                             │
      │                             ▼
      │                          [end]
      │
      └── requires approval ───▶ [end] (Approval gate is D17)
```

### 3.1 Node: `execute`

- **Input:** `state.plan`, `state.risk_flags`
- **Action:** 
  1. Iterate over steps. If `risk_flags[step_index].requires_approval` is false, call the appropriate MCP client.
  2. Implement retry logic for transient errors (exponential backoff up to 3 times) updating `state.retries`.
- **DB writes:** 
  1. INSERT into `execution_logs` with step payload and `latency_ms`.
  2. UPDATE `plan_steps` with step result and status.
- **Output:** Sets `state.step_results`.

---

## 4. Security Notes

- Use the OAuth tokens retrieved during the D8 token exchange phase to authenticate with the Google Calendar API.
- Validate `idempotency_key` on the provider side to prevent double-creates on retry.
- Any step requiring approval must hard-stop the graph for now.

---

## 5. Acceptance / Test Criteria

- `test_execute_node_runs_low_risk_calendar_tool`: A low-risk calendar step invokes the `calendar` MCP client, returns output, and writes to `execution_logs`.
- `test_execute_node_skips_high_risk_step`: A step flagged with `requires_approval = True` halts the graph before `execute`.
- `test_mcp_calendar_client_idempotency`: Retrying a `create_event` tool with the same `idempotency_key` does not create duplicate events.
- `test_execution_logs_latency`: The execute node correctly records `latency_ms` for the MCP call in `execution_logs`.
