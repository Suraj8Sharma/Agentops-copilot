---
name: d29-mcp-integration-test-suite
description: Technical specification for Suraj's Day 29 tasks - complete MCP Integration Test Suite (9 named tests) covering per-server connectivity, failure handling, timeout handling, and idempotency per Manual Section 14, Section 15.4, and Gate 3.
---

# D29 Spec: MCP Integration Test Suite — Connectivity, Failure Handling & Idempotency

**Task (Manual §14, §15.4, D29, Suraj):** MCP integration test suite — connectivity, failure handling, idempotency; all 9 named tests in `test_mcp_*.py`.  
**Date:** Fri 25 Sep 2026 · **Owner:** Suraj · **Source:** Manual v2.0 (§8.2, §8.3, §14, §15.4, §17 Gate 3, §18 A1, A2, A3, A6, A9).  
**Depends on:** D14 (Calendar MCP & execute node), D15 (Gmail MCP client), D16 (GitHub & Slack MCP clients), D17 (Approval gate), D28 (Sign-in/Sign-up test suite & OAuth bug fixes merged).  
**Status:** Ready for Implementation (Offline mock-only test suite, zero live credentials).  

---

## 1. Objective

Deliver the complete, production-grade **MCP Integration Test Suite** for AgentOps Copilot. By Day 28, individual MCP client stubs and unit tests were created across different PRs (D14–D17), but Section 14 and Section 15.4 of the Manual mandate a formal, unified MCP integration suite running under the `test_mcp_*.py` test discovery pattern before the Week 5 review and Gate 3 freeze.

The suite must validate four operational pillars across all four integrated MCP providers (**Google Calendar**, **Gmail**, **GitHub**, **Slack**):

1. **Per-Server Connectivity & Tool-Call Success:** Validating that every supported MCP server correctly translates tool parameters, invokes provider endpoints, measures latency, and returns the standard AgentOps envelope (`status`, `output`, `error`, `latency_ms`).
2. **Failure & Exception Handling:** Ensuring that external 401s (token revoked/expired), 403s (insufficient scopes), 429s (rate limits), and 5xx errors translate into clean, structured domain errors rather than uncaught Python exceptions.
3. **Timeout & Crash Resilience:** Proving that hanging external HTTP calls (>15s) trigger graceful timeout envelopes, and downed MCP servers fail the step and mark the parent task `failed` immediately without hanging or leaving the agent loop frozen.
4. **Idempotency & Duplicate Prevention:** Guaranteeing that retried steps (following network glitches or transient errors) never cause duplicate side-effects (e.g., duplicate calendar events, repeated emails, or multiple GitHub issues).

---

## 2. Architecture & Contracts

### 2.1 The Standard AgentOps MCP Envelope

Every tool call dispatched via `app.mcp_clients.call_tool` returns a uniform envelope:

```python
{
    "status": "success" | "error" | "rate_limited",
    "output": dict | None,
    "error": str | None,
    "latency_ms": int
}
```

- `"status": "success"`: The tool call completed; `output` contains the JSON response body from the provider, `error` is `None`.
- `"status": "rate_limited"`: The provider returned HTTP 429; the execute node may retry with exponential backoff.
- `"status": "error"`: The call failed due to client error, authentication expiry, network failure, or provider server error; `output` is `None`, `error` contains human-readable explanation.
- `"latency_ms"`: Monotonic elapsed time in milliseconds; persisted to `execution_logs` and aggregated on the Trust Dashboard (Acceptance A6).

### 2.2 Provider Architecture & Transport Mapping

AgentOps Copilot interfaces with four external providers through specialized client modules in `backend/app/mcp_clients/`:

