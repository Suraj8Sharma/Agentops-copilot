# D17 Spec — Approval Gate + Approvals Table

**Project:** AgentOps Copilot
**Day:** D17 (scheduled Fri 11 Sep, running Sat 12 Sep)
**Owner:** Suraj
**Manual reference:** Section 9.2 (approval_gate.py), Section 7 Group B (approvals table), Section 10 (API reference)

---

## 1. Purpose

Build the fail-closed enforcement layer that sits between a planned step and its execution. No high-risk action may run without an explicit, logged, human approval. This is the single most safety-critical subsystem in the project — it is what Acceptance Criterion A2 and the D31 adversarial bypass test will hold to a 100% standard.

## 2. Scope

**In scope for today:**
- `backend/app/risk/approval_gate.py` — the `evaluate()` and `gate()` functions
- `approvals` table + migration
- `POST /approvals/{step_id}` endpoint
- Logging every risk decision to `execution_logs`

**Explicitly out of scope for today** (do not implement, note as follow-up):
- The explanation LLM (Section 9.3) that writes plain-English approval copy — that's Ishani's track, not part of this spec.
- The D31 adversarial bypass test itself — build *toward* it, don't write it today.

**Added to scope:** swapping the LangGraph checkpointer from `MemorySaver` to a Postgres-backed one (Section 6 below). This isn't in the manual's D17 row as written, but it's a correctness dependency of the approval gate, not a nice-to-have — see Section 6 for why.

## 3. `approval_gate.py`

### 3.1 `evaluate(step: PlanStep) -> RiskDecision`

Looks up `risk_rules` by `(step.tool_name, step.mcp_server)`.

- **If a matching row exists:** return a `RiskDecision` carrying that row's `risk_tier`, `requires_approval`, and `rationale`.
- **If no matching row exists:** this is not an error condition to surface — it is the fail-closed default. Return `risk_tier="high"`, `requires_approval=True`, `rationale="no matching risk_rules entry — fail closed"`.
- Before returning, log the decision to `execution_logs` with `event_type="risk_tagged"` and the full rule/decision as `payload`. This write happens before the decision has any downstream effect — not after.

**Non-negotiable:** there is no code path here that calls an LLM or any heuristic. This is a flat table read. An unrecognized action is never treated as safe by omission.

### 3.2 `gate(step: PlanStep, decision: RiskDecision)`

- If `decision.requires_approval` is `False` → call `execute(step)` directly (low/medium risk auto-executes).
- If `decision.requires_approval` is `True` → call `create_approval_request(step, decision)`, which:
  - Writes a row to `approvals` with `decision` left null/pending
  - Halts the LangGraph run at this node (checkpoint saved via the Postgres-backed checkpointer, Section 6)
  - Returns `WAIT_FOR_USER` — the function must not proceed past this point under any circumstance until an external approval decision arrives

