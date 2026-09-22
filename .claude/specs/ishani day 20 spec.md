Spec: Banner Copy Rules Per Event Type

Owner: Ishani (with Suraj) · Day: D20, Tue 15 Sep · Week 4 (14–19 Sep)

Derived from the AgentOps Implementation Manual (§3 Team Structure, §4.2 Design Principles, §7 Data Model — notifications, §8.4 LLM Router, §9.3 Explanation LLM guardrails, §14 Day Plan D17–D29, §15.1 LLM Evaluation Pipeline, §16.3 Definition of Done, §17 Gate 2). Points not stated verbatim are marked [interpreted].

1. Problem Statement

Up to now the banner model has been generic. D17 produced a first working version that takes an event and returns a line of copy; D19 pinned the payload contract between that output and Jigyasu's in-app banner component. Neither step said anything about what a good banner line actually says for each kind of event.

D20 is where that gets decided. All three notification owners converge on the same day: Suraj documents the trigger rules — which event types fire and when — Jigyasu builds the display logic that consumes those event types plus the model output, and Ishani defines the copy rules that sit between them. Ishani's task is explicitly paired with Suraj, because the copy rules can only be written against the firing logic he is documenting the same day.

The four event types are not interchangeable. approval_needed is a prompt for a human decision on a risk-flagged action and must stay strictly descriptive — the design principle is risk gate hard, explanation soft: copy describes the decision, it never influences it. task_completed is a factual report on something already done. digest_ready is a passive availability notice. oauth_expiring is a warning about a connection that will break, where a silent failure is an explicit acceptance-criteria violation (A3). Each needs different information, a different register, and a different length budget — and each needs rules concrete enough that the eval suite can test compliance on D29.

Without per-type rules, the model produces plausible-sounding copy with no defined bar to measure against, and Sanskriti's D21 banner-text eval cases have nothing to encode expectations from.

Explicitly not in scope for D20: the trigger/firing logic itself (Suraj, D20); the in-app banner display logic and component (Jigyasu, D19–D20); the banner eval cases (Sanskriti, D21); the model quality pass against golden banner-text cases (Ishani, D29); the notifications table and push endpoint (Suraj, D24).

2. Functional Requirements
FR1 — A defined copy rule per event type. Distinct, documented rules for approval_needed, task_completed, digest_ready, and oauth_expiring — the four values on notifications.type.
FR2 — Each rule specifies its input fields. Which facts from the event payload the copy for that type may reference (e.g. tool_name, task summary, provider name), so the model never has to reach for information it wasn't given.
FR3 — Each rule specifies register and tone bounds. Non-alarming and non-persuasive throughout, carrying forward the §9.3 guardrails; approval_needed in particular describes, never recommends.
FR4 — Each rule specifies a length budget. Within the single shared cap agreed on D19, with per-type guidance where a type warrants shorter copy. [interpreted — the manual fixes one cap via test_banner_model_output_length_under_limit, not per-type budgets]
FR5 — Facts-only constraint restated per type. No invented details; copy states only what is present in the input for that event type.
FR6 — Rules encoded into the prompt. The per-type rules must be reflected in banner_model.py's prompt construction, not left as prose in a document the model never sees.
FR7 — Rules are testable. Each rule must be expressible as a check the eval suite can run — concretely, test_banner_model_matches_triggering_event_type and test_banner_model_output_length_under_limit must be able to assert against it.
FR8 — Aligned with Suraj's trigger rules. Every event type Suraj documents as firing must have a copy rule, and no copy rule may exist for an event type that never fires.
FR9 — Documented for the team. Suraj's trigger rules are explicitly "documented for team" on the same day; the copy rules are the companion half and must be written down for Jigyasu (display) and Sanskriti (eval authoring) to consume.
3. API Contract

No HTTP endpoint is authored on D20. The deliverable is a prompt-and-rules contract inside backend/app/notifications/banner_model.py, consuming the event payload agreed on D19 and producing the banner_text value that populates notifications.banner_text.

Per-type rule shape (the structure each of the four rules follows):

json
{
  "event_type": "approval_needed | task_completed | digest_ready | oauth_expiring",
  "permitted_input_fields": ["list of payload fields the copy may reference"],
  "must_state": ["facts the line is required to convey"],
  "must_not": ["recommend a decision", "invent details", "use alarming language"],
  "max_length": "int — characters, within the D19-agreed cap",
  "example_output": "string — a reference line for this type"
}

