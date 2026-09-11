# AgentOps Copilot — Spec: Slack MCP Client

**Day:** D17 (schedule shifted — see note below) | **Date:** Fri 11 Sep 2026
**Owner:** Suraj | **Component:** `backend/app/mcp_clients/slack.py`
**Status:** Rev. 1

---

## 0. Schedule Note

This work was not originally assigned a day in Section 14 of the manual — Calendar (D14), Gmail (D15), and GitHub (D16) each got an explicit MCP-client build day, but Slack did not, despite being fully specified in Section 8.3 and bundled into Appendix D's client list. To close that gap without disturbing later weeks, this week's plan is locally resequenced:

| Date | Was | Now |
|---|---|---|
| Fri 11 Sep | Approval-gate logic + approvals table/endpoint | **Slack MCP client (this spec)** |
| Sat 12 Sep | LLM router + Week-3 PR merge/freeze | Approval-gate logic + approvals table/endpoint |
| Sun 13 Sep | Rest day (buffer) | LLM router + Week-3 PR merge — orchestration core frozen |
| Mon 14 Sep | — | Unchanged, back on original schedule |

D19 onward is untouched. This spec covers **only** the Slack client — approval-gate logic and the LLM router are explicitly out of scope here (they're tomorrow's and Sunday's work respectively).

---

## 1. Objective

Build `slack.py` implementing the four Slack tools against the official Slack-hosted MCP server, following the identical client envelope already established by `calendar.py`, `gmail.py`, and `github.py`, so the planner and risk gate require zero Slack-specific branching.

## 2. Dependencies (confirmed met)

- D10 — Slack OAuth app registered, token flow extended (`oauth_connections` has Slack rows)
- D12 — `risk_rules` seeded (see Section 6 flag below — partially met)
- Section 8.2 — MCP client envelope contract already implemented in 3 prior clients

## 3. Integration Architecture

- **Endpoint:** Official Slack-hosted MCP server, `https://mcp.slack.com/mcp` — generally available, production-grade (per Section 8.3, no Developer Preview caveats unlike Calendar/Gmail).
- **Auth:** Per-user Slack OAuth token (bot token, workspace-scoped) fetched from `oauth_connections` where `provider = 'slack'`, sent as `Authorization: Bearer <user_token>` on every call — same per-user pattern as the other three clients (Section 8.2, step 1–2).
- **No split integration.** Unlike Gmail (MCP for read/draft, Resend for send), all four Slack tools route through the single official MCP endpoint. No secondary vendor involved.

### 3.1 Token Fetch & Fernet Decryption

`_fetch_slack_token(user_id)` follows the identical pattern used by `calendar.py`, `gmail.py`, and `github.py`:

1. Query `oauth_connections` for `user_id` + `provider = 'slack'` → get `access_token`.
2. Attempt Fernet decryption using `settings.ENCRYPTION_KEY`:
   ```python
   fernet = Fernet(settings.ENCRYPTION_KEY.encode())
   token = fernet.decrypt(encrypted_token.encode()).decode()
   ```
3. If decryption fails (e.g. dev/test environment where tokens are stored unencrypted), **fall back to the raw token value** with a debug-level log — same fallback used by all three existing clients.
4. If no row found or the query itself fails, return `None` → caller returns an `error` envelope.

This is not optional. The `oauth.py` callback (D10) Fernet-encrypts tokens before writing to `oauth_connections`. Reading them back without decryption would send ciphertext as a Bearer token, which would always 401.

### 3.2 MCP Transport

Slack's official MCP server at `https://mcp.slack.com/mcp` uses **plain JSON-RPC over HTTP** (same transport as Calendar and Gmail), not the Streamable HTTP / SSE transport used by GitHub. This means:

- Standard `httpx.post()` with `Content-Type: application/json`
- Response parsed via `response.json()` (no SSE `data:` line extraction)
- No `mcp-session-id` lifecycle — no initialize handshake, no session caching
- No `notifications/initialized` step

**Verify at implementation time:** If the live endpoint returns `text/event-stream` or requires an `initialize` handshake, adopt the SSE parsing + session management pattern from `github.py` instead.

## 4. Tool Inventory & Risk Tiers

Per Section 8.3 and Appendix E:

| Tool | Purpose | Risk tier | Approval required |
|---|---|---|---|
| `slack.list_channels` | Read available channels | low | No |
| `slack.post_message_dm` | Post a direct message | medium | No |
| `slack.post_message_channel` | Post to a public/shared channel | high | Yes |
| `slack.add_reaction` | React to an existing message | low | No |

**Action-type derivation:** `slack.post_message` arrives from the planner as a single base tool name; per Section 9.2's fourth bullet, the risk-tag node — not this client — is responsible for computing whether a given call is `slack.post_message_dm` or `slack.post_message_channel` from the `input_params.channel` field (DM vs. channel target) before the `risk_rules` lookup happens. This client's job is only to accept whichever fully-resolved tool name it's given and call the right MCP method; it does not do risk classification itself.

### 4.1 Tool Name Mapping

The client needs a `_TOOL_NAME_MAP` that maps internal AgentOps tool names to the actual tool names exposed by Slack's MCP server:

```python
_TOOL_NAME_MAP: dict[str, str] = {
    "slack.list_channels":        "list_channels",
    "slack.post_message_dm":      "post_message",      # same MCP tool, risk-tag already split
    "slack.post_message_channel": "post_message",      # same MCP tool, risk-tag already split
    "slack.add_reaction":         "add_reaction",
}
```

**Verify at implementation time:** Confirm exact tool names against the live Slack MCP server's `tools/list` response. If `post_message_dm` and `post_message_channel` are separate server-side tools, update the map accordingly.

## 5. Client Envelope Compliance

`slack.py` implements the standard envelope (Section 8.2 table) with no Slack-specific fields:

- **Request:** `tool_name`, `mcp_server: "slack"`, `input_params`, `idempotency_key` (`plan_id:step_index`)
- **Response:** `status` (`success | error | rate_limited`), `output`, `error` (typed code + message), `latency_ms`

### 5.1 Error Code Taxonomy

Matching the structured `{"code": "...", "message": "..."}` shape used by `github.py`:

| Code | Trigger | Notes |
|---|---|---|
| `AUTH_EXPIRED` | HTTP 401 | Token revoked or workspace uninstalled — no retry |
| `RATE_LIMITED` | HTTP 429 | Return `status: "rate_limited"` |
| `TIMEOUT` | `httpx.TimeoutException` | No response within `_TIMEOUT` budget |
| `INVALID_PARAMS` | JSON-RPC error code `-32602` | Bad `input_params` from planner |
| `PROVIDER_ERROR` | Any other non-2xx or MCP RPC error | Catchall for Slack-side failures |

### 5.2 Execution Logging

Every call logs to `execution_logs` with `agent_name = "mcp_slack"` before and after the call, per Section 4.2's auditability-by-construction principle.

**Current state:** The `execution_logs` table exists (migration `20260909000009`), but the insert helper is not yet wired — same open dependency as Calendar, Gmail, and GitHub clients. Implementation should include a `_log_execution()` stub with a `TODO(D22)` comment, identical to the pattern in `github.py`.

### 5.3 Router Registration

`mcp_clients/__init__.py` must be updated to include the Slack client:

```python
from app.mcp_clients import calendar, github, gmail, slack

_ROUTER = {
    "calendar": calendar,
    "gmail": gmail,
    "github": github,
    "slack": slack,       # ← add this
}
```

Without this, the execute node cannot route `mcp_server="slack"` steps to the client.

## 6. Open Items to Verify Before/During Implementation

These are gaps in the manual's Slack coverage, not assumptions to silently paper over:

1. **`risk_rules` coverage gap.** Section 9.1's seed table explicitly lists `slack.post_message_dm` and `slack.post_message_channel`, but **not** `slack.list_channels` or `slack.add_reaction`. If those two rows were never seeded in D12, the fail-closed default (Section 9.2) will tag them `high` / `requires_approval = true` — which contradicts Section 8.3's explicit `low` / `No` assignment for both. **Action:** check the D12 migration for these two rows before relying on the risk tags in Section 8.3's table; if missing, they need a follow-up migration (reviewed like code, per Section 9.2's third bullet) — not a runtime patch.
2. **OAuth scope gap.** Section 5.2 lists only `chat:write` and `channels:read` as the requested Slack scopes. `slack.add_reaction` needs a `reactions:write`-equivalent scope that isn't in that list. **Action:** confirm current scope grant in `oauth.py` (D10) covers reaction-adding; if not, this is a companion change to `oauth.py`, same pattern as the `gmail.send` scope addition flagged in the D15 spec.
3. **Idempotency support unconfirmed.** Unlike Gmail (explicitly documented in the D15 spec as having no idempotency-key header support on its REST API), the manual doesn't state whether Slack's official MCP server accepts or ignores the `idempotency_key` field from the standard envelope. Given the "official MCP server landscape changed rapidly in 2026 — cached knowledge is likely outdated" principle, verify against Slack's current MCP server docs rather than assuming either way. If unsupported, apply the same application-level precheck pattern used for Gmail (status check against `plan_steps` before the HTTP call) as a fallback.