| Provider | Client Module | Transport & Protocol | Auth Storage & Mechanism | Idempotency Mechanism |
|---|---|---|---|---|
| **Google Calendar** | `calendar.py` | Google Calendar REST API v3 (`https://www.googleapis.com/calendar/v3`) | `oauth_connections` (`google_calendar`), auto-refreshed via `google_token_refresh` | `X-Idempotency-Token: <plan_id>:<step_index>` request header |
| **Gmail** | `gmail.py` | Gmail REST API v1 (`https://gmail.googleapis.com/gmail/v1/users/me`) | `oauth_connections` (`gmail`), auto-refreshed via `google_token_refresh` | Application precheck: queries `plan_steps.status == 'done'` before send |
| **GitHub** | `github.py` | Copilot MCP Server (`https://api.githubcopilot.com/mcp/`) via Streamable SSE / JSON-RPC | `oauth_connections` (`github`), Fernet encrypted at rest | Session ID reuse + application precheck on `plan_steps.status` |
| **Slack** | `slack.py` | Slack MCP Server (`https://mcp.slack.com/mcp`) via JSON-RPC over HTTP | `oauth_connections` (`slack`), Fernet encrypted at rest | Application precheck: queries `plan_steps.status == 'done'` before write |

### 2.3 Router Interface (`mcp_clients/__init__.py`)

The LangGraph `execute` node communicates exclusively through `call_tool()`:

```python
def call_tool(
    tool_name: str,
    mcp_server: str,
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
    task_id: str = "unknown",
) -> dict[str, Any]:
    ...
```

If `mcp_server` is not registered in `_ROUTER`, `call_tool` returns an error envelope immediately without making network calls:
`{"status": "error", "output": None, "error": "no MCP client registered for provider '<mcp_server>'", "latency_ms": 0}`.

### 2.4 Execute Node & Task State Machine (`app/agents/nodes.py`)

When `nodes.execute()` executes a step:
1. It reads `state.plan[current_step_index]`.
2. It calls `call_tool()` with `idempotency_key = f"{plan_id}:{current_step_index}"`.
3. If `result["status"] == "rate_limited"` or transient error, it retries up to `_MAX_RETRIES` (3 attempts) with exponential backoff (`_RETRY_BACKOFF_BASE ** attempt`).
4. On success:
   - Logs `event_type="step_completed"` to `execution_logs`.
   - Updates `plan_steps` with `status="done"`, `output=result`.
   - Returns `{"current_step_index": idx + 1, "step_results": ...}`.
5. On terminal failure (e.g. MCP server down or timeout exhausted):
   - Logs `event_type="step_failed"` to `execution_logs`.
   - Updates `plan_steps` with `status="failed"`, `output=result`.
   - **Crucial:** Updates `tasks` table with `status="failed"`.
   - Returns `{"error": "step_failed", "step_results": ...}` which immediately halts the LangGraph workflow without hanging.

---

## 3. The 9 Named Tests Specification (Manual §15.4)

Section 15.4 of the Manual explicitly lists the exact 9 test function names for the MCP Integration test suite (`test_mcp_*.py`). Every single named test must exist, execute deterministically, and pass cleanly in CI.

| # | Named Test | Target Module / System | Scenario Tested | Key Assertions |
|---|---|---|---|---|
| 1 | `test_calendar_create_event_success` | `app.mcp_clients.calendar.call` | Successful creation of a calendar event via REST API v3. | `status == "success"`, `output["id"]` present, `X-Idempotency-Token` header forwarded, `latency_ms >= 0`. |
| 2 | `test_calendar_list_events_returns_expected_range` | `app.mcp_clients.calendar.call` | Fetching calendar events within specific `timeMin` and `timeMax` range. | `status == "success"`, returned items match mock payload, query params forwarded to `GET /calendars/primary/events`. |
| 3 | `test_calendar_invalid_params_returns_clear_error` | `app.mcp_clients.calendar.call` | Invoking tool with missing mandatory arguments (e.g., `eventId` missing for delete/update) or unknown tool. | `status == "error"`, `output is None`, descriptive error string returned, zero uncaught exceptions. |
| 4 | `test_gmail_draft_email_success` | `app.mcp_clients.gmail.call` | Creating an email draft via Gmail REST API v1. | `status == "success"`, `output["id"]` present, correct draft payload passed, `latency_ms >= 0`. |
| 5 | `test_gmail_send_respects_approval_gate` | `app.agents.nodes.route_step` & risk rules | High-risk tool `gmail.send_message` must route to `approval_gate`, never `execute`. | `route_step(state) == "approval_gate"`. Enforces Manual Acceptance A2 safety boundary. |
| 6 | `test_github_create_issue_success` | `app.mcp_clients.github.call` | Creating a GitHub issue via Copilot MCP server over SSE transport. | `status == "success"`, `output["number"]` present, `output["html_url"]` populated. |
| 7 | `test_github_retry_is_idempotent_no_double_create` | `app.mcp_clients.github.call` | Retrying `github.create_issue` when step is already marked `done` in DB. | Second call makes zero HTTP requests (`httpx.post.assert_not_called()`), returns cached output. |
| 8 | `test_mcp_server_timeout_handled_gracefully` | `app.mcp_clients.*` & `call_tool` | Provider call exceeds timeout (>15s) and raises `httpx.TimeoutException`. | Catches timeout, returns `status == "error"`, `error == "timeout"`, writes `TIMEOUT` event to `execution_logs`. |
| 9 | `test_mcp_server_down_marks_task_failed_not_hung` | `app.agents.nodes.execute` | Outbound MCP service returns HTTP 500/connection error across all retries. | Step status becomes `"failed"`, `tasks.update({"status": "failed"})` executed, graph returns `error: "step_failed"`. |

