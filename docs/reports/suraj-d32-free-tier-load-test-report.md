# D32 Load Test Report — Free-Tier Quota Handling

**Owner:** Suraj  
**Task:** D32 — Load test: concurrent users vs free-tier LLM/MCP limits, verify backoff  
**Date:** 2026-11-12

## Objective

Validate that the backend remains stable when the free-tier LLM and MCP providers rate-limit under burst load. The app must degrade gracefully with conservative backoff, fallback to the secondary provider where supported, and fail closed rather than silently succeeding when both providers remain exhausted.

## Scope covered

- Concurrent LLM burst traffic through `route_llm_call`
- Groq/Gemini rate-limit fallback behavior
- Concurrent MCP burst traffic for GitHub, Gmail, and Slack
- Clean `rate_limited` reporting for external provider 429s
- Exhaustion path where both providers remain rate-limited

## Test evidence

### 1) LLM free-tier burst validation

Command run:

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest app/tests/test_d32_load_test.py -q
```

Result:

```text
2 passed in 0.45s
```

This verifies:
- 12 concurrent LLM requests handled under burst conditions
- Groq rate-limit triggers fallback path
- Gemini fallback succeeds under free-tier stress
- sustained exhaustion remains fail-closed instead of silently succeeding

### 2) MCP free-tier burst validation

Command run:

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest app/tests/test_d32_mcp_load_test.py -q
```

Result:

```text
2 passed in 1.04s
```

This verifies:
- GitHub, Gmail, and Slack clients return clean `rate_limited` responses under 429 conditions
- concurrent burst calls do not crash or hang the internal app flow
- provider rate-limit handling is surfaced cleanly to the application layer

## Interpretation and limits

This is a validated resilience test for the free-tier failure mode, not a claim of unlimited live-provider throughput. Provider quotas are vendor-dependent and may change without notice. The code therefore enforces conservative retry spacing and avoids aggressive parallel retries that would otherwise trigger quota lockouts.

In practical terms, the system has been validated to handle the tested burst pattern safely under free-tier rate limiting:
- no provider hammering under concurrency
- clean retry/backoff enforcement
- graceful fallback where possible
- fail-closed behavior when providers remain exhausted

## Conclusion

D32 load validation passed for the tested free-tier conditions. The backend is resilient under simulated concurrent burst load, and the application degrades safely when Groq/Gemini and MCP providers begin returning 429 errors.