**Invariant to preserve:** no code path anywhere in the system may call `execute()` on a step where `requires_approval=True` without first passing through `gate()` and receiving back an explicit `approved` decision recorded in `approvals`. This invariant is what D31 will test adversarially — build with that test already in mind (e.g., don't allow `execute()` to be called directly from `nodes.py` bypassing `gate()`, even as a "fast path" for convenience).

## 4. `approvals` table

Migration file: `backend/migrations/xxxx_create_approvals.sql`

| Column | Type / Constraints | Notes |
|---|---|---|
| id | uuid, PK, DEFAULT gen_random_uuid() | |
| step_id | uuid, FK plan_steps(id) ON DELETE CASCADE | |
| user_id | uuid, FK profiles(user_id) | |
| decision | text, nullable | `approved` \| `rejected`, null while pending |
| explanation_text | text, nullable | Display-only; populated later by Ishani's explainer LLM. Nothing in this spec's logic reads this field to make a decision. |
| decided_at | timestamptz, nullable | |
| response_time_ms | int, nullable | Time from surfaced to decided |
| created_at | timestamptz, DEFAULT now() | Not in the original schema table but needed to compute `response_time_ms` — add it |

**RLS:** `user_id = auth.uid()` for SELECT/UPDATE. INSERT restricted to the backend (service role), since only `create_approval_request()` should create rows — never the client directly.

Index `step_id` — it's the join path back to `plan_steps`.

## 5. `POST /approvals/{step_id}` endpoint

File: `backend/app/api/approvals.py`

**Request body:**
```json
{ "decision": "approved" }
```
or
```json
{ "decision": "rejected" }
```

**Behavior:**
1. Verify JWT (standard dependency, per Section 5.1).
2. Verify the `approvals` row for `step_id` belongs to `auth.uid()` — RLS should already enforce this, but the route should not trust that alone; check ownership explicitly before mutating.
3. Verify the row is currently pending (`decision IS NULL`). If it's already decided, return a clear error rather than silently overwriting — this is itself a small fail-closed choice worth keeping.
4. Update `approvals`: set `decision`, `decided_at = now()`, compute `response_time_ms` from `created_at`.
5. Resume the LangGraph checkpoint for the parent task at the `approval_gate` node:
   - `approved` → routes to `execute(step)` → `log()` → next step / complete
   - `rejected` → routes to `log()` → `skip_step` / `halt_task` (per Section 8.1's node sequence — rejected does not retry or fall through to execute under any circumstance)
6. Log the approval decision itself to `execution_logs` with `event_type="approval_decided"`, before resuming the graph.

**Response:** updated `approvals` row + resulting step status.

## 6. Checkpointer: swap `MemorySaver` → Postgres-backed

### 6.1 Why this belongs in today's work, not later

`MemorySaver` only persists graph state within the running Python process. On Render's free tier, the process spins down after inactivity and cold-starts on the next request. Any task sitting at `approval_gate` (halted, waiting on a human) at the moment of a restart loses its checkpoint silently — no error surfaces, the task just never resumes. This directly breaks the manual's own stated behavior (Section 8.1): "a task that is mid-approval when the app is closed resumes exactly where it left off." Today's approval gate isn't actually done until this is fixed, since the gate is only as durable as its checkpointer.

This also lines up with upstream guidance: `langgraph-checkpoint`'s own docs now explicitly state `MemorySaver` should be used for debugging/testing only, with `PostgresSaver` / `AsyncPostgresSaver` recommended for production.

### 6.2 Implementation

Package: `langgraph-checkpoint-postgres`. Use the async variant, since the FastAPI app is async throughout.

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
    await checkpointer.setup()   # one-time; creates checkpoints,
                                  # checkpoint_writes, checkpoint_blobs tables
    graph = builder.compile(checkpointer=checkpointer)
```

- `setup()` needs to run once (a startup hook or a one-off script is fine — don't call it per-request).
- These tables are managed entirely by the library. They are not part of the 17-table app schema and don't need RLS policies written for them — the checkpointer connects with the backend's own DB credentials, not a client-scoped one.
- Wire this into `backend/app/agents/graph.py`, replacing the current `MemorySaver()` instantiation. `nodes.py` and `approval_gate.py` don't need to change to accommodate this — the checkpointer is transparent to them.

### 6.3 Connection gotcha — do not use Supabase's pooler for this

`AsyncPostgresSaver` has documented compatibility problems with Supabase's connection pooler (Supavisor), in both session and transaction mode — `psycopg.OperationalError` and dropped SSL connections are reported by multiple people hitting this, seemingly related to prepared-statement handling that pgbouncer-style poolers don't support well.

This is directly in tension with Section 2.3's existing free-tier plan, which routes app DB access through Supabase's pooler. **Treat the checkpointer as the one deliberate exception**: point `DB_URI` at Supabase's **direct connection string**, not the pooler URL. Render supports normal outbound DB connections, so this should be viable.

**If the direct connection proves unreliable in practice on Render** (worth a quick live test before committing), the fallback is `langgraph-checkpoint-supabase`, which talks to Supabase over PostgREST instead of a raw `psycopg` connection — it avoids the pooler issue by construction, at the cost of being a smaller, less-established package than the official one. Don't reach for this preemptively; only fall back to it if the direct connection actually fails in your environment.

### 6.4 Env var

Add to `backend/.env.example` and the real `.env`:
```
LANGGRAPH_CHECKPOINTER_DB_URI=
```
Keep this separate from any existing `SUPABASE_URL` / pooler-based connection string your app code already uses for regular queries — don't reuse the pooled one here (see 6.3).

## 7. Logging requirements (applies to all files above, including the checkpointer swap)

Every write to `execution_logs` must happen *before* the event it describes has an external effect — not reconstructed afterward. Concretely today:

- `evaluate()` logs `risk_tagged` before returning the decision to the caller.
- `create_approval_request()` logs `approval_requested` before halting the graph.
- The `/approvals/{step_id}` endpoint logs `approval_decided` before resuming the graph.

## 8. Test coverage to write alongside this (not the full D31 suite, just the unit-level ones for this task)

From Section 15.4's named list — these two files, these specific tests:

`test_approval_gate.py`:
- `test_low_risk_action_auto_executes_without_approval`
- `test_high_risk_action_blocks_pending_approval`
- `test_rejected_approval_halts_task_with_no_side_effects`
- A no-matching-rule case: assert fail-closed default (`risk_tier="high"`, `requires_approval=True`) — this isn't in the named list but should exist given how central it is to Section 9.2.

`test_mcp_*.py` (one relevant case):
- `test_gmail_send_respects_approval_gate` — confirms `gmail.send_message` specifically routes through the gate, since that's your highest-stakes real action right now.

Add one more, given today's checkpointer change:
- `test_task_resumes_after_app_closed_mid_approval` (from Section 15.4's Agent-Loop suite) — this is the direct test that the Postgres swap was for. Worth pulling forward from wherever it's currently scheduled, since without it you have no actual proof the swap worked — restart the process mid-approval in the test and confirm the checkpoint survives and resumes correctly.

## 9. Environment notes

Dev environment is Windows/PowerShell. If the coding agent generates manual test commands (e.g. curl for the new endpoint), use `curl.exe` explicitly and keep commands single-line — no bash-style `\` line continuation.

## 10. Follow-up items (not today, noted so they don't get lost)

- D31: the actual adversarial bypass test suite exercising this code from every angle (direct API calls, replayed requests, malformed plan JSON, missing risk_rules rows).
- If the direct Postgres connection for the checkpointer turns out to be unreliable from Render in practice, revisit with `langgraph-checkpoint-supabase` (PostgREST-based) as documented in Section 6.3.