# AgentOps Copilot — Build Spec: D16 GitHub MCP Client

**Day:** D16 (Thu 10 Sep) · **Owner:** Suraj · **File to create:** `backend/app/mcp_clients/github_client.py`
**Manual task:** "MCP client — GitHub (create issue/comment)"

This spec is self-contained. It does not assume `calendar_client.py` (D14) or
`gmail_client.py` (D15) already exist — if they do, align naming/shape with them;
if not, this spec follows the same shared-envelope pattern they should also use,
per Section 8.2's "identical envelope" design principle.

**This spec is grounded in real, already-validated behavior** — not projected.
Today's testing confirmed the exact transport shape against the live endpoint,
first with a PAT, then with a token decrypted from `oauth_connections` via the
Fernet utility. Both authenticated identically.

---

## 1. Scope

Build one client module, `github_client.py`, exposing a single public entry point
the LangGraph `execute` node calls for every GitHub-related `plan_step`. Unlike
Gmail (split MCP/Resend), **every GitHub tool routes through one endpoint** — no
backend branching needed.

| Tool | Purpose | Risk tier (Section 9.1 / 8.3) | Approval |
|---|---|---|---|
| `github.list_issues` | Read open issues for context | low | No |
| `github.create_issue` | File a new issue | medium | No |
| `github.comment_on_issue` | Add a comment to an existing issue | medium | No |
| `github.create_pr_comment` | Comment on a pull request | medium | No |

Notable difference from Calendar/Gmail: **no GitHub tool in this MVP defaults to
requires_approval = true.** Everything here auto-executes once the risk_tag node
clears it — there's no GitHub equivalent of `gmail.send_message`'s always-approve
rule. Scoped deliberately to issue-level interactions only — no PR merges, no repo
administration (Section 8.3).

**Out of scope for this file** (built on other days — don't duplicate):
- Risk-tier lookup / approval gating logic → `risk_rules.py` + `approval_gate.py` (D17)
- LangGraph node wiring → `nodes.py`
- `execution_logs` writes as a system → see §6, same open dependency as D14/D15

---

## 2. Shared MCP Envelope (Section 8.2)

✅ **DONE** — Implemented in `github.py` matching the same `call()` entry point
pattern used by `calendar.py` and `gmail.py`. Returns the standard
`{ status, output, error, latency_ms }` envelope. Error field uses the structured
`{ code, message }` shape per §7.

---

## 3. Auth: Token Retrieval & Decryption

✅ **DONE** — `_fetch_github_token()` looks up `provider='github'` in
`oauth_connections`, then Fernet-decrypts the `access_token` using
`settings.ENCRYPTION_KEY`. Falls back to raw token if decryption fails (dev/test).
401 returns `AUTH_EXPIRED` with no retry.

**Open item to confirm:** Section 5.2 describes the granted scope only as
"repo-scoped ... issue/comment creation only, not full repo admin" without naming
the literal OAuth scope string. Confirm which scope(s) were actually requested when
the GitHub OAuth app was registered on D10, and note it here once known — matters
if `create_pr_comment` ever needs a broader scope than issue comments do.

---

## 4. GitHub MCP Transport — Confirmed Today

✅ **DONE** — Full MCP session lifecycle implemented:
- Initialize handshake with SSE response parsing
- `mcp-session-id` captured and sent on subsequent requests
- `notifications/initialized` sent after initialize
- Session cached per user, re-initialized on 404/410 rejection
- SSE `data:` line parsing (not raw `.json()`)

### 4.1 Session reuse

✅ **DONE** — `_session_cache` dict keyed by `user_id`. `_invalidate_session()`
clears on rejection/401.

---

## 5. Idempotency (`test_github_retry_is_idempotent_no_double_create`)

✅ **DONE** — `_already_done()` checks `plan_steps.status` before
`github.create_issue`. If `status='done'` with output, returns cached result
without calling MCP.

---

## 6. Logging to `execution_logs` — Same Open Dependency

✅ **DONE (stub)** — `_log_execution()` stubs to `logger.debug()`. The
`execution_logs` table exists (migration `20260909000009`), but the insert helper
isn't wired yet. TODO(D22) comment in place.

> **Note:** The migration was pulled forward and already exists — the real insert
> can be wired when the service-role insert helper is built.

---

## 7. Error Taxonomy

✅ **DONE** — All error codes implemented via `_make_error()`:

| Code | Meaning |
|---|---|
| `AUTH_EXPIRED` | Token revoked (401) — no retry loop |
| `RATE_LIMITED` | 429 from GitHub MCP |
| `TIMEOUT` | No response within budget |
| `SESSION_EXPIRED` | Cached `Mcp-Session-Id` rejected — retry once with fresh session |
| `INVALID_PARAMS` | Malformed `input_params` or JSON-RPC -32602 |
| `PROVIDER_ERROR` | Any other non-2xx from GitHub |

---

## 8. Manual Smoke Test — Next Steps From Today

Steps 1–2 below are **already done** (today's session). Pick up at step 3:

1. ~~Decrypt a real `github` token from `oauth_connections`.~~ ✅
2. ~~`initialize` against `https://api.githubcopilot.com/mcp/`, confirm `200 OK`,
   SSE body, `mcp-session-id` header.~~ ✅ (done twice — PAT and real OAuth token,
   identical result)
3. Send `notifications/initialized` on that session — confirm no error.
4. Send `tools/list` on that session — capture the real tool names/schemas, compare
   against the `github.*` names assumed in Section 9.1's `risk_rules` seed data.
5. Try `github.create_issue` end to end against a real (test/scratch) repo your
   OAuth app has access to.
6. Try `github.comment_on_issue` against the issue just created.

Steps 3–6 use the same request.json + curl.exe pattern from today — just change the
`method`/`params` in the JSON body and keep reusing the session ID from step 2's
response header.

---

## 9. Acceptance Check for This Spec

Structurally complete when:

- [x] Single `call_tool(request, user_id)` entry point, no backend branching needed
- [x] Fernet decryption used for token retrieval
- [x] SSE response parsing, not raw `.json()`
- [x] Session ID captured and reused across calls in a task; re-init on rejection
- [x] `notifications/initialized` sent after `initialize`
- [x] `401` → `AUTH_EXPIRED`, no retry loop
- [x] Idempotency check against `plan_steps.status` before `create_issue`
- [x] `execution_logs` calls present but stubbed safely if the table doesn't exist yet
- [x] Error codes match §7 taxonomy

Supports these named tests from Section 15.4 once the MCP integration suite is
built (D29) — not required today, but the interface should be clean for them:
`test_github_create_issue_success`, `test_github_retry_is_idempotent_no_double_create`.