Illustrative per-type intent (to be finalised against Suraj's firing logic):

Event type	Copy must convey	Must not
approval_needed	What action is pending and which tool/target it affects	Recommend approve or reject; imply urgency beyond the facts
task_completed	What finished, factually	Imply a result that wasn't in the output
digest_ready	That a digest is available, and for which period	Summarise digest content it wasn't given
oauth_expiring	Which provider connection needs re-auth	Fail silently or bury the provider name (A3)

Producer/consumer boundary (unchanged from D19):

Suraj — trigger_rules.py supplies type, title, body, related_task_id and decides when a notification fires.
Ishani — banner_model.py supplies banner_text only, per these rules.
Jigyasu — banner_widget.dart renders it and handles tap-to-open; display logic consumes event types plus model output.

Generation path (§8.4): every call routes through the shared LLM router (Groq primary, Gemini fallback on 429/5xx) and logs to llm_usage_logs with request_type = 'banner'.

Eval path (§15.1): cases land in eval_cases under category = 'banner', replayed by Suraj's harness into eval_runs with suite_name = 'banner_model_eval'.

4. Constraints
Risk gate hard, explanation soft (§4.2). This is the governing principle for approval_needed copy: risk_rules decides whether an action needs approval; the copy only describes that decision and never influences it.
§9.3 guardrails carry over in full: state only facts present in the input, never invent details, never suggest the user should or shouldn't approve, non-alarming tone.
Advisory only. banner_text is a display field; nothing in approval_gate.py or any decision path reads it.
Paired with Suraj by design. The copy rules depend on his firing logic, documented the same day — they cannot be finalised independently of it.
Downstream consumers are same-week. Jigyasu's display logic (D20) and Sanskriti's banner-text eval cases (D21) both depend on these rules; late or vague rules block both.
Single shared length cap agreed on D19 with Jigyasu — per-type budgets may be tighter but never looser.
Free-tier reality (§2.3, §8.4). Rules must be satisfiable by a small, fast model under rate-limit pressure; copy requirements that demand long reasoning or many facts will fail in practice.
Gate 2 is four days out (19 Sep) — notification banner rendering must be working, and Sanskriti's banner eval cases delivered.
Definition of Done (§16.3): one paragraph of docs the same day; for a rules task, the written rules are the deliverable.
5. Edge Cases & Error Handling
Case	Expected Handling
Event payload missing a field a rule requires	Degrade to a shorter, still-accurate line rather than inventing the missing fact (FR5). [interpreted]
Model produces copy that reads as a recommendation on approval_needed	Rule violation — the single most important failure mode, given §4.2. Must be catchable in eval, not just in review.
Copy references a fact not present in the input	Rule violation, mirroring test_risk_explainer_no_false_claims_about_the_action applied to banner copy.
Copy doesn't match the type that triggered it	Caught by test_banner_model_matches_triggering_event_type; type from the trigger is authoritative, never inferred from the copy.
Output exceeds the per-type budget	Truncate or regenerate; must not ship over-length (test_banner_model_output_length_under_limit).
Suraj documents an event type with no copy rule	Gap must be closed the same day — FR8 requires one-to-one coverage.
A copy rule exists for an event type that never fires	Dead rule; remove rather than carry, or the eval suite tests behaviour that can't occur.
Two event types produce near-identical copy	Indicates the rules aren't actually differentiated; the point of per-type rules is that the types aren't interchangeable. [interpreted]
oauth_expiring copy that reads as informational rather than actionable	Risks the silent-failure mode A3 explicitly forbids — the provider needing re-auth must be clear.
Rule changes after D21 eval cases are authored	Coordinate with Sanskriti — her cases encode these rules, and a silent rule change turns passing cases into false greens. [interpreted]
6. Acceptance Criteria
AC1: A written copy rule exists for each of the four notifications.type values, each specifying permitted input fields, what the line must convey, tone bounds, and a length budget.
AC2: The rules are reflected in banner_model.py's prompt construction — the model is actually governed by them, not just documented alongside them.
AC3: approval_needed copy is demonstrably descriptive and never recommending, consistent with §4.2 and §9.3 Guardrail 2.
AC4: Every event type in Suraj's D20 trigger-rules document has exactly one corresponding copy rule, and vice versa.
AC5: Sample output per event type is generated and reviewed, showing each rule produces distinguishable, type-appropriate copy.
AC6: The rules are expressed concretely enough that Sanskriti can author D21 banner-text eval cases directly from them, without further clarification.
AC7: test_banner_model_output_length_under_limit and test_banner_model_matches_triggering_event_type pass against sample output for all four types.
AC8: Jigyasu's display logic can consume the rules as-is — no open questions blocking his D20 work at end of day.
AC9: Rules documented the same day per §16.3 and shared with the team, as the companion to Suraj's trigger-rules document.
