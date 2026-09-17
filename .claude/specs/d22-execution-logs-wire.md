# Execution Logs Wire-Up — Technical Spec

**Project:** AgentOps Copilot
**Plan reference:** D22 — "execution_logs wire-up (all 4 MCP clients)"
**Owner / track:** Suraj — backend
**Branch:** `feature/d22-execution-logs-wire`
**Files:**
- `backend/app/mcp_clients/calendar.py` (modify)
- `backend/app/mcp_clients/gmail.py` (modify)
- `backend/app/mcp_clients/github.py` (modify)
- `backend/app/mcp_clients/slack.py` (modify)
- `backend/app/tests/test_execution_logs_wire.py` (new)

**Status going into this spec:**
The `execution_logs` table was pulled forward from D22 during D13 (migration `20260909000009_create_execution_logs.sql`). The planner (`agents/nodes.py`) and the approvals router already write real rows via `_log_event()`.

The 4 MCP clients are in two different states of incompleteness:

| Client | Current state |
|---|---|
| `github.py` | Has `async def _log_execution(...)` stub — only emits `logger.debug`, marked `# TODO(D22)` |
| `slack.py` | Has `async def _log_execution(...)` stub — only emits `logger.debug`, marked `# TODO(D22)` |
| `calendar.py` | No execution_logs write at all — only `logger.*` calls |
| `gmail.py` | No execution_logs write at all — only `logger.*` calls |

All 4 need to be wired.

---

## 1. Objective

Add a real `execution_logs` insert to all 4 MCP clients using the Supabase service-role client — matching the pattern already established in `agents/nodes.py::_log_event()`. No new migration or schema change is needed; the table and its CHECK constraints already exist.

---

## 2. Reference Implementation

`agents/nodes.py::_log_event()` is the canonical pattern — follow it exactly:

```python
# agents/nodes.py L41-69 (reference — DO NOT IMPORT, replicate the pattern)
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
        logger.warning(
            "execution_logs write failed [task_id=%s event_type=%s]",
            task_id,
            event_type,
            exc_info=True,
        )
```

Key rules:
- **Synchronous** (not async) — all 4 `call()` entrypoints are sync.
- **Best-effort** — catches all exceptions, falls back to `logger.warning`, never re-raises.
- Uses `supabase` already imported in all 4 files via `from app.db.supabase_client import supabase`.
- Required columns: `task_id`, `agent_name`, `event_type`, `payload`. Optional: `step_id`, `latency_ms`.

---

## 3. Implementation Steps

### 3.1 Add `_log_event_<provider>()` helper to each client

Add the following helper to each file. The only difference per file is `agent_name` and the warning prefix.

| File | `agent_name` value | Helper name |
|---|---|---|
| `calendar.py` | `"mcp_calendar"` | `_log_event_calendar` |
| `gmail.py` | `"mcp_gmail"` | `_log_event_gmail` |
| `github.py` | `"mcp_github"` | `_log_event_github` |
| `slack.py` | `"mcp_slack"` | `_log_event_slack` |

Template (substitute `<AGENT_NAME>` and `<PREFIX>`):

```python
def _log_event_<provider>(
    task_id: str,
    event_type: str,
    payload: dict[str, Any],
    step_id: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Write one row to execution_logs for a <Provider> MCP event (best-effort)."""
    try:
        row: dict[str, Any] = {
            "task_id": task_id,
            "agent_name": "<AGENT_NAME>",
            "event_type": event_type,
            "payload": payload,
        }
        if step_id is not None:
            row["step_id"] = step_id
        if latency_ms is not None:
            row["latency_ms"] = latency_ms
        supabase.table("execution_logs").insert(row).execute()
    except Exception:
        logger.warning(
            "execution_logs write failed [<PREFIX> task_id=%s event_type=%s]",
            task_id,
            event_type,
            exc_info=True,
        )
```

### 3.2 Thread `task_id` through `call()`

All 4 public `call()` signatures currently are:

```python
def call(tool_name, input_params, user_id, idempotency_key) -> dict
```

Add `task_id: str` as a parameter so it can be passed to the log helper:

```python
def call(tool_name, input_params, user_id, idempotency_key, task_id: str) -> dict
```

