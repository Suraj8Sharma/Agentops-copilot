Spec: Coordinate Notification-Banner Output into the In-App Banner

Owner: Ishani (with Jigyasu) · Day: D19, Mon 14 Sep · Week 4 (14–19 Sep)

Derived from the AgentOps Implementation Manual (§3 Team Structure, §6 Page Inventory, §7 Data Model — notifications, §9.3 advisory-only guardrails, §10 API Reference, §11.1/Appendix D file ownership, §14 Day Plan D17–D24, §16.3 Definition of Done, §17 Gate 2). Points not stated verbatim are marked [interpreted].

1. Problem Statement

Week 4 is notifications week — trigger, delivery, banner model, digests. Ownership is deliberately split down the middle: Suraj defines what fires and why (trigger_rules.py), Ishani owns the small LLM that writes the banner copy (backend/app/notifications/banner_model.py), and Jigyasu owns client-side delivery — push registration, the in-app banner component, and tap-to-open (mobile/lib/features/notifications/banner_widget.dart).

That split is what creates D19's problem. On D17 Ishani produced a first working version of the banner model that returns a banner_text string. On D19 Jigyasu builds the banner UI component and tap-to-open handling. Both sides are being built on the same day, against a backend that does not exist yet: trigger_rules.py lands D20, and the notifications table plus the FCM push endpoint land D24.

Ishani's D19 task is therefore not to build the banner UI — that is Jigyasu's file. It is to agree and pin down the contract between model output and banner component, so that when Suraj's table and trigger rules land on D20/D24 both halves already fit. Without this, either the model emits a shape the widget can't render, or the widget assumes fields the model never produces, and the mismatch surfaces at Gate 2 (19 Sep) when "notification banner rendering" is a required item.

This mirrors the pattern the plan uses elsewhere the same week: Shivangi finalises a Digest payload mock while the backend job is still pending, and Jigyasu agrees the Notifications-screen payload contract with Suraj on D23. Contract first, wiring later.

Explicitly not in scope for D19: the banner UI component itself and tap-to-open implementation (Jigyasu, D19); per-event-type copy rules (Ishani with Suraj, D20); in-app banner display logic (Jigyasu, D20); the live notifications table and push endpoint (Suraj, D24); the banner eval cases (Sanskriti, D21).