---

## 4. Per-Test Behavioral Contract & Implementation Details

### Test 1: `test_calendar_create_event_success`
- **Location:** `backend/app/tests/test_mcp_calendar.py`
- **Setup:**
  - Mock `get_valid_google_token` to return a valid access token (`ya29.valid_calendar_token`).
  - Mock `httpx.post` returning HTTP 200 with JSON:
    `{"id": "evt_abc123", "status": "confirmed", "htmlLink": "https://calendar.google.com/event?eid=abc123", "summary": "Project Sync"}`.
- **Execution:**
  ```python
  call(
      tool_name="calendar.create_event_internal_only",
      input_params={
          "summary": "Project Sync",
          "start": {"dateTime": "2026-09-25T10:00:00Z"},
          "end": {"dateTime": "2026-09-25T10:30:00Z"},
      },
      user_id=TEST_USER_ID,
      idempotency_key="plan_999:0",
      task_id=TEST_TASK_ID,
  )
  ```
- **Assertions:**
  - Envelope status is `"success"`.
  - `result["output"]["id"] == "evt_abc123"`.
  - `result["error"] is None`.
  - Sent HTTP headers contain `Authorization: Bearer ya29.valid_calendar_token` and `X-Idempotency-Token: plan_999:0`.
  - `result["latency_ms"] >= 0`.

### Test 2: `test_calendar_list_events_returns_expected_range`
- **Location:** `backend/app/tests/test_mcp_calendar.py`
- **Setup:**
  - Mock `get_valid_google_token`.
  - Mock `httpx.get` returning HTTP 200 with JSON:
    `{"kind": "calendar#events", "items": [{"id": "ev1", "summary": "Standup"}, {"id": "ev2", "summary": "Demo"}]}`.
- **Execution:**
  ```python
  call(
      tool_name="calendar.list_events",
      input_params={
          "timeMin": "2026-09-25T00:00:00Z",
          "timeMax": "2026-09-25T23:59:59Z",
          "maxResults": 10,
      },
      user_id=TEST_USER_ID,
      idempotency_key="plan_999:1",
      task_id=TEST_TASK_ID,
  )
  ```
- **Assertions:**
  - HTTP `GET` called against `https://www.googleapis.com/calendar/v3/calendars/primary/events`.
  - Query parameters contain `timeMin="2026-09-25T00:00:00Z"`, `timeMax="2026-09-25T23:59:59Z"`, and `maxResults=10`.
  - Envelope `result["status"] == "success"`.
  - `len(result["output"]["items"]) == 2`.

### Test 3: `test_calendar_invalid_params_returns_clear_error`
- **Location:** `backend/app/tests/test_mcp_calendar.py`
- **Setup:** Mock `get_valid_google_token`.
- **Execution & Scenarios:**
  - Scenario A: Calling `calendar.delete_event` without `eventId`:
    `call("calendar.delete_event", {}, user_id=TEST_USER_ID, idempotency_key="plan:0")`
    -> Returns `status: "error"`, `error: "missing required param: eventId"`.
  - Scenario B: Calling nonexistent tool:
    `call("calendar.nonexistent_action", {}, user_id=TEST_USER_ID, idempotency_key="plan:0")`
    -> Returns `status: "error"`, `error` mentions unknown tool.
