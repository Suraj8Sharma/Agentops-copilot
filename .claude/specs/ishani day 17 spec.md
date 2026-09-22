Spec: Notification-Banner Model — First Working Version

Owner: Ishani · Day: D17, Fri 11 Sep · File: backend/app/notifications/banner_model.py

Derived from the AgentOps Implementation Manual (Team Structure §3, Risk & Approval Gate §9, LLM Router §8.4, Data Model §7 notifications/llm_usage_logs, API Reference §10, Testing §15). Day-level scope (what "first working version" means) is interpreted from where D17 sits between D11 (spec + prompt draft) and D19/D20/D29 (wiring, copy rules, golden eval) — flagged inline as [interpreted] wherever the manual doesn't state it verbatim.

1. Problem Statement

AgentOps sends users push + in-app notifications (approval requests, task completions, digests, OAuth expiry warnings). Each notification carries a short, human-readable banner line written by a small LLM call rather than a static template, so the copy can vary naturally by context while staying strictly factual.

This model is deliberately built and evaluated separately from the planner and the approval gate, and owned by Ishani rather than Suraj, for one reason: a bad or vague banner line must never be able to change what the agent actually does or bypass the fail-closed approval logic (§9.2). It is advisory copy only.

By D11, the spec and prompt were drafted. D17's job is to turn that draft into a first working version of banner_model.py: a callable module that takes a notification event and returns a generated banner_text string, using the same LLM router (Groq primary / Gemini fallback) as the rest of the system. Full wiring into the live notification pipeline, per-event-type copy rules, and the golden-dataset eval pass come later (D19, D20, D29) — not part of this task.

2. Functional Requirements
FR1 — Generate a banner line from an event. Given a notification event (type + relevant context, e.g. task/approval details), the module produces a short, plain-English banner_text line describing what happened or what's pending.
FR2 — Cover all four notification types. Must handle approval_needed, task_completed, digest_ready, and oauth_expiring (the enum values on notifications.type).
FR3 — State only facts present in the input. No invented details — same discipline as the explanation LLM in §9.3.
FR4 — Non-alarming, non-persuasive tone. The banner describes; it never recommends or argues for a decision.
FR5 — Length-capped output. Output must fit a mobile banner/push-notification line (short — one clause, not a paragraph).
FR6 — Route through the shared LLM router. Use backend/app/llm/router.py (Groq primary, Gemini fallback on 429/5xx) rather than calling a provider directly (§8.4).
FR7 — Log every call. Every invocation writes a row to llm_usage_logs with request_type = 'banner' (provider, model, tokens_in/out, latency_ms, rate_limit_hit).
FR8 — Purely advisory output. The returned banner_text is a display value only. Nothing in approval_gate.py or any decision path may read it (mirrors the §9.3 Guardrail 3 separation already required for the explanation LLM).
FR9 — Independently callable/testable. The module must be invokable standalone (not only from inside the full notification pipeline), since trigger_rules.py (Suraj, D20) and the notifications table/endpoint (Suraj, D24) don't land until after D17 — this is what "first working version" scopes to. [interpreted]
3. API Contract

There is no public HTTP endpoint for this model at D17 — it's an internal Python module called by the notification pipeline once that pipeline exists (Suraj's trigger_rules.py, D20). The contract at this stage is the function-level interface, following the same INPUT → SYSTEM → OUTPUT shape the manual uses for the sibling explanation LLM in §9.3:

Module: backend/app/notifications/banner_model.py

Input (event payload — mirrors the fields needed to populate notifications):

json
{
  "type": "approval_needed | task_completed | digest_ready | oauth_expiring",
  "context": {
    "task_id": "uuid, optional",
    "tool_name": "string, optional — e.g. gmail.send_message",
    "summary": "string — the fact(s) the banner may reference"
  }
}

System prompt contract (same guardrail pattern as §9.3):

"You write one short, plain-English notification banner line for an AI task-assistant app. State only facts present in the input. Never invent details. Never suggest what the user should do. Non-alarming tone."

Output:

