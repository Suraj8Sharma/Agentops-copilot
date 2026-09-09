# Gmail MCP Client — Technical Spec (D15) — Rev. 2

**Project:** AgentOps Copilot
**Plan reference:** D15 — "MCP client — Gmail (draft/send, read)" (Section 14)
**Owner / track:** Suraj — backend
**Branch:** `feature/d15-gmail-mcp-client`
**Files (new / modified):**
- `backend/app/mcp_clients/gmail.py` (new — Gmail MCP client: list/read/draft via Gmail MCP; send via the Gmail REST API, using the user's own OAuth token)
- `backend/app/mcp_clients/__init__.py` (modify — register `"gmail"` in `_ROUTER`)
- `backend/app/api/oauth.py` (modify — add `gmail.send` to the Google OAuth consent scope list; see Section 0.1)

**Status going into this spec:** D14 complete — Google Calendar MCP client ships and is registered in `_ROUTER`. The `execute` node in `nodes.py` routes all MCP calls through `call_tool()`. `execution_logs`, `plan_steps`, `oauth_connections` tables are live.

---

## 0. Revision history

**Rev. 1** used Resend as the send path, since the Gmail MCP server has no send tool. Correct as far as it went, but it meant every email came from a shared `RESEND_FROM_ADDRESS`, not the user's own account.

**Rev. 2 (this version)** replaces Resend entirely. `gmail.send_message` now sends through the **Gmail REST API** (`gmail.googleapis.com`, not the MCP server) using the user's own Google OAuth token, so the email is genuinely sent from and by the user's account. Two things fall out of that:

- Reply-To is no longer a concern — replies land in the user's own inbox naturally, since the user's own account sent the message. (This resolves the Reply-To gap flagged in the prior conversation.)
- **No new third-party dependency, no new env vars.** Resend's `RESEND_API_KEY` / `RESEND_FROM_ADDRESS` are gone; the send path reuses the exact same `oauth_connections` token lookup the MCP read/draft path already uses.

### 0.1 Companion change required — OAuth scope bump

`gmail.send` must be added to the scope list requested in `oauth.py`'s Google consent flow. This is a real change to the OAuth layer frozen at D12, not a D15-internal detail — call it out in the D15 PR description explicitly rather than letting it slide in quietly.

Consequence: **any user who connected Google before this change does not have `gmail.send` on their stored token.** Their first send attempt will get a `403` from Gmail (insufficient scope), which this spec surfaces as a clean, typed re-auth error (Section 7) rather than a generic failure — but they do need to reconnect once. No migration needed for already-stored tokens; this is a reconnect flow, not a data fix.

`gmail.send` is a Google *restricted* scope. Your OAuth consent screen is presumably still in Testing publishing status (consistent with the 7-day Testing-mode expiry handling already built at D9) — that's fine for the team + a handful of test accounts, but is the thing that would need a Google verification pass (CASA assessment) before this could ever go out to the public. Not a D15 concern, just worth having on your radar before demo day if the test-user list grows.

---

## 1. Objective

Build the **Gmail MCP client** (`gmail.py`) behind the identical call/response contract established in D14 (`calendar.py`). Wire it into the execute node's router with one line in `__init__.py`.

Gmail is split across two integrations, **both using the same per-user Google OAuth token** — there is no longer a separate credential for sending:
- **Gmail MCP server** (`https://gmailmcp.googleapis.com/mcp/v1`) — handles reading and drafting. The server has no send tool at all in Developer Preview; drafting is as far as it goes.
- **Gmail REST API** (`https://gmail.googleapis.com/gmail/v1/users/me/messages/send`) — handles `send_message`, authenticated as the user, sending from the user's own address. This is a separate REST surface from the MCP server, not a workaround of it.

**Explicitly not built today:**
- GitHub MCP client (D16)
- Slack MCP client (D16)
- Approval gate wiring (D17) — `gmail.send_message` is already flagged `requires_approval = true` in `risk_rules`; the execute node already halts for it. The client just needs to be reachable when approval is eventually granted.

---

## 2. Tool Inventory

| Tool (internal action_type) | Real endpoint | Auth | Risk tier | Approval default |
|---|---|---|---|---|
| `gmail.list_messages` | Gmail MCP `search_threads` | user's Google token | low | No |
| `gmail.get_message` | Gmail MCP `get_message` | user's Google token | low | No |
| `gmail.create_draft` | Gmail MCP `create_draft` | user's Google token | low | No |
| `gmail.send_message` | Gmail REST API `users.messages.send` | user's Google token | high | Yes — always |

All four rows now authenticate the same way: the user's own OAuth token from `oauth_connections`. `gmail.send_message` is the only one requiring the added `gmail.send` scope (Section 0.1).

---

## 3. MCP Client Contract

`gmail.py` implements the **identical envelope** as `calendar.py` (Section 8.2):

```python
def call(
    tool_name: str,
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """
    Returns:
        {
            "status":     "success" | "error" | "rate_limited",
            "output":     dict | None,
            "error":      str | None,
            "latency_ms": int,
        }
    """
```

`idempotency_key` is still `plan_id:step_index`. Unlike Resend, the Gmail REST API has **no concept of an idempotency key** — see Section 4.5 for how duplicate-send protection is actually enforced now.

---

## 4. Implementation Detail

### 4.1 Internal tool-name map

```python
GMAIL_MCP_URL  = "https://gmailmcp.googleapis.com/mcp/v1"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# Tools routed to the Gmail MCP server.
# `list_messages` is not a real tool on this server — closest equivalent
# for "read recent messages for context" is `search_threads`.
_MCP_TOOL_MAP: dict[str, str] = {
    "gmail.list_messages": "search_threads",
    "gmail.get_message":   "get_message",
    "gmail.create_draft":  "create_draft",
}

# Routed to the Gmail REST API's own send endpoint — not the MCP server,
# not a third party. Uses the same user token as the MCP path above.
_SEND_TOOLS = {"gmail.send_message"}
```

### 4.2 Token fetch

Single shared helper, used by **both** the MCP path and the send path now (previously the send path used a static `RESEND_API_KEY` instead):

```python
def _fetch_google_token(user_id: str) -> str | None:
    """Read user's Google OAuth access_token from oauth_connections (provider='google')."""
```

No separate credential exists for sending anymore. If the stored token lacks `gmail.send` (an old-scope token from before Section 0.1's change), Gmail's API itself will reject the call with `403` — see Section 7.

### 4.3 `call()` routing logic

```
if tool_name in _SEND_TOOLS:
    → _call_gmail_send(input_params, user_id, idempotency_key)
elif tool_name in _MCP_TOOL_MAP:
    → _call_gmail_mcp(tool_name, input_params, user_id, idempotency_key)
else:
    → error envelope: "unknown tool: {tool_name}"
```

### 4.4 `_call_gmail_mcp()` — Gmail MCP path (unchanged from Rev. 1)

Follows the same 6-step structure as `calendar.call()`:
1. Resolve real MCP tool name from `_MCP_TOOL_MAP` (e.g. `gmail.list_messages` → `search_threads`).
2. Fetch user Google token via `_fetch_google_token`.
3. Build MCP JSON-RPC payload (`jsonrpc: "2.0"`, `method: "tools/call"`).
4. POST to `GMAIL_MCP_URL` with `Authorization: Bearer <token>` and `X-Idempotency-Key`.
5. Handle HTTP errors: 429 → `"rate_limited"`, 401 → `"error"` (token expired), other non-2xx → `"error"`.
6. Parse JSON-RPC response; return `"success"` envelope on `result`, `"error"` envelope on `error` field.

Timeout: `15.0s`.

### 4.5 `_call_gmail_send()` — send path (replaces `_call_resend`)

```python
def _call_gmail_send(
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
```

**Step 0 — idempotency precheck (new, replaces the header-based dedup Resend used to provide):**

Gmail's send endpoint does not honor an idempotency-key header, so a retried call after a timeout could genuinely send a second real email from the user's account. Guard against this at the application level, before making any HTTP call:

```python
def _already_sent(plan_id: str, step_index: int) -> dict | None:
    """Check plan_steps for a prior successful run of this exact step.
    Returns the cached output if it already completed, else None.
    """
    result = (
        supabase.table("plan_steps")
        .select("status, output")
        .eq("plan_id", plan_id)
        .eq("step_index", step_index)
        .single()
        .execute()
    )
    if result.data and result.data["status"] == "done" and result.data.get("output"):
        return result.data["output"]
    return None
```

`idempotency_key` is parsed into `(plan_id, step_index)` at the top of `_call_gmail_send`. If `_already_sent` returns a cached output, `_call_gmail_send` returns a `"success"` envelope built from that cached output immediately — no HTTP call, no duplicate send.

**Steps 1–5 — the actual send, only reached if not already sent:**

1. Fetch user's Google token via `_fetch_google_token`.
2. Build a standard RFC 2822 MIME message from `input_params` (`to`, `subject`, `body`) — no `From` header is set; Gmail fills it in as the authenticated account automatically.
3. Base64url-encode the raw MIME bytes.
4. `POST` to `GMAIL_SEND_URL` with `Authorization: Bearer <token>`, body `{"raw": "<encoded>"}`.
5. Handle the response:
   - `200` → `"success"`, output `{"id": <gmail message id>, "threadId": <thread id>}`.
   - `401` → `"error"`, "unauthorized — token expired or revoked."
   - `403` → `"error"`, **"insufficient scope — user must reconnect Google with mail-send permission"** (distinct message from 401 — this is the expected error for Section 0.1's old-scope tokens, not a broken connection).
   - `429` → `"rate_limited"`.
   - Other non-2xx → `"error"` with the response body's message.

Timeout: `15.0s`, matching the other clients.

### 4.6 `__init__.py` — one-line change (unchanged from Rev. 1)

```python
from app.mcp_clients import calendar, gmail   # add gmail

_ROUTER = {
    "calendar": calendar,
    "gmail":    gmail,              # add this line
}
```

No changes to the execute node, `call_tool()` signature, or any other file.

---

## 5. Config / Env

**No new environment variables.** Resend's `RESEND_API_KEY` and `RESEND_FROM_ADDRESS` are removed entirely — the send path reuses `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` (already present, used to read `oauth_connections` and now also `plan_steps` for the idempotency precheck).

---

## 6. Security Notes

- Google OAuth token fetched server-side from `oauth_connections`; never logged in plaintext.
- Email content and the send action now happen entirely within Google's infrastructure under the user's own account — no email body or recipient ever passes through a third-party vendor (Resend is gone). This is a net privacy improvement over Rev. 1.
- `gmail.send_message` is `requires_approval = true` in `risk_rules`, unchanged. The execute node halts before reaching the Gmail client for this tool; the send path is only reachable after an explicit `approved` row exists in `approvals` (enforced in D17). Widening the scope to `gmail.send` does not weaken this — the approval gate sits in front of the client regardless of which credential the client eventually uses.
- Because a duplicate here would be a real email sent from the user's real account (not a shared `noreply@` address), the idempotency precheck in Section 4.5 is treated as required, not a nice-to-have — this is exactly the kind of user-facing, hard-to-undo mistake the fail-closed philosophy in Section 9 is meant to prevent.

---

## 7. Error Handling

| Condition | Behavior |
|---|---|
| No Google token in `oauth_connections` | `status: "error"`, message: re-auth required |
| Step already has a successful `done` result for this `plan_id`/`step_index` | Short-circuit to cached `"success"` output — no HTTP call made |
| Gmail MCP 401 | `status: "error"`, message: token expired/revoked |
| Gmail MCP 429 | `status: "rate_limited"` — execute node retries with exponential backoff (up to 3×) |
| Gmail MCP timeout (>15s) | `status: "error"`, message: timeout |
| Gmail MCP non-JSON response | `status: "error"`, message: invalid JSON from MCP server |
| Gmail send 401 | `status: "error"`, message: token expired/revoked |
| Gmail send 403 | `status: "error"`, message: insufficient scope — reconnect required (distinct from 401) |
| Gmail send 429 | `status: "rate_limited"` |
| Gmail send timeout (>15s) | `status: "error"`, message: timeout |
| Unknown `tool_name` | `status: "error"`, message: `"unknown tool: {tool_name}"` |

---

## 8. Out of Scope for D15

- GitHub MCP client — **D16**
- Slack MCP client — **D16**
- Approval gate (`POST /approvals/{step_id}`, graph resume) — **D17**
- `gmail.send_message` executing end-to-end through an approved flow — requires D17's gate wired; D15 only ensures the client is correct when approval arrives
- OAuth reconnect **UI** prompt in the app for users on an old-scope token — Ishani/Jigyasu's track. D15's backend just needs to surface the 403 cleanly (Section 7); the app-side "please reconnect Google" screen is separate work.
- Google OAuth verification / moving out of Testing publishing status — not needed for the capstone's scale, flagged in Section 0.1 only as a forward-looking note.

---

## 9. Acceptance / Test Criteria

- `test_gmail_client_routes_send_to_gmail_api`: `gmail.call("gmail.send_message", ...)` calls `GMAIL_SEND_URL`, not the Gmail MCP server and not any third-party endpoint.
- `test_gmail_client_routes_read_to_mcp`: `gmail.call("gmail.list_messages", ...)` invokes the Gmail MCP server path.
- `test_gmail_list_messages_maps_to_search_threads`: the MCP JSON-RPC payload for `gmail.list_messages` uses `"name": "search_threads"`, not `"list_messages"`.
- `test_gmail_send_uses_recipient_own_token`: `_call_gmail_send` fetches and uses the token from `oauth_connections` for `user_id`, not any static app-level credential.
- `test_gmail_send_skips_duplicate_call_if_step_already_done`: if `plan_steps` already shows `status="done"` with an `output` for this `plan_id`/`step_index`, no HTTP call is made and the cached output is returned.
- `test_gmail_send_403_insufficient_scope_returns_clear_reauth_error`: a `403` from `GMAIL_SEND_URL` returns `{ status: "error", error: "insufficient scope — user must reconnect Google with mail-send permission" }`, distinguishable from the 401 case.
- `test_gmail_draft_email_success`: `gmail.create_draft` with valid `input_params` returns `{ status: "success", output: {...}, latency_ms: <int> }`.
- `test_gmail_send_respects_approval_gate`: The execute node does **not** call `gmail.call("gmail.send_message", ...)` unless a valid `approved` row exists. (Regression guard.)
- `test_gmail_mcp_token_missing_returns_error`: No Google token in `oauth_connections` → `{ status: "error" }`, no HTTP call made.
- `test_gmail_mcp_401_returns_error`: 401 from Gmail MCP → `{ status: "error", error: "unauthorized — token expired or revoked" }`.
- `test_gmail_mcp_429_returns_rate_limited`: 429 from Gmail MCP → `{ status: "rate_limited" }`.
- `test_gmail_unknown_tool_returns_error`: `gmail.call("gmail.nonexistent", ...)` → `{ status: "error", error: "unknown tool: gmail.nonexistent" }`.
- `test_call_tool_routes_gmail_server`: `call_tool(mcp_server="gmail", ...)` resolves to `gmail.call()` via `_ROUTER`.

---

## 10. Dependencies

- **D14 complete** — `execute` node + Calendar MCP client pattern established; `_ROUTER` in `__init__.py` exists.
- **D12 complete** — `risk_rules` table seeded with `gmail.*` rows (`gmail.send_message` = high/true, `gmail.create_draft` = low/false).
- **D8 complete** — `oauth_connections` table + Google OAuth token stored (provider `'google'`).
- **`oauth.py` scope update (Section 0.1)** — `gmail.send` must be added to the Google consent scope list before send will work for any user, including freshly-connecting ones. Already-connected users need to reconnect once.
- **`execution_logs` migration** — `20260909000009_create_execution_logs.sql` pulled forward from D22 and run today (D13/D14/D15 all write to this table). Must be applied before any agent-loop test runs.
- **No new env vars, no new Python packages** — `httpx` already installed; MIME construction uses the Python standard library (`email.mime.text`) plus `base64`.