- **Assertions:**
  - No `httpx` HTTP calls are dispatched.
  - Zero uncaught exceptions; error envelope cleanly returned.

### Test 4: `test_gmail_draft_email_success`
- **Location:** `backend/app/tests/test_gmail_mcp.py`
- **Setup:**
  - Mock `get_valid_google_token` for provider `"gmail"`.
  - Mock `httpx.post` against `https://gmail.googleapis.com/gmail/v1/users/me/drafts` returning HTTP 200 with:
    `{"id": "draft_xyz789", "message": {"id": "msg_001", "threadId": "th_001"}}`.
- **Execution:**
  ```python
  call(
      tool_name="gmail.create_draft",
      input_params={"to": ["client@example.com"], "subject": "Draft Subject", "body": "Hello"},
      user_id=TEST_USER_ID,
      idempotency_key="plan_999:2",
      task_id=TEST_TASK_ID,
  )
  ```
- **Assertions:**
  - Envelope status is `"success"`.
  - `result["output"]["id"] == "draft_xyz789"`.
  - Post payload contains base64url-encoded RFC 2822 MIME message.

### Test 5: `test_gmail_send_respects_approval_gate`
- **Location:** `backend/app/tests/test_gmail_mcp.py` & `backend/app/tests/test_mcp_integration.py`
- **Setup:**
  - Construct `AgentState` containing a step with `tool_name="gmail.send_message"`, `mcp_server="gmail"`.
  - Risk rules flag `0: {"risk_tier": "high", "requires_approval": True, "rationale": "Irreversible external email"}`.
- **Execution:** Call `route_step(state)`.
- **Assertions:**
  - Return value is strictly `"approval_gate"`.
  - Never transitions directly to `"execute"`.
  - Guarantees 100% adherence to Acceptance Criteria A2 (zero unapproved high-risk executions).

### Test 6: `test_github_create_issue_success`
- **Location:** `backend/app/tests/test_github_mcp.py`
- **Setup:**
  - Mock Supabase `oauth_connections` query returning encrypted GitHub token.
  - Mock `plan_steps` query returning `status="pending"`.
  - Mock SSE response stream from `https://api.githubcopilot.com/mcp/` yielding JSON-RPC result:
    `{"jsonrpc": "2.0", "result": {"number": 104, "html_url": "https://github.com/org/repo/issues/104"}}`.
- **Execution:**
  ```python
  call(
      tool_name="github.create_issue",
      input_params={"repo": "org/repo", "title": "CI failure", "body": "Stack trace here"},
      user_id=TEST_USER_ID,
      idempotency_key="plan_999:3",
      task_id=TEST_TASK_ID,
  )
  ```
- **Assertions:**
  - Envelope status is `"success"`.
  - `result["output"]["number"] == 104`.
  - `result["output"]["html_url"] == "https://github.com/org/repo/issues/104"`.

### Test 7: `test_github_retry_is_idempotent_no_double_create`
- **Location:** `backend/app/tests/test_github_mcp.py`
- **Setup:**
  - Mock Supabase `plan_steps` query for `idempotency_key="plan_999:3"`.
  - Database row already has: `{"status": "done", "output": {"number": 104, "html_url": "https://github.com/org/repo/issues/104"}}`.
- **Execution:**
  ```python
  call(
      tool_name="github.create_issue",
      input_params={"repo": "org/repo", "title": "CI failure", "body": "Stack trace here"},
      user_id=TEST_USER_ID,
      idempotency_key="plan_999:3",
      task_id=TEST_TASK_ID,
  )
  ```
- **Assertions:**
  - `httpx.post.assert_not_called()` (zero network packets sent to GitHub MCP).
  - Return envelope status is `"success"`.
  - Output matches cached dictionary (`output["number"] == 104`).

