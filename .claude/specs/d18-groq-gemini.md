# D18 — LLM Router (Groq Primary / Gemini Fallback)

**Manual reference:** Section 8.4, D18 day-plan cell
**Date:** Shifted from Sat 12 Sep to Sun 13 Sep (buffer day) per team's D17 schedule adjustment
**Owner:** Suraj (backend/orchestration track)
**Depends on:** D13 (LangGraph skeleton exists, not wired to a real LLM yet — see Out of Scope)

---

## 1. Why This Exists (plain language)

Every LLM-driven node in the planner (intent-classify, plan, risk-tag, and later the risk-explainer and banner model) needs one reliable way to ask a language model a question. Today's task builds that one chokepoint: a router that tries Groq first (cheap, fast, free-tier default) and automatically falls over to Gemini if Groq is rate-limited or down — with zero manual intervention and a log row for every attempt, successful or not.

Nothing about *what the planner asks* changes today. This task is purely: given a prompt, return an answer, pick the right provider, and log it.

---

## 2. Scope

### In Scope
- `backend/app/llm/groq_client.py` — thin async wrapper around the Groq API
- `backend/app/llm/gemini_client.py` — thin async wrapper around the Gemini API
- `backend/app/llm/types.py` — shared response dataclass + typed exceptions used by both clients and the router
- `backend/app/llm/router.py` — the fallback + logging chokepoint every caller uses
- `.env` additions: `GROQ_MODEL_DEFAULT`, `GEMINI_MODEL_DEFAULT` (see Section 5)
- A standalone manual test script (or two pytest cases) proving the fallback path works

### Out of Scope (explicitly deferred)
- **Wiring `nodes.py` to call the router.** D13's LangGraph skeleton was built with placeholder/stub logic for its nodes. Today's task builds the router as a self-contained, independently testable unit. Actually replacing the stub logic inside `intent_classify`/`plan`/`risk_tag` with real calls to `router.py` is a separate, future task — do not touch `backend/app/agents/nodes.py` today.
- **Real `llm_usage_logs` database writes.** Per Section 14 of the manual, the `llm_usage_logs` table itself is not created until **D21** ("llm_usage_logs + rate-limit backoff handling"). Today's router must still call a logging function on every attempt (success or failure) — but that function writes to a **local structured log** (Python `logging` module, JSON-formatted) rather than a real Supabase insert. See Section 6 for the exact interface, designed so swapping in the real DB write on D21 requires touching only one function body, not any caller.
- **Retry loops beyond the single Groq→Gemini failover.** No exponential backoff, no multiple attempts per provider. Section 8.4 describes an immediate failover on 429/5xx, not a retry-then-failover pattern. If both providers fail on a given call, the router raises a clear typed exception up to the caller — handling that (e.g. marking a task `failed`) is the caller's job, not the router's, and is out of scope until nodes.py is wired.
- **Cost estimation / `cost_estimate` field population.** That column exists on `execution_logs`, not `llm_usage_logs`, and isn't part of this task.
- **Streaming responses.** Not needed for planning/routing/risk-explanation calls; skip `generate_content_stream`/streaming chat completions entirely.

---

## 3. Design Decisions (stated up front so the coding agent doesn't re-derive them)

