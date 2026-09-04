# risk_rules Table, Seed Data & risk_rules.py — Technical Spec

**Project:** AgentOps Copilot
**Plan reference:** D12 — "risk_rules table seeded; Week-2 PR merge — auth + OAuth layer frozen v1"
**Owner / track:** Suraj — backend
**Branch:** `feature/risk-rules`
**Files:**
- `backend/migrations/20260905000008_create_risk_rules.sql` (new)
- `backend/app/risk/risk_rules.py` (new)
**Status going into this spec:** `plan_steps` already carries `risk_tier` and `requires_approval` columns (D11 migration). The values that populate those columns come from a lookup against the `risk_rules` table, which does not yet exist. This spec creates that table via a seeded migration and implements the in-process lookup helper in `risk_rules.py`. The `approval_gate.py` enforcement logic is **not** built here — that is D17.

---

## 1. Objective

1. **DB Layer:** Create the `risk_rules` table and seed it with the canonical 10-row rule set defined in Section 9.1 of the project manual. The table is **never written to by the running application or by any LLM** — only by a reviewed, signed-off migration.
2. **risk_rules.py:** Implement a lightweight, in-process lookup module (`backend/app/risk/risk_rules.py`) that reads the seeded rows once at startup (via Supabase service-role client) and exposes a single `lookup(action_type, mcp_server)` function returning a `RiskRule` dataclass (or `None` on miss).
3. **Fail-Closed Contract:** Any call to `lookup()` that returns `None` MUST be treated by the caller as `risk_tier="high", requires_approval=True`. The lookup module itself does not enforce this — it returns `None` honestly and the gate (D17) enforces the default-deny rule. The contract is documented and tested here so D17 can rely on it unconditionally.

---

## 2. Database — risk_rules Table

### 2.1 Schema

The hardcoded, seeded safety table. Global config — read-only to the app role; writable only via migration under service-role.

| Column | Type / Constraints | Notes |
|---|---|---|
| `id` | serial, PK | Auto-incrementing integer; not UUID (order matters for readability during reviews) |
| `action_type` | text, NOT NULL | e.g. `gmail.send_message`, `calendar.delete_event` |
| `mcp_server` | text, NOT NULL | `calendar` \| `gmail` \| `github` \| `slack` |
| `risk_tier` | text, NOT NULL | `low` \| `medium` \| `high` |
| `requires_approval` | boolean, NOT NULL | |
| `rationale` | text | Human-readable justification, shown to reviewers in PRs that touch this table |

**Unique constraint:** `UNIQUE(action_type, mcp_server)` — the lookup key must be unambiguous.

**CHECK constraints:**
- `mcp_server IN ('calendar', 'gmail', 'github', 'slack')`
- `risk_tier IN ('low', 'medium', 'high')`

**RLS policy:** `risk_rules` is a global config table — it has no `user_id` column. Enable RLS but add a **single SELECT policy** that allows the authenticated role to read all rows (the planner needs to perform lookups on behalf of any user). INSERT / UPDATE / DELETE remain service-role only (no policy = blocked for the client role).

---

### 2.2 Seed Data (canonical 10 rows)

| `action_type` | `mcp_server` | `risk_tier` | `requires_approval` | `rationale` |
|---|---|---|---|---|
| `calendar.list_events` | `calendar` | `low` | `false` | Read-only, no side effects |
| `calendar.create_event_internal_only` | `calendar` | `medium` | `false` | Reversible; all attendees on a known/internal domain |
| `calendar.create_event_external_attendee` | `calendar` | `high` | `true` | Involves a party outside the organisation; needs confirmation before external visibility |
| `calendar.delete_event` | `calendar` | `high` | `true` | Destructive and not easily reversible for the invitee's view |
| `gmail.create_draft` | `gmail` | `low` | `false` | Nothing leaves the user's account |
| `gmail.send_message` | `gmail` | `high` | `true` | Irreversible the moment it is sent |
| `github.create_issue` | `github` | `medium` | `false` | Reversible — can be closed/edited |
| `github.comment_on_issue` | `github` | `medium` | `false` | Visible externally but editable/deletable |
| `slack.post_message_dm` | `slack` | `medium` | `false` | Private; low blast radius |
| `slack.post_message_channel` | `slack` | `high` | `true` | Instantly visible to a whole workspace |