## 7. Explicitly Out of Scope for This Spec

- Approval-gate logic / `approvals` table — moved to Sat 12 Sep
- LLM router (Groq/Gemini) — moved to Sun 13 Sep
- Risk-tag node's DM-vs-channel classification logic itself (only this client's consumption of its output is in scope)
- Any change to `risk_rules` beyond flagging the potential gap in Section 6 above — actual migration is a separate, reviewed change

## 8. Exit Criteria for Today

- [ ] `slack.py` implements all four tools against `https://mcp.slack.com/mcp`
- [ ] `_fetch_slack_token()` decrypts via Fernet with raw-token fallback (§3.1)
- [ ] Per-user token fetch from `oauth_connections` (provider = `slack`) working
- [ ] Standard envelope in/out on all four tools, matching Calendar/Gmail/GitHub clients
- [ ] Error codes follow the taxonomy in §5.1 (AUTH_EXPIRED, RATE_LIMITED, TIMEOUT, INVALID_PARAMS, PROVIDER_ERROR)
- [ ] `_log_execution()` stub with TODO(D22) present (§5.2)
- [ ] `mcp_clients/__init__.py` updated — `"slack": slack` added to `_ROUTER` (§5.3)
- [ ] MCP transport confirmed as plain HTTP or SSE; implementation matches (§3.2)
- [ ] `_TOOL_NAME_MAP` verified against live `tools/list` response (§4.1)
- [ ] `execution_logs` rows written for every call (or stub in place)
- [ ] Risk_rules coverage for `list_channels` / `add_reaction` confirmed or follow-up migration filed
- [ ] OAuth scope for `add_reaction` confirmed or companion change to `oauth.py` filed
- [ ] Idempotency behavior of Slack's MCP server confirmed or fallback precheck implemented