1. **One shared response shape.** Both providers return a common `LLMResponse` dataclass so the router (and eventually the planner nodes) never branches on which provider answered.
2. **Immediate failover, no retry-before-fallback.** Groq is tried exactly once. On `RateLimitError` or `ServerError` (see Section 6.3), Gemini is tried exactly once. Any other exception from Groq (e.g. bad request, auth error) is NOT treated as a failover trigger — it's a real bug and should surface immediately, not silently mask itself behind a Gemini call.
3. **Router is async.** FastAPI backend is async throughout; both clients must expose async call methods (`AsyncGroq`, `google-genai`'s `client.aio.models.generate_content`).
4. **Model names are configurable, not hardcoded.** Model strings change often on both providers. Both defaults live in `.env`, not in code, so a model deprecation doesn't require touching `router.py`.
5. **Logging is unconditional.** Every attempt against every provider gets one log call — including the Groq attempt that fails right before Gemini succeeds. This matches Section 8.4's "every call — successful or not — writes a row" language; today it just writes to a local log instead of the table until D21.

---

## 4. Packages to Install

```
pip install groq --break-system-packages
pip install google-genai --break-system-packages
```

**Verified as of today (13 Sep 2026):**
- Groq's official Python SDK is `groq` (async client class: `AsyncGroq`). This has not changed.
- Google's Gemini SDK landscape **has** changed: `google-generativeai` is deprecated (its support window ended 30 Nov 2025). Use **`google-genai`** (`from google import genai`) instead — this is the current unified SDK. Do not let the coding agent reach for `google-generativeai` from older training data or tutorials; it is legacy.

Add both to `backend/requirements.txt`.

---

## 5. Environment Variables

Add to `backend/.env` (both keys should already be present from the earlier setup step; the two model defaults below are new for today):

```
GROQ_API_KEY=<already set>
GEMINI_API_KEY=<already set>
GROQ_MODEL_DEFAULT=openai/gpt-oss-20b
GEMINI_MODEL_DEFAULT=gemini-3.7-flash
```

**Updated (13 Sep 2026):** Model names verified and confirmed as available:
- Groq: `openai/gpt-oss-20b` (previous `llama-3.3-70b-versatile` is deprecated)
- Gemini: `gemini-3.7-flash` (previous `gemini-2.5-flash` is deprecated)

Also add both new keys to `backend/.env.example` (with placeholder/empty values) so the team's env template stays accurate — do NOT put real values in `.env.example`.

---

## 6. File-by-File Specification

### 6.1 `backend/app/llm/types.py`

Defines the shared contract every part of this task uses.

```python
from dataclasses import dataclass
from enum import Enum

class LLMProvider(str, Enum):
    GROQ = "groq"
    GEMINI = "gemini"

@dataclass
class LLMResponse:
    text: str
    provider: LLMProvider
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    rate_limited: bool = False

class LLMProviderError(Exception):
    """Base class for all provider-level failures."""
    pass

class LLMRateLimitError(LLMProviderError):
    """Raised on a 429 from either provider."""
    pass

class LLMServerError(LLMProviderError):
    """Raised on a 5xx from either provider."""
    pass

class LLMRouterExhaustedError(Exception):
    """Raised when both Groq and Gemini have failed for the same request."""
    pass
```

### 6.2 `backend/app/llm/groq_client.py`

```python
async def call_groq(
    prompt: str,
    model: str | None = None,          # falls back to GROQ_MODEL_DEFAULT env var
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> LLMResponse:
    ...
```

- Uses `AsyncGroq(api_key=os.environ["GROQ_API_KEY"])`.
- Wraps the call in a timer to compute `latency_ms`.
- Maps Groq SDK exceptions to the shared types:
  - HTTP 429 → raise `LLMRateLimitError`
  - HTTP 5xx → raise `LLMServerError`
  - Anything else → let it propagate unchanged (do not swallow)
- On success, extract token counts from the Groq response object's usage field and return a populated `LLMResponse` with `provider=LLMProvider.GROQ`.

### 6.3 `backend/app/llm/gemini_client.py`

```python
async def call_gemini(
    prompt: str,
    model: str | None = None,          # falls back to GEMINI_MODEL_DEFAULT env var
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> LLMResponse:
    ...
```

- Uses `genai.Client(api_key=os.environ["GEMINI_API_KEY"])` and calls `client.aio.models.generate_content(...)` (the async path on the current `google-genai` SDK — do not use the sync method inside an async function).
- Same latency timing and exception-mapping pattern as `groq_client.py`, using whatever HTTP status the `google-genai` SDK surfaces for rate limits (429) and server errors (5xx).
- Returns `LLMResponse` with `provider=LLMProvider.GEMINI`.

### 6.4 `backend/app/llm/router.py`

```python
async def route_llm_call(
    prompt: str,
    request_type: str,   # "planning" | "routing" | "risk_explanation" | "banner" | "memory_extraction"
    groq_model: str | None = None,
    gemini_model: str | None = None,
) -> LLMResponse:
    ...
```

Logic:
1. Call `call_groq(prompt, model=groq_model)`.
2. On success: call `log_llm_usage(response, request_type)`, return the response.
3. On `LLMRateLimitError` or `LLMServerError` from Groq:
   - Log the failed Groq attempt (`log_llm_usage` with a failure variant — see 6.5)
   - Call `call_gemini(prompt, model=gemini_model)`
   - On Gemini success: log it, return the response
   - On Gemini failure too: log the Gemini failure, then raise `LLMRouterExhaustedError` with both underlying errors attached (e.g. as `__cause__`/`__context__` or a combined message) so whatever calls this later has a real error to act on.
4. Any other exception from Groq (not rate-limit/server-error) propagates immediately — no fallback attempt.

`request_type` is a required parameter, not inferred — the caller always knows why it's calling the LLM, and this value is what eventually populates `llm_usage_logs.request_type` per the Section 8.4 schema.

### 6.5 Logging interface (temporary, pre-D21)

Add this to `router.py` or a small `backend/app/llm/logging.py`:

```python
import logging
import json

_llm_logger = logging.getLogger("llm_usage")

def log_llm_usage(
    provider: str,
    model: str,
    request_type: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    rate_limit_hit: bool,
    success: bool,
) -> None:
    _llm_logger.info(json.dumps({
        "provider": provider,
        "model": model,
        "request_type": request_type,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "rate_limit_hit": rate_limit_hit,
        "success": success,
    }))
```

**Mark this function clearly with a `# TODO(D21):` comment** stating it must be replaced with a real insert into the `llm_usage_logs` table once that table exists, using the exact column names from Section 7, Group F of the manual. The call sites in `router.py` should not need to change on D21 — only this function's body.

---

## 7. Error Handling Summary

| Scenario | Behavior |
|---|---|
| Groq succeeds | Return response, one log row |
| Groq 429/5xx → Gemini succeeds | Two log rows (Groq failure + Gemini success), return Gemini's response |
| Groq 429/5xx → Gemini also fails | Two log rows (both failures), raise `LLMRouterExhaustedError` |
| Groq raises a non-rate-limit/non-server error (e.g. bad API key, malformed request) | Propagates immediately, no Gemini attempt, no silent masking |

This deliberately mirrors the manual's own separation principle (Section 8.4, last row): the router decides *which model answers*; it has no opinion on risk or approval, and it must never hide a real configuration bug behind a fallback.

---

## 8. Testing Requirements for Today

Two minimum checks before calling D18 done:

1. **Happy path:** call `route_llm_call("Say hello in one sentence.", request_type="planning")` with valid keys. Confirm it returns a populated `LLMResponse` from Groq and exactly one log line appears.
2. **Fallback path:** force a Groq failure (temporarily set `GROQ_API_KEY` to an invalid value, or monkeypatch `call_groq` to raise `LLMRateLimitError`) and confirm the same call transparently returns a Gemini `LLMResponse`, with two log lines (one failure, one success).

A `pytest` file (`backend/app/tests/test_llm_router.py`) with these two cases is preferred over a throwaway script, so this becomes part of the regression suite the manual references in Section 15 — but a manual script is acceptable today if time is tight, provided both scenarios are actually exercised once.

---

## 9. Open Items / Flags

- **Model string drift:** `GROQ_MODEL_DEFAULT` and `GEMINI_MODEL_DEFAULT` values in Section 5 should be verified against your live console access before testing — both providers rename/deprecate models frequently.
- **`llm_usage_logs` table doesn't exist yet** (arrives D21) — logging today is local/structured only, with an explicit TODO marker for the swap.
- **Gemini rate-limit/server-error status codes**: the coding agent should confirm exactly which exception classes/status codes the current `google-genai` SDK raises for 429 and 5xx before finalizing the `except` mapping in `gemini_client.py` — SDK-specific exception types are more reliable than parsing raw HTTP codes if the SDK exposes them.

---

## 10. Acceptance for D18

- [ ] `groq_client.py`, `gemini_client.py`, `types.py`, `router.py` created under `backend/app/llm/`
- [ ] Both packages in `requirements.txt`
- [ ] `.env` and `.env.example` updated with the two new model-default vars
- [ ] Happy-path test passes (Groq answers, one log line)
- [ ] Fallback test passes (Gemini answers after simulated Groq failure, two log lines)
- [ ] Non-rate-limit Groq errors are confirmed to propagate without a Gemini attempt
- [ ] `nodes.py` is untouched
- [ ] `log_llm_usage` has the `# TODO(D21)` marker