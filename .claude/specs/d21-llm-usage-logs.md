# LLM Usage Logs & Rate-Limit Backoff Handling — Technical Spec

**Project:** AgentOps Copilot
**Plan reference:** D21 — "llm_usage_logs + rate-limit backoff handling (Groq/Gemini free tier)"
**Owner / track:** Suraj — backend
**Branch:** `feature/d21-llm-usage-logs`
**Files:**
- `backend/migrations/20260916000000_create_llm_usage_logs.sql` (new)
- `backend/app/llm/router.py` (modify)

**Status going into this spec:** The `router.py` (built in D18) currently logs LLM usage to a local JSON structured log because the `llm_usage_logs` table did not exist. The failover from Groq to Gemini is immediate and does not retry if both providers fail with rate limits.

---

## 1. Objective

1. **DB Layer:** Create the `llm_usage_logs` table with correct columns according to Section 7, Group F of the project manual.
2. **Real DB Logging:** Update `log_llm_usage` in `backend/app/llm/router.py` to write a real row to the `llm_usage_logs` table via the Supabase client instead of the temporary `logger`.
3. **Rate-Limit Backoff:** Add exponential backoff / retry handling to `route_llm_call`. Since we are using free-tier API keys, rate limits can happen concurrently across Groq and Gemini.

---

## 2. Database — New Table

### 2.1 llm_usage_logs

Every LLM attempt (success or failure) writes exactly one row.

| Column | Type / Constraints | Notes |
|---|---|---|
| `id` | bigint, PK, GENERATED ALWAYS AS IDENTITY | |
| `provider` | text | `groq` or `gemini` |
| `model` | text | |
| `tokens_in` | int | |
| `tokens_out` | int | |
| `latency_ms` | int | |
| `request_type` | text | `planning`, `routing`, `risk_explanation`, `banner`, or `memory_extraction` |
| `rate_limit_hit` | boolean, DEFAULT false | |
| `created_at` | timestamptz, DEFAULT now() | |

**Index:** Create an index on `created_at` (required for Trust Dashboard aggregations).

**RLS policy:** Internal — service-role only. Never exposed to the client. No `SELECT` or `INSERT` access for the authenticated user role.

---

## 3. Implementation Steps

### 3.1 Migration

Create a new idempotent migration file `backend/migrations/20260916000000_create_llm_usage_logs.sql`:
1. Create table `llm_usage_logs`.
2. Add `CHECK` constraint on `provider` (`groq`, `gemini`).
3. Add `CHECK` constraint on `request_type`.
4. Create an index on `llm_usage_logs(created_at)`.
5. Enable RLS and do NOT create any policies (meaning default deny for all clients). The backend will insert using the service-role key.

### 3.2 Update `log_llm_usage`

Modify `backend/app/llm/router.py`:
- Inject or import the Supabase service-role client.
- Replace the JSON logging inside `log_llm_usage` with a `.table("llm_usage_logs").insert(...)` call.
- Remember that `log_llm_usage` is synchronous/async (ensure compatibility with `route_llm_call`). If `route_llm_call` is async, the insertion should be non-blocking.
- Remove the `# TODO(D21)` marker once completed.

### 3.3 Rate-Limit Backoff Handling

Modify `route_llm_call` in `backend/app/llm/router.py`:
- Introduce a retry loop for the entire Groq -> Gemini fallback sequence.
- If both providers throw `LLMRateLimitError`, sleep (exponential backoff, e.g. `1s, 2s, 4s`) and retry the full sequence up to 3 times.
- If it fails after the max retries, raise `LLMRouterExhaustedError` as it currently does.
- Continue to log every failed attempt. If a rate limit is hit on attempt 1, it should still be logged as a failure in `llm_usage_logs`, and the retry attempt will log a separate row.

---

## 4. Error Handling & Edge Cases

- **Insert Failures:** If the `llm_usage_logs` insert fails, it should **not** crash the application or the LLM call. Catch any DB insert exceptions and fallback to `logging.error`.
- **Latency Logging:** Ensure that latency is measured accurately for each individual attempt, not across the retry loops.

---

## 5. Acceptance / Test Criteria

1. Migration successfully creates `llm_usage_logs`.
2. Running an LLM call through the router writes a row to `llm_usage_logs` in Supabase.
3. Forcing a rate limit on both Groq and Gemini triggers the backoff sleep and retries.
4. Calling `route_llm_call` successfully logs a row even if the `route_llm_call` was successful on the first try.