> **Note:** Check `mcp_clients/__init__.py` and `agents/nodes.py` (the execute node) to confirm they pass `task_id` when calling `call_tool()` — update the call-site if needed.

### 3.3 Call the helper at the right moments

Each `call()` function should emit **two** log rows per tool invocation:

| When | `event_type` | Required payload fields |
|---|---|---|
| Just before the HTTP call to the MCP server | `"tool_called"` | `tool_name`, `mcp_server`, `input_params` (sanitised — no tokens) |
| After receiving the result (success or error) | `"tool_result"` (success) / `"error"` (failure) | `tool_name`, `mcp_server`, `status`, `output` or `error_code` + `message` |

For `github.py` and `slack.py`: replace all existing calls to `_log_execution(...)` with the new helper and remove the stub + its `# TODO(D22)` comment.

For `calendar.py` and `gmail.py`: add new calls at the same two moments — before the `httpx.post(...)` call and after parsing the response.

**Security:** Never log raw OAuth tokens, full HTTP headers, or idempotency keys in the payload.

---

## 4. Schema Reminder (no changes needed)

Migration `20260909000009_create_execution_logs.sql` — table already live.

| Column | Notes |
|---|---|
| `task_id` | uuid, FK tasks(id) — **required** |
| `step_id` | uuid, FK plan_steps(id) — nullable, pass if available |
| `agent_name` | CHECK constraint includes `mcp_calendar`, `mcp_gmail`, `mcp_github`, `mcp_slack` |
| `event_type` | CHECK constraint includes `tool_called`, `tool_result`, `error` |
| `payload` | jsonb NOT NULL |
| `latency_ms` | int, nullable |
| `model_used` | leave NULL for MCP events |
| `tokens_used` | leave NULL for MCP events |
| `cost_estimate` | leave NULL for MCP events |

**RLS:** INSERT is service-role only. `supabase_client.py` uses `SUPABASE_SERVICE_ROLE_KEY` — no client changes needed.

---

## 5. Error Handling

- The log helper must **never raise** — a logging failure must not affect the MCP call result or the planner graph.
- If `task_id` is somehow unavailable, log with `task_id = "unknown"` and emit a `logger.warning` — do not skip the insert.

---

## 6. Out of Scope

- `agents/nodes.py` and `api/routers/approvals.py` — already wired correctly, no changes.
- New migrations — `execution_logs` table is already live.
- Digest or notification logging — D23/D24.

---

## 7. Acceptance / Test Criteria

Create `backend/app/tests/test_execution_logs_wire.py`. Use `unittest.mock.patch` on `supabase.table("execution_logs").insert(...).execute()` — no real DB calls in unit tests.

| Test | What it checks |
|---|---|
| `test_calendar_tool_called_writes_log` | `_log_event_calendar` inserts a row with `agent_name="mcp_calendar"`, `event_type="tool_called"` |
| `test_calendar_tool_result_writes_log` | After success, a `tool_result` row is written |
| `test_gmail_tool_called_writes_log` | `_log_event_gmail` inserts a row with `agent_name="mcp_gmail"` |
| `test_gmail_error_writes_log` | A 401 or send failure results in an `error` row |
| `test_github_tool_called_writes_log` | `_log_event_github` inserts with `agent_name="mcp_github"` |
| `test_github_tool_result_writes_log` | Success path writes a `tool_result` row |
| `test_github_error_writes_log` | 401/timeout results in an `error` row |
| `test_slack_tool_called_writes_log` | `_log_event_slack` inserts with `agent_name="mcp_slack"` |
| `test_slack_tool_result_writes_log` | Success path writes a `tool_result` row |
| `test_slack_error_writes_log` | Rate-limit or auth error results in an `error` row |
| `test_log_failure_does_not_crash_mcp_call` | If the Supabase insert raises, the MCP call result is still returned (no re-raise) — test for all 4 clients |

---

## 8. Dependencies

- D13 (planner + execution_logs migration pulled forward) — ✅ done
- D14 (calendar execute node) — ✅ done
- D15 (Gmail MCP client) — ✅ done
- D16 (GitHub MCP client with stub) — ✅ done
- D17 (Slack MCP client with stub) — ✅ done
- D21 (llm_usage_logs) — ✅ done; execution_logs wire is independent