### Test 8: `test_mcp_server_timeout_handled_gracefully`
- **Location:** `backend/app/tests/test_mcp_integration.py`
- **Setup:**
  - Mock `httpx.post` / `httpx.get` to raise `httpx.TimeoutException("Read timed out")`.
  - Mock `supabase_admin.table("execution_logs").insert` to capture log calls.
- **Execution:**
  Call `call_tool("calendar.create_event_internal_only", "calendar", {...}, user_id=TEST_USER_ID, idempotency_key="plan:0", task_id=TEST_TASK_ID)`.
- **Assertions:**
  - Function returns envelope without raising exception.
  - `result["status"] == "error"`.
  - `result["error"] == "timeout"`.
  - `execution_logs` received an insert with `event_type="error"` and `payload["error_code"] == "TIMEOUT"`.

### Test 9: `test_mcp_server_down_marks_task_failed_not_hung`
- **Location:** `backend/app/tests/test_mcp_integration.py`
- **Setup:**
  - Mock `call_tool` to simulate a completely dead/unreachable MCP server (e.g. returning `{"status": "error", "error": "502 Bad Gateway", "output": None, "latency_ms": 120}`).
  - Setup an active `AgentState` with a pending task (`task_id="task_fail_1"`, `plan=[{"tool_name": "calendar.create_event_internal_only", "mcp_server": "calendar", "input_params": {}}]`).
  - Mock `supabase_admin.table("tasks").update` and `supabase_admin.table("plan_steps").update`.
- **Execution:** Call `execute(state)`.
- **Assertions:**
  - Retries up to `_MAX_RETRIES` (3 times) with exponential backoff.
  - `supabase_admin.table("plan_steps").update` called with `{"status": "failed", ...}`.
  - `supabase_admin.table("tasks").update` called with `{"status": "failed"}` for `id="task_fail_1"`.
  - Execute returns `{"error": "step_failed", ...}` which terminates LangGraph execution immediately.
  - The task is marked `failed` in the database, proving it never hangs in `running` or `in_progress`.

---

## 5. Extended MCP Coverage (Slack & Provider Edge Cases)

To achieve comprehensive integration coverage beyond the 9 minimal tests, D29 also includes tests for Slack MCP and provider-specific error conditions:

| Extra Test | Target Provider | Assertion / Scenario |
|---|---|---|
| `test_slack_post_message_channel_respects_approval_gate` | Slack MCP | `slack.post_message_channel` is flagged high-risk; `route_step` routes to `approval_gate`. |
| `test_slack_retry_is_idempotent_no_duplicate` | Slack MCP | Existing `done` status in `plan_steps` short-circuits call without sending duplicate message. |
| `test_mcp_401_auth_expired_logs_clean_error` | All MCPs | HTTP 401 returns `status: "error"`, error code `AUTH_EXPIRED`, requiring user reconnection. |
| `test_mcp_403_insufficient_scope_distinct_from_401` | Calendar / Gmail | HTTP 403 returns distinct message `insufficient scope — user must reconnect Google account`. |
| `test_mcp_429_rate_limited_returns_rate_limited_status` | All MCPs | HTTP 429 returns `status: "rate_limited"` envelope, enabling execute node retry loop. |
| `test_call_tool_unknown_mcp_server_returns_error` | Router | Unknown server (e.g. `mcp_server="notion"`) returns error envelope with 0 latency. |

---

## 6. Step 0: Static Analysis & Codebase Pre-Flight Audit

Before authoring new integration tests, verify the following contracts in existing backend code:

1. **`backend/app/mcp_clients/calendar.py`**:
   - Confirm `call()` expects `task_id` parameter (added during execution logs wiring).
   - Confirm `_create_event()` attaches header `X-Idempotency-Token: idempotency_key`.
   - Confirm `_handle_http_error()` maps status 429 -> `_rate_limited(latency_ms)` and 401 -> `AUTH_EXPIRED`.
2. **`backend/app/mcp_clients/gmail.py`**:
   - Confirm `gmail.create_draft` POSTs to `_GMAIL_BASE/drafts` with base64 encoded MIME.
   - Confirm `gmail.send_message` queries `plan_steps` for `idempotency_key` and short-circuits if `status == "done"`.
