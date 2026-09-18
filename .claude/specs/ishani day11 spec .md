Day 11 Spec — Notification-Banner Small Model (Spec + Prompt Draft)

Owner: Ishani | Date: Fri, 4 Sep 2026 | Week: 2 (Auth + OAuth phase) Key file (built later): backend/app/notifications/banner_model.py

1. Problem Statement

Notifications (approval_needed, task_completed, digest_ready, oauth_expiring) carry a title and body, but the manual also calls for a short, plain-English banner line — a quick, human-readable gloss of what happened, shown as the push/in-app banner text. Someone glancing at a notification shouldn't have to parse a full body to know what's going on.

This banner text is LLM-written, which creates a specific risk the design has to close off from the start: a bad or vague banner line must never be able to change what the agent actually does. Section 3 states this explicitly — the model is "built and evaluated separately from the planner so a bad banner line can never change what the agent actually does." Day 11's job is not to build the model yet (that's D17) — it's to write the spec and a first prompt draft so D17's build has something concrete to implement against.

2. Functional Requirement
Own and author backend/app/notifications/banner_model.py — a small, fast LLM call, backend-adjacent but explicitly Ishani's, not Suraj's (Section 3).
The model takes a notification event as input and produces a short line of copy for notifications.banner_text.
Must cover all four notification types defined in the notifications.type enum: approval_needed, task_completed, digest_ready, oauth_expiring — each needs banner copy that reads naturally for that event.
Strict separation from the planner/agent logic — this is the same design principle used for the risk-explanation LLM in Section 9.3 ("Risk gate hard, explanation soft"), applied here to notifications: the banner model describes, it never decides or triggers. Suraj's trigger_rules.py (built D20) owns what fires and why; the banner model only writes the copy for what already fired.
D11's actual deliverable is two artifacts:
A written spec (input/output shape, tone rules, per-event-type behavior)
A first draft system prompt, in the same style as the Section 9.3 explanation-LLM prompt (plain-English, no invented details, non-alarming tone)
Downstream dependency chain this spec sets up: D17 (first working version) → D19 (coordinate output into in-app banner, with Jigyasu) → D20 (banner copy rules per event type, with Suraj) → D29 (quality pass vs. golden banner-text cases).
3. API Contract

There is no new client-facing REST endpoint for this — the banner model is an internal backend call invoked when a notification is created, not something the Flutter app calls directly. The client-facing surface is already defined:

Method	Path	Auth	Purpose
GET	/notifications	JWT	List in-app notifications (includes banner_text)
POST	/notifications/{id}/read	JWT	Mark a notification read

Storage contract — notifications table (Group E):

Column	Type	Notes
banner_text	text	Short LLM-written line, advisory only, display field
type	text	approval_needed | task_completed | digest_ready | oauth_expiring — drives which banner copy applies
title, body	text	Full notification content the banner line summarizes

Internal model contract (to spec on D11, mirroring the Section 9.3 explanation-LLM pattern):

Input: the triggering event — type, and the relevant payload fields for that event (e.g. for approval_needed, the step's tool_name/input_params; for oauth_expiring, the provider and expires_at).
Output: a single short banner string.
Logging: every call must be logged with request_type = "banner" — this is already a defined value in llm_usage_logs.request_type's enum (planning | routing | risk_explanation | banner | memory_extraction), so the spec should account for this from day one rather than bolting it on later.
4. Constraints
Separate ownership, separate eval — banner model is Ishani's, evaluated independently from Suraj's planner/router eval, specifically so a banner bug can never become an agent-behavior bug (Section 3, Section 15.1).
Advisory-only, by design — nothing in approval_gate.py or the planner reads banner_text to make any decision; it's a pure display field. The spec should state this constraint explicitly rather than leave it implicit, since it's the whole point of the separation.
Free-tier LLM budget — banner calls go through the same Groq-primary/Gemini-fallback router as every other LLM call (Section 8.4) and count against the same rate limits; the spec should treat this as a "keep it small and fast" constraint, not an unlimited-budget assumption.
Built ahead of its own dependencies — the notifications table isn't live until D24, trigger_rules.py isn't built until D20, and FCM setup is D17. D11 is deliberately a spec-only, no-code-dependency day: the schema (Section 7, Group E) is already fixed at manual-writing time, so the spec can be written precisely without needing the table to exist yet.
Tone/content guardrails, following the same philosophy as the Section 9.3 explanation LLM even though that section is written for risk explanations specifically: non-alarming, no invented details, states only facts present in the input.
5. Edge Cases & Error Handling

The manual doesn't spell out banner-model failure handling explicitly — this is a gap worth resolving in the D11 spec itself, not deferring. Points to design for, based on adjacent patterns in the document:

Banner generation failure — since banner_text is advisory-only, a failed/timed-out banner call should plausibly still let the notification itself (title/body) go out; the spec should state whether banner_text is nullable-on-failure rather than blocking the notification. (Inferred from the "advisory only" design principle — not stated outright in the manual, so flag this as a decision to confirm with Suraj.)
Output length — must respect a length cap; this is a named, tested requirement (test_banner_model_output_length_under_limit, Section 15.1), so the spec should define the actual character/word limit now rather than leaving it to D17.
Event-type mismatch — the banner text must match the triggering event type (test_banner_model_matches_triggering_event_type); the spec should define per-type templates or constraints so this is testable against golden cases from the start.
Golden-dataset alignment — Sanskriti authors notification-banner-text eval cases on D21; the D11 spec should anticipate the eval_cases schema (category = banner, input_prompt, expected_output) so those cases can be written against a stable input/output contract rather than a moving target.
Rate-limit/fallback behavior — since banner calls share the Groq/Gemini router, a 429 on Groq should fail over to Gemini automatically per Section 8.4, same as any other LLM call; no banner-specific exception should be introduced.
6. Acceptance Criteria

None of the ten numbered acceptance criteria (Section 18) name the banner model directly — it's not one of the ten headline gates. The criteria that do apply come from the CI-level eval suite (Section 15.1) and should be treated as D11's real "definition of done" for the spec itself:

Test	What it requires
test_banner_model_output_length_under_limit	Output stays under the length cap the D11 spec must define.
test_banner_model_matches_triggering_event_type	Banner copy is correct for its type — spec must define per-type expectations clearly enough to test against.
test_eval_suite_regression_no_new_failures_vs_last_frozen_run (suite-wide)	A later prompt change to the banner model can't silently regress a previously-passing golden case.

Indirect tie-in: Widget-level acceptance (A7, 80% coverage floor) will eventually cover banner_widget.dart (Jigyasu's rendering component, D19) — not the model itself, but worth noting since the two are coordinated in the same week (D19–D20).

Compiled from AgentOps Copilot Technical Implementation Manual v2.0 — Sections 3, 7 (Group E, Group F), 8.4, 9.3 (design pattern), 10, 11, 14 (D11, D17, D19, D20, D21, D29), 15.1.

Content
AgentOps_Implementation_Manual.docx

DOCX