2. Functional Requirements
FR1 — Agreed banner payload contract. A single documented shape that banner_model.py emits and banner_widget.dart consumes, covering all four notification types: approval_needed, task_completed, digest_ready, oauth_expiring.
FR2 — Contract aligns with the notifications table. Field names and semantics must map cleanly onto the columns Suraj will create on D24 — type, title, body, banner_text, read, related_task_id — so no translation layer is needed later.
FR3 — Tap-to-open routing defined. The contract must carry enough information for the banner to route on tap: related_task_id for task-linked types, and a defined destination for types with no task (e.g. digest_ready, oauth_expiring). [interpreted — the manual specifies tap-to-open as Jigyasu's behaviour but does not state the routing key]
FR4 — Length budget fixed and shared. The character cap the model enforces (test_banner_model_output_length_under_limit) must be the same cap the widget is designed to render without truncation or overflow.
FR5 — Mock payload delivered. A worked example payload per event type, usable by Jigyasu to build and test the widget before any real notification exists.
FR6 — Advisory-only separation preserved in the contract. banner_text is a display field. The contract must not give the client any field that influences a decision, and no approval or risk behaviour may key off banner content (§9.3 Guardrail 3, §9 separation).
FR7 — Fallback path defined. The contract must specify what the widget renders when banner_text is absent or empty — the model can fail, and the notification must still display. [interpreted]
FR8 — Contract documented and shared with Suraj. D20 depends on it (Ishani's copy rules, Jigyasu's display logic) and D24 depends on it (Suraj's table and push endpoint), so it must be written down, not agreed verbally.
3. API Contract

No HTTP endpoint is authored on D19. The deliverable is the contract — an internal payload shape spanning banner_model.py (producer) and banner_widget.dart (consumer), pinned ahead of the backend.

Banner payload (proposed shape, to be ratified with Jigyasu and Suraj):

json
{
  "notification_id": "uuid — nullable pre-D24 while the table is pending",
  "type": "approval_needed | task_completed | digest_ready | oauth_expiring",
  "title": "string — short header",
  "body": "string — fuller text for the notifications list",
  "banner_text": "string | null — LLM-written line, advisory only, length-capped",
  "related_task_id": "uuid | null — tap-to-open target for task-linked types",
  "read": false,
  "created_at": "timestamptz"
}

Field mapping to notifications (§7, live D24):

Contract field	Column	Notes
notification_id	id	uuid, PK
type	type	approval_needed | task_completed | digest_ready | oauth_expiring
title	title	text
body	body	text
banner_text	banner_text	"Short LLM-written line (Section 9.3), advisory only"
related_task_id	related_task_id	uuid, FK tasks(id)
read	read	boolean, default false
created_at	created_at	timestamptz

RLS: user_id = auth.uid() — the client only ever sees its own notifications.

Endpoints this contract will flow through (Suraj, later):

Method	Path	Auth	Purpose
GET	/notifications	JWT	List in-app notifications
POST	/notifications/{id}/read	JWT	Mark a notification read

Producer side (Ishani, banner_model.py): emits banner_text only; type, title, body, related_task_id originate from Suraj's trigger rules. Consumer side (Jigyasu, banner_widget.dart): renders the banner and handles tap-to-open; must not depend on any field outside this contract.

4. Constraints
Split ownership is fixed. Ishani owns banner_model.py; Jigyasu owns banner_widget.dart. D19 is coordination across that boundary — Ishani does not write the widget.
Backend not yet live. trigger_rules.py is D20, the notifications table and FCM push endpoint are D24. The contract must be agreeable without either, exactly as Shivangi's Digest payload mock is finalised while its job is pending.
Advisory-only, non-negotiable (§9, §9.3). Banner copy can never influence what the agent does or whether an action needs approval — that is risk_rules alone. This constraint is the reason the banner model is owned separately from the planner in the first place.
Model guardrails carry into the contract: facts-only (no invented details), non-alarming and non-persuasive tone, length-capped output.
Free-tier LLM behaviour (§8.4). Banner generation routes through the Groq-primary / Gemini-fallback router and can be slow or fail under rate limits; the contract cannot assume banner_text is always present or always fast.
FCM token churn (§2.3). Device-token rotation and uninstalls need explicit handling or notifications silently stop delivering — Jigyasu's push-delivery suite covers stale tokens, but the contract should not assume guaranteed delivery.
Gate 2 (19 Sep) requires notification banner rendering to be working — five working days out, with the table landing on the gate day itself.
Definition of Done (§16.3): one paragraph of docs written the same day. For a contract task, that document is the deliverable.
5. Edge Cases & Error Handling
Case	Expected Handling
banner_text is null or empty (model failed, or both LLM providers down)	Banner still renders using title/body; the notification is never suppressed because copy generation failed. [interpreted — carries forward the open question flagged in the D17 spec]
Banner generation is slow (Groq rate-limited, Gemini fallback)	Notification must not block on copy — display path must tolerate banner_text arriving late or not at all. [interpreted]
Model output exceeds the agreed length cap	Model-side truncation/regeneration; the widget must additionally handle overflow gracefully rather than trusting the producer.
related_task_id is null (digest_ready, oauth_expiring)	Tap-to-open routes to a defined non-task destination rather than failing or dead-ending. [interpreted]
Banner copy doesn't match the triggering event type	Caught by test_banner_model_matches_triggering_event_type — the contract must make type authoritative, not inferred from copy text.
Unknown type value arrives at the widget	Render a safe generic banner rather than crashing; unknown types must not break the notification surface. [interpreted]
Tapping an approval_needed banner for an already-decided step	Routes to the task/approval surface and shows current state; must not re-open a stale approval prompt or imply a pending decision. [interpreted]
Banner content used, anywhere, to gate or influence an action	Contract violation — the approval gate reads risk_rules only (§9).
Contract changes after D20/D24 wiring begins	Treat as a coordinated change across all three owners (Ishani, Jigyasu, Suraj), not a unilateral edit — both D20 tasks and the D24 table depend on it.
6. Acceptance Criteria
AC1: A written banner payload contract exists, covering all four notifications.type values, agreed by Ishani and Jigyasu and shared with Suraj.
AC2: Every field in the contract maps onto a column Suraj will create in the notifications table on D24 — no orphan fields requiring a later translation layer.
AC3: A mock payload per event type is delivered to Jigyasu, sufficient to build and test banner_widget.dart before the backend is live.
AC4: The agreed length cap is a single shared number, enforced model-side and designed for widget-side.
AC5: Tap-to-open routing is defined for every type, including types with no related_task_id.
AC6: The null/empty banner_text fallback is specified, and the notification still renders in that case.
AC7: The contract is demonstrably advisory-only — no field or behaviour in it can influence the approval gate or any risk decision.
AC8: D20 can proceed on the contract without renegotiation: Ishani's per-event-type copy rules (with Suraj) and Jigyasu's in-app display logic both consume it as-is.
AC9: Contract documented the same day per §16.3, in module docs or docs/, and the day's diary entry reflects it. [interpreted]