json
{
  "banner_text": "string — short, factual, non-alarming",
  "provider": "groq | gemini",
  "latency_ms": 123
}

Downstream consumers (not built at D17, for context only):

Method	Path	Notes
GET	/notifications	Eventually lists records whose banner_text column this model populates
POST	/notifications/{id}/read	Marks a notification read; unrelated to generation

Persistence target (future): notifications.banner_text (text, advisory only per §7 data model).

4. Constraints
Free-tier LLM limits (§2.3, §8.4): Groq is primary; any 429/5xx auto-falls-back to Gemini. No manual intervention, no dropped call.
Usage must be auditable: every call logged to llm_usage_logs, not a black box (§8.4).
Strict separation from decision logic: the banner model must never influence approval_gate.py or any risk decision — decisions are governed solely by risk_rules (§9).
Owned and evaluated independently of the planner: built and tested apart from Suraj's planner/router/explainer stack, even though it shares the LLM router.
Evaluated via the shared eval pipeline, but a separate category: golden cases live in eval_cases under category = 'banner', authored by Sanskriti/Shivangi, replayed by Suraj's harness into eval_runs (suite_name = 'banner_model_eval') — full case set isn't delivered until Gate 2 (19 Sep) and finalized D29, so D17 cannot depend on the complete golden set. [interpreted]
Output length: must satisfy test_banner_model_output_length_under_limit (§15.1) — keep well under a banner/push line's practical character limit.
5. Edge Cases & Error Handling
Case	Expected Handling
Groq returns 429 or 5xx	Router auto-falls-back to Gemini; call still succeeds and is logged with rate_limit_hit = true (§8.4).
Both Groq and Gemini fail/unavailable	Module must fail safely — return no banner line (or a minimal non-LLM fallback) rather than raising an error that blocks the parent notification from being created. [interpreted — not stated in manual; flag with Suraj/Ishani before D19 wiring]
Missing or malformed context fields	Model must not fabricate the missing facts (FR3) — degrade to a generic, still-accurate line rather than inventing specifics.
Unknown/unsupported type value	Reject or log — should not silently produce a mismatched banner (test_banner_model_matches_triggering_event_type, §15.1).
Model output exceeds length cap	Truncate or regenerate; must not ship an over-length banner (violates test_banner_model_output_length_under_limit).
Model output implies a recommendation ("you should approve this")	Guardrail violation — same non-alarming/non-persuasive bar as §9.3 Guardrail 2; must be caught before this is considered "working."
Model output references facts not present in input	Guardrail violation — same as §9.3 Guardrail 1 ("no false claims about the action"), applied to banner copy.
Downstream pipeline not yet live (pre-D20 trigger_rules.py, pre-D24 notifications table)	Module must be testable in isolation (direct function call / script), independent of the not-yet-built pipeline (FR9).
6. Acceptance Criteria

Scoped to D17's "first working version" milestone — full production wiring is explicitly later work (D19–D29):

AC1: banner_model.py exists and exposes a callable function that accepts the event payload (§3) and returns banner_text for each of the four supported type values (FR2).
AC2: Calls route through backend/app/llm/router.py; a forced-Groq-failure test demonstrates the Gemini fallback engages, consistent with test_llm_router_falls_back_to_gemini_on_groq_429 (§15.1).
AC3: Every call produces a corresponding llm_usage_logs row with request_type = 'banner'.
AC4: Output passes test_banner_model_output_length_under_limit and test_banner_model_matches_triggering_event_type (§15.1) against at least a smoke set of hand-written cases (the full Sanskriti/Shivangi golden set isn't due until Gate 2 / D29). [interpreted]
AC5: Manual spot-check confirms outputs are factual (no invented details) and non-alarming in tone — the same bar §9.3 sets for the sibling explanation LLM.
AC6: Demonstrated that no other module (in particular approval_gate.py) reads or depends on banner_text — the advisory-only separation (FR8) is verifiably intact.
AC7: Module is callable/testable standalone, without requiring Suraj's trigger_rules.py or the live notifications table to exist yet (FR9).