3. **`backend/app/mcp_clients/github.py`**:
   - Confirm SSE chunk parsing handles `event: endpoint` and `data: {"jsonrpc": ...}`.
   - Confirm token decryption handles empty key in test mocks gracefully.
4. **`backend/app/agents/nodes.py` (`execute`)**:
   - Confirm `_MAX_RETRIES = 3`.
   - Confirm failure handler executes `supabase_admin.table("tasks").update({"status": "failed"}).eq("id", task_id).execute()`.
   - Confirm return payload includes `{"error": "step_failed"}`.

Record findings in `docs/diary/2026-09-25.md`.

---

## 7. Test Suite File Organization & CI Integration

### 7.1 Test Module Layout

All MCP integration tests are placed in `backend/app/tests/` and match the `test_mcp_*.py` pattern required by Section 15.4:

```text
backend/app/tests/
├── test_mcp_calendar.py       # Named Tests 1, 2, 3 (create, list range, invalid params)
├── test_gmail_mcp.py          # Named Tests 4, 5 (create draft, approval gate) + Gmail REST suite
├── test_github_mcp.py         # Named Tests 6, 7 (create issue, retry idempotency) + SSE suite
├── test_slack_mcp.py          # Slack MCP JSON-RPC suite + channel approval test
└── test_mcp_integration.py    # Named Tests 8, 9 (timeout handling, server down marks task failed) + router tests
```

### 7.2 CI Execution & Performance Budget

In GitHub Actions CI (`backend-ci.yml`):
```bash
pytest backend/app/tests/test_mcp_*.py backend/app/tests/test_*_mcp.py -v
```

- **Mock Isolation:** 100% mocked via `unittest.mock.patch`.
- **Secrets:** Zero live API tokens or Supabase service keys required.
- **Speed Budget:** Entire MCP suite executes in `< 6.0 seconds`.
- **Ruff Compliance:** Zero lint or line-length errors (`ruff check . && ruff format --check .`).

---

## 8. Acceptance Criteria & Gate 3 Alignment

| ID | Criterion | Verification in D29 MCP Suite |
|---|---|---|
| **Gate 3** | All test suites running in CI (Sat 26 Sep) | MCP integration test suite running alongside LLM eval, OAuth/JWT, and sign-in/sign-up suites in CI. |
| **A1** | Valid plan execution | Validates that MCP router and clients faithfully execute planned steps and return valid output JSON. |
| **A2** | Approval gate bypass protection (100%) | `test_gmail_send_respects_approval_gate` and `test_slack_post_message_channel_respects_approval_gate` verify high-risk tools never execute unapproved. |
| **A3** | OAuth token refresh & failure handling | Mocks verify that expired Google tokens trigger automatic refresh via `google_token_refresh`, and revoked access surfaces `AUTH_EXPIRED`. |
| **A6** | Latency tracking (<8s p95) | Every MCP envelope returns monotonic `latency_ms` and records it to `execution_logs`. |
| **A9** | CI blocks merge on failing test | Suite is fully automated, strictly typed, deterministic, and enforced on all PRs. |

---

## 9. Definition of Done

- [ ] All 9 named tests from Manual Section 15.4 are implemented and pass cleanly:
  - [ ] `test_calendar_create_event_success`
  - [ ] `test_calendar_list_events_returns_expected_range`
  - [ ] `test_calendar_invalid_params_returns_clear_error`
  - [ ] `test_gmail_draft_email_success`
  - [ ] `test_gmail_send_respects_approval_gate`
  - [ ] `test_github_create_issue_success`
  - [ ] `test_github_retry_is_idempotent_no_double_create`
  - [ ] `test_mcp_server_timeout_handled_gracefully`
  - [ ] `test_mcp_server_down_marks_task_failed_not_hung`
- [ ] Extended tests for Slack MCP and router validation pass cleanly.
- [ ] All tests run 100% offline with zero live network calls and zero credentials in CI.
- [ ] Code formatted with `ruff format` and passes `ruff check`.
- [ ] Day 29 diary entry (`docs/diary/2026-09-25.md`) drafted and committed.
- [ ] Feature branch PR opened and confirmed green in CI for Week 5 PR merge review.