> **Fail-closed default (not a DB row):** Any `action_type` not present in the table must be treated as `risk_tier="high", requires_approval=True` by the lookup caller — never as safe. Silence in the rule table is never read as permission.

---

## 3. Migration

**File:** `backend/migrations/20260905000008_create_risk_rules.sql`

Steps the migration must perform:

1. `CREATE TABLE IF NOT EXISTS public.risk_rules (...)` with the schema in Section 2.1.
2. Add `UNIQUE(action_type, mcp_server)` constraint.
3. Add `CHECK` constraints on `mcp_server` and `risk_tier`.
4. `ALTER TABLE public.risk_rules ENABLE ROW LEVEL SECURITY;`
5. `DROP POLICY IF EXISTS "risk_rules_authenticated_select" ON public.risk_rules;` then re-create:

```sql
CREATE POLICY "risk_rules_authenticated_select" ON public.risk_rules
    FOR SELECT
    USING (true);
-- any authenticated user may read all rows; no user_id scoping needed.
-- No INSERT / UPDATE / DELETE policy for the client role — blocked by default.
```

6. `INSERT INTO public.risk_rules (...) VALUES (...) ON CONFLICT (action_type, mcp_server) DO NOTHING;` — all 10 seed rows in a single multi-row insert.

**Migration must be idempotent:** `CREATE TABLE IF NOT EXISTS`, `DROP POLICY IF EXISTS` + re-create, `ON CONFLICT DO NOTHING` for inserts.

---

## 4. risk_rules.py — In-Process Lookup Module

**File:** `backend/app/risk/risk_rules.py`

### 4.1 Data Structures

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class RiskRule:
    action_type: str
    mcp_server: str
    risk_tier: str          # "low" | "medium" | "high"
    requires_approval: bool
    rationale: str
```

### 4.2 Lookup Strategy

The module uses a **module-level in-memory cache** populated from Supabase (service-role read) at first call, then held for the lifetime of the process. The `risk_rules` table changes only via migrations (deploys), so a process-lifetime cache is safe and avoids a DB round-trip per plan step.

```python
from __future__ import annotations
from dataclasses import dataclass
from app.db.supabase_client import get_service_role_client

_cache: dict[tuple[str, str], RiskRule] | None = None


def _load_rules() -> dict[tuple[str, str], RiskRule]:
    client = get_service_role_client()
    rows = client.table("risk_rules").select("*").execute().data
    return {
        (row["action_type"], row["mcp_server"]): RiskRule(
            action_type=row["action_type"],
            mcp_server=row["mcp_server"],
            risk_tier=row["risk_tier"],
            requires_approval=row["requires_approval"],
            rationale=row.get("rationale", ""),
        )
        for row in rows
    }


def lookup(action_type: str, mcp_server: str) -> RiskRule | None:
    """
    Return the matching RiskRule, or None if no row exists for this
    (action_type, mcp_server) pair.

    CONTRACT: None MUST be treated as (risk_tier="high", requires_approval=True)
    by the caller. This function never defaults — it returns honestly.
    """
    global _cache
    if _cache is None:
        _cache = _load_rules()
    return _cache.get((action_type, mcp_server))


def invalidate_cache() -> None:
    """Force re-load on next lookup call. FOR TEST USE ONLY."""
    global _cache
    _cache = None
```

### 4.3 Supabase Client

Use `SUPABASE_SERVICE_ROLE_KEY` (not the user-JWT client) because `risk_rules` is a service-level config table with no user context. The service-role key bypasses RLS entirely — the SELECT-only RLS policy is a defence-in-depth measure for the client role, not the access path used by `risk_rules.py`.

---

## 5. Config / Env

No new environment variables required. Reuses:

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project endpoint |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role access to read `risk_rules` |

---

## 6. Security Notes

- **Never writable at runtime.** The table has no INSERT / UPDATE / DELETE policy for the client role. The application code has no write path to `risk_rules`. Any attempt to insert a row via the anon or authenticated role is rejected at the DB level.
- **No LLM in the loop.** `lookup()` is a pure dictionary read after the initial DB fetch. There is no model call, no prompt, and no probability — the decision is deterministic.
- **Fail-closed by design.** A missing row returns `None`, not a permissive default. The contract is explicit and tested.
- **Cache invalidation is test-only.** `invalidate_cache()` is exposed only for pytest fixtures. It MUST NOT be called from any production code path (enforced by the CI lint gate in Section 9.3).
- **Service-role key scoping.** `risk_rules.py` is the only module in the risk package that holds a reference to the service-role client. It MUST NOT pass that client reference outside the module.

---

## 7. Error Handling

| Case | Behaviour |
|---|---|
| Supabase unreachable at startup (first `lookup()` call) | Raise `RuntimeError("risk_rules: failed to load cache from Supabase")` — the process fails loudly rather than silently defaulting to permissive |
| `action_type` / `mcp_server` pair has no matching row | Return `None`; caller must default-deny |
| DB returns row with unexpected `risk_tier` value | The `CHECK` constraint prevents this at the DB level; if somehow reached, the value is passed through to the caller as-is — it will fail the caller's own tier validation |
| `invalidate_cache()` called in production code | Caught by the CI grep lint gate (Section 9.3) before it can reach production |

---

## 8. Out of Scope for D12

- `approval_gate.py` fail-closed enforcement (D17) — this spec builds only the lookup; the gate that calls it and enforces `None ? deny` is D17.
- `approvals` table and `POST /approvals/{step_id}` endpoint (D17).
- The Explanation LLM (Section 9.3 of project manual) — writes plain-English copy for the Approval Screen; owned by Ishani, wired in D17.
- Parameter-dependent action-type derivation (e.g. computing `calendar.create_event_internal_only` vs `calendar.create_event_external_attendee` from `input_params`) — that logic lives in the LangGraph risk-tag node (D13), not in `risk_rules.py`.
- Adding new rows for future MCP servers — handled by future reviewed migrations under the same pattern.

---

## 9. Acceptance / Test Criteria

### 9.1 Migration Tests

- `test_risk_rules_table_exists`: After migration, `SELECT 1 FROM public.risk_rules LIMIT 1` returns without error.
- `test_risk_rules_has_10_seed_rows`: `SELECT COUNT(*) FROM public.risk_rules` returns `10`.
- `test_risk_rules_rls_client_cannot_insert`: Inserting a row with the anon/authenticated role is rejected (PostgreSQL error code `42501`).
- `test_risk_rules_rls_authenticated_can_select`: `SELECT * FROM public.risk_rules` with a valid user JWT returns all 10 rows.
- `test_risk_rules_unique_constraint`: Attempting to insert a duplicate `(action_type, mcp_server)` pair via service role raises a unique-violation error.
- `test_risk_rules_check_constraint_rejects_bad_tier`: Attempting to insert a row with `risk_tier = 'extreme'` via service role raises a check-violation error.

### 9.2 risk_rules.py Unit Tests

- `test_lookup_returns_rule_for_known_action`: `lookup("gmail.send_message", "gmail")` returns a `RiskRule` with `risk_tier="high"` and `requires_approval=True`.
- `test_lookup_returns_none_for_unknown_action`: `lookup("calendar.summon_dragon", "calendar")` returns `None`.
- `test_lookup_caches_after_first_call`: Call `lookup()` twice; assert the Supabase client's `.execute()` is called exactly once (use `unittest.mock.patch`).
- `test_invalidate_cache_forces_reload`: Call `invalidate_cache()` then `lookup()`; assert the Supabase client's `.execute()` is called again.
- `test_all_10_seed_rows_are_reachable`: Parametrised test — for every `(action_type, mcp_server)` pair in the canonical seed set (Section 2.2), assert `lookup()` returns a non-`None` `RiskRule`.
- `test_risk_rule_is_immutable`: Attempting to mutate a returned `RiskRule` field raises `FrozenInstanceError` (validates `frozen=True` on the dataclass).

### 9.3 Lint / CI Gate

```bash
# Fails the build if invalidate_cache() appears in any non-test, non-definition file:
grep -r "invalidate_cache" backend/app --include="*.py" \
  | grep -v "test_" \
  | grep -v "risk_rules.py"
# Must return no matches.
```

Add as a step in the CI workflow (alongside `pytest`).

---

## 10. Dependencies

- D2 complete (Supabase project reachable; migration runner in place).
- D11 complete (`plan_steps.risk_tier` and `plan_steps.requires_approval` columns exist — they are the consumer of `risk_rules.lookup()` output in the planner, from D13 onwards).
- `SUPABASE_SERVICE_ROLE_KEY` present in `.env` (established at project init, confirmed used in D8/D9 OAuth token storage).
