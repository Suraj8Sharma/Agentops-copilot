Day 27 Spec: Widget Tests for Plan View & Approval Screen (Safety-Critical)
Owner: Ishani (Frontend Design Lead & Trust Surfaces) · Date: Wed 23 Sep 2026 (D27, Week 5) · Source: AgentOps Implementation Manual, Sections 3, 6, 7, 8.1, 9, 10, 15, 16.3, 17, 18
Note on sources. Everything below comes from the manual except items marked (proposed). The manual names the Day 27 task ("Widget tests — Plan View, Approval Screen (safety-critical)") and three test names. The remaining test names, JSON payload shapes and thresholds are suggestions to confirm, not existing decisions.
1. Problem Statement
The Agent Plan View and the Approval Screen are the two screens a user's trust in the whole system rests on. The Plan View shows what the agent intends to do, and the Approval Screen is where a human decides whether a risk-flagged action may run. The manual treats a silent mis-render on either screen as a safety bug, not a cosmetic one: if the Plan View drops or reorders a step, or the Approval Screen shows the wrong action or lets a step through without a decision, the human-in-the-loop guarantee is broken at the last point where it can be enforced.
Both screens were built on D7–D8, wired to real data on D15–D16, and had their edge cases built on D23 (multi-step plans, rejected mid-flow). They have no automated tests yet. Day 27 adds the widget and golden tests that make the "never mis-render" bar enforceable in CI, and brings these two screens to the 100% coverage required by Acceptance Criterion A7.
Where Day 27 sits:
Item
Detail
Depends on
D25: widget-test framework and golden-screen baseline; D26: widget tests for Onboarding, Home and Composer (patterns and mocks reused); D15/D16/D23: Plan View and Approval Screen wired to real data, with edge cases built
Feeds into
D28 (Activity Log tests), D31 (UI-side support for the approval-gate bypass e2e test), D33 (no cross-user data renders), D35 (full frontend regression), Gate 3
Screens in scope
plan_view_screen.dart, approval_screen.dart (plus the widgets they compose)
Out of scope today
Backend approval-gate tests and the adversarial bypass test (Suraj, D31), explanation-LLM quality evals (test_risk_explainer_*, Suraj's eval harness), Activity Log (D28), OAuth Connections, Trust Dashboard
2. Functional Requirements
The requirements describe what the tests must verify. Test names marked (proposed) follow the manual's test_<screen>_<behaviour> convention. The three names without that mark come straight from Section 15.2.
2.1 Agent Plan View (GET /tasks/{id}/plan)
ID
Requirement
Test
FR-PV-1
All steps of the active plan render, in step_index order, with none missing or duplicated.
test_plan_view_renders_all_steps_in_order
FR-PV-2
Each step shows its tool (tool_name, e.g. calendar.create_event), its provider (mcp_server) and its key input_params in a readable form.
test_plan_view_step_shows_tool_provider_and_params (proposed)
FR-PV-3
Each step shows its risk_tier (low, medium, high) and whether approval is required, and these indicators never rely on colour alone.
test_plan_view_shows_risk_tier_and_approval_flag (proposed)
FR-PV-4
Each step shows its status (pending, awaiting_approval, approved, rejected, executing, done, failed) with a distinct, accurate presentation per status.
test_plan_view_renders_each_step_status (proposed)
FR-PV-5
A step in awaiting_approval offers a path to the Approval Screen.
test_plan_view_awaiting_step_links_to_approval (proposed)
FR-PV-6
A completed step shows its result summary; a failed step shows a clear failure state.
test_plan_view_done_and_failed_step_states (proposed)
FR-PV-7
A golden (pixel-reference) test locks the rendering of a representative multi-step plan with mixed risk tiers.
test_plan_view_golden_mixed_risk_plan (proposed)
2.2 Approval Screen (GET /approvals/pending, POST /approvals/{step_id})
ID
Requirement
Test
FR-AP-1
The screen shows the risk-flagged action (what will run and on which provider, with its parameters) together with the plain-English explanation.
test_approval_screen_renders_risk_explanation (golden test)
FR-AP-2
The screen never auto-approves: rendering it, leaving it open, navigating away or losing focus never sends an approved decision. Only an explicit user tap on Approve does.
test_approval_screen_never_auto_approves
FR-AP-3
Tapping Approve sends exactly one POST /approvals/{step_id} with decision: approved.
test_approval_screen_approve_sends_single_approved_decision (proposed)
FR-AP-4
Tapping Reject sends exactly one POST /approvals/{step_id} with decision: rejected.
test_approval_screen_reject_sends_single_rejected_decision (proposed)
FR-AP-5
The risk tier and rationale for the flagged action are visible before the user can decide.
test_approval_screen_shows_risk_tier_before_decision (proposed)
FR-AP-6
The explanation is presented as description only: the screen shows no "recommended" or pre-selected choice, and Approve and Reject have equal prominence.
test_approval_screen_has_no_preselected_or_recommended_choice (proposed)
FR-AP-7
After a decision, the screen reflects the outcome and returns the user to the correct place (Plan View or Home); the decision controls cannot be used a second time.
test_approval_screen_after_decision_disables_controls_and_navigates (proposed)
FR-AP-8
With several pending approvals, each is shown for its own step and a decision applies only to the step shown.
test_approval_screen_multiple_pending_targets_correct_step (proposed)
FR-AP-9
A golden test locks the layout of the Approval Screen for a high-risk action (for example gmail.send_message).
covered by test_approval_screen_renders_risk_explanation
2.3 Cross-cutting
ID
Requirement
FR-X-1
All tests run under flutter test with the backend replaced by mocks or fakes. No test calls the real backend.
FR-X-2
Files are mobile/test/screens/plan_view_test.dart and mobile/test/screens/approval_screen_test.dart, reusing the D25 harness and golden baseline.
FR-X-3
flutter test --coverage reports 100% line coverage for plan_view_screen.dart and approval_screen.dart, and the result is checked in CI (proposed: a coverage-threshold step).
FR-X-4
Tests run automatically in CI on every PR.
3. API Contract
The widget tests mock the backend, so this contract defines exactly what the mocks return. Endpoint paths, auth rules and table columns come from Sections 7 and 10. The JSON shapes are not given in the manual and are derived from the task_plans, plan_steps and approvals tables, so they are marked (proposed). Confirm them with Suraj before writing the mocks.
3.1 Endpoints used by these screens
Screen
Method
Path
Auth
Purpose
Plan View
GET
/tasks/{id}/plan
JWT
Full task_plans + plan_steps for the Agent Plan View
Plan View
GET
/tasks/{id}
JWT
Task detail including its plan and step statuses (used for task-level status)
Approval Screen
GET
/approvals/pending
JWT
List steps currently awaiting this user's decision
Approval Screen
POST
/approvals/{step_id}
JWT
Record an approve/reject decision; resumes the LangGraph checkpoint
All four routes sit behind the JWT-verification dependency (Section 5.1). The app sends the Supabase access token as a bearer token.
3.2 GET /tasks/{id}/plan (response shape proposed)
{
  "plan": {
    "id": "uuid",
    "task_id": "uuid",
    "status": "active",
    "planner_version": "v1"
  },
  "steps": [
    {
      "id": "uuid",
      "step_index": 0,
      "tool_name": "calendar.create_event",
      "mcp_server": "calendar",
      "input_params": { "title": "Call with Prof. Rao", "start": "2026-09-24T15:00:00+05:30" },
      "risk_tier": "medium",
      "requires_approval": false,
      "status": "done",
      "output": { "event_id": "abc123" }
    },
    {
      "id": "uuid",
      "step_index": 1,
      "tool_name": "gmail.send_message",
      "mcp_server": "gmail",
      "input_params": { "to": ["professor.rao@university.edu"], "subject": "Agenda for Thursday's call" },
      "risk_tier": "high",
      "requires_approval": true,
      "status": "awaiting_approval",
      "output": null
    }
  ]
}
• plan.status is draft, active or superseded. Re-planning creates a new task_plans row rather than overwriting, so the screen must show the active plan only.
• risk_tier is low, medium or high. status is one of the seven step statuses in FR-PV-4.
• The example mirrors the manual's demo script: create a calendar event, then email the agenda.
3.3 GET /approvals/pending (response shape proposed)
[
  {
    "step_id": "uuid",
    "task_id": "uuid",
    "tool_name": "gmail.send_message",
    "mcp_server": "gmail",
    "input_params": { "to": ["professor.rao@university.edu"], "subject": "Agenda for Thursday's call" },
    "risk_tier": "high",
    "rationale": "Irreversible the moment it is sent",
    "explanation_text": "This will send an email to professor.rao@university.edu with the subject 'Agenda for Thursday's call'.",
    "surfaced_at": "2026-09-23T10:02:11Z"
  }
]
explanation_text is advisory display copy written by the explanation LLM (Section 9.3). It is stored in approvals.explanation_text; nothing in the decision logic reads it.
3.4 POST /approvals/{step_id} (request and response shapes proposed)
Request:
{ "decision": "approved" }
decision is approved or rejected. Response (200):
{ "step_id": "uuid", "decision": "approved", "decided_at": "2026-09-23T10:02:40Z" }
The approvals table also stores response_time_ms (time from surfaced to decided, feeding the Trust Dashboard). The manual does not say whether the client sends it or the server computes it from surfaced_at: confirm with Suraj, and if the client sends it, add a test that the value is sent.
3.5 Error responses the mocks must cover (proposed shapes, standard HTTP semantics)
Status
Meaning
Expected UI behaviour
401
Expired or invalid JWT
Silent refresh attempt, then hand-off to Sign In; no decision is assumed to have been recorded
404
Step or plan no longer exists (e.g. task cancelled or deleted)
Clear "no longer available" state; controls removed
409
Step already decided, or plan superseded
Screen refreshes to current state and tells the user; never shows a stale Approve button
422
Invalid decision value
Treated as an error; no optimistic success shown
5xx or timeout
Backend error or Render cold start
Explicit loading, then error with retry; the step is shown as still awaiting a decision, never as approved
4. Constraints
Constraint
Source
Impact on Day 27
Approval Screen and Plan View must never mis-render
Sections 3, 15
Tests assert content, order and state exactly, not just that a widget exists
Golden-file (pixel-reference) tests are required for both screens
Section 15.2
Goldens are generated on a fixed device size, theme, font and text scale so they are deterministic across machines and CI. Golden updates only happen intentionally, in a reviewed PR
Coverage must be 100% on these two screens (80% overall)
A7, Section 15.2
Every branch (each status, each risk tier, each error state) needs a test. Coverage is measured with flutter test --coverage and checked for these two files
Fail-closed principle: an unrecognised action is never treated as safe
Section 4.2, 9.2
If the UI receives an unknown risk_tier or status, it presents the step as high-risk / needing a decision, never as safe or approved
"Risk gate hard, explanation soft"
Section 4.2, 9.3
The UI must not let the explanation text change what is allowed or pre-select a decision. The structured fields (tool_name, input_params, risk_tier) are always shown alongside the explanation
Explanation tone is non-alarming and describes without recommending
Section 9.3
The screen shows no recommendation copy or default choice of its own
risk_rules is never written by the app
Section 9.1
The client only displays risk data it receives and has no code path to alter it
No cross-user data may ever render
Section 3, D33
Mocks contain only the current user's rows. A test confirms nothing from another user's data is shown if a response mistakenly includes it (proposed)
A decision is irreversible once the gate resumes
Section 9
After a decision, controls are disabled. Double taps send one request
Definition of Done: merged via reviewed PR, tests pass, linters clean, fail-closed behaviour verified, one paragraph of docs the same day
Section 16.3
PR goes to Suraj (sole merger). Fail-closed UI behaviour is explicitly tested
CI blocks merge on any failing test or lint error
A9
Goldens and tests must be stable and non-flaky on CI, not just locally
Saturday is review + PR-merge day
Section 13
Work may merge on D27, or at the latest on D30 (Week-5 merge), in time for Gate 3 on 26 Sep
Free-tier cold starts and rate limits
Section 2.3
Explicit loading states are asserted. A rate-limited or slow backend never causes a spinner that looks like approval
5. Edge Cases & Error Handling
5.1 Plan View
Case
Expected behaviour
Covered by
Plan with one step
Renders correctly with no ordering UI glitches
test_plan_view_single_step_plan (proposed)
Plan with many steps (10+)
All steps render in order; list scrolls; none dropped
test_plan_view_many_steps_all_rendered_in_order (proposed)
Steps arrive out of order in the response
Displayed by step_index, not by array order
test_plan_view_sorts_by_step_index (proposed)
Mixed-risk plan (low steps, then a paused high-risk step)
Low-risk steps shown as running or done; only the high-risk step shows awaiting_approval; later independent low-risk steps are not shown as blocked
test_plan_view_mixed_risk_ordering (proposed)
Step rejected mid-flow
Rejected step clearly marked; subsequent steps show the halted or skipped state the backend reports, and the task is not shown as completed
test_plan_view_rejected_step_midflow (proposed)
Plan superseded by re-planning
Only the active plan is shown; a stale plan is never displayed as current
test_plan_view_ignores_superseded_plan (proposed)
Empty or draft plan (still planning)
Explicit "planning" state, not a blank screen
test_plan_view_planning_state (proposed)
Unknown risk_tier or status
Treated cautiously (shown as high-risk / needs attention), no crash
test_plan_view_unknown_values_fail_closed (proposed)
Long or nested input_params
Truncated or expandable without overflow, and the full value remains reachable
test_plan_view_long_params_no_overflow (proposed)
Fetch fails or times out
Error state with retry; no stale steps presented as current
test_plan_view_error_state_retry (proposed)
5.2 Approval Screen
Case
Expected behaviour
Covered by
Screen opened and left idle, backgrounded, or navigated away
No decision is sent
FR-AP-2
Approve double-tapped
Exactly one request
test_approval_screen_double_tap_approve_sends_once (proposed)
Approve then Reject in quick succession
Only the first decision is sent; controls lock immediately
test_approval_screen_locks_controls_after_first_tap (proposed)
POST fails (5xx, timeout, offline)
Error shown, step still shown as awaiting a decision, retry allowed; never shown as approved
test_approval_screen_post_failure_not_shown_as_approved (proposed)
409 (already decided elsewhere) or step superseded
Screen refreshes and explains; no stale actionable controls
test_approval_screen_409_refreshes_state (proposed)
401 during decision
Auth hand-off; no assumption a decision was recorded
test_approval_screen_401_no_assumed_decision (proposed)
Explanation missing, empty or still loading
Structured action details are still shown. The user can see what will run; approval is not offered without them (proposed: Approve disabled until the action details are visible)
test_approval_screen_missing_explanation_still_shows_action (proposed)
Explanation very long or contains unusual characters
Truncated cleanly or scrollable, no overflow, no markup injection
test_approval_screen_long_explanation_no_overflow (proposed)
Explanation text disagrees with structured params
Structured params are displayed as the source of truth next to the explanation
test_approval_screen_shows_structured_params_alongside_explanation (proposed)
Unknown risk_tier
Presented as high-risk (fail-closed)
test_approval_screen_unknown_tier_treated_as_high (proposed)
No pending approvals
Clear empty state, no phantom Approve button
test_approval_screen_no_pending_empty_state (proposed)
App closed mid-approval and reopened
The pending step is shown again and still awaits the user's decision (the backend resumes from its checkpoint)
test_approval_screen_pending_step_survives_reopen (proposed)
Multi-step plan with multiple pending approvals
Each decision targets the correct step_id
FR-AP-8
Small screen / large text scale
Approve and Reject remain visible and tappable; the risk information is not pushed off-screen
test_approval_screen_small_screen_large_text (proposed)
5.3 Test-suite hygiene
• Goldens must be deterministic: fixed device size, pixel ratio, theme and bundled fonts, with no timestamps or animations in the frame. Regenerate goldens only on purpose, with the diff reviewed.
• Assert absence as well as presence: never_auto_approves verifies that no POST was made, by checking the mock's recorded calls.
• No real network: an unmocked call fails the test.
• Bugs found while testing: fix them in the same PR or log them with severity. P0/P1 bugs on core screens must be closed by Gate 4 on 3 Oct. Any bug in how these two screens represent risk or decisions is treated as P0.
6. Acceptance Criteria
6.1 Day 27 completion criteria
ID
Criterion
How verified
D27-1
plan_view_test.dart and approval_screen_test.dart exist under mobile/test/screens/.
File review in PR
D27-2
The three manual-named tests exist and pass: test_plan_view_renders_all_steps_in_order, test_approval_screen_renders_risk_explanation (golden), test_approval_screen_never_auto_approves.
flutter test output
D27-3
Every FR in Section 2 has at least one passing test (FR-PV-1 to 7, FR-AP-1 to 9).
Test output mapped to FR IDs
D27-4
Both golden files are committed, deterministic, and match on a clean CI run.
CI + golden diff review
D27-5
flutter test --coverage reports 100% line coverage on plan_view_screen.dart and approval_screen.dart.
Coverage report attached to PR
D27-6
The edge cases in Section 5 are covered, or any exception is listed in the PR description with a reason.
PR checklist
D27-7
Fail-closed UI behaviour is verified: unknown tier or status is treated as high-risk, failed POST is never shown as approved, no decision is sent without an explicit tap.
Named tests above
D27-8
No test calls the real backend. Mock payloads match the contract in Section 3, confirmed with Suraj or flagged as assumptions.
Code review, PR comment
D27-9
Linters are clean, CI is green, and the PR is opened for Suraj's review with no direct push to main.
PR and CI status
D27-10
A short docs paragraph on how to run and update these tests, including how to regenerate goldens, is added the same day.
Docs diff in PR
D27-11
No flaky failures across 3 consecutive CI runs (proposed threshold).
CI history
6.2 Project-level criteria this work supports
ID
How Day 27 contributes
A7 (widget-test coverage ≥ 80% of screens overall, 100% on Approval Screen and Plan View)
Delivers the 100% requirement for both named screens
A2 (every high-risk action blocked pending approval in 100% of bypass-test runs)
Provides the UI-side evidence for D31: the Approval Screen never submits an approval on its own, and the Plan View never shows an unapproved high-risk step as approved or done
G2 (a user can always see what the agent is about to do and why, before it happens)
Locks the Plan View and Approval Screen so that goal cannot silently regress
A9 (CI blocks merge on any failing test or lint error)
Tests and goldens run in CI and must be stable enough not to cause spurious blocks
Gate 3 ("Widget tests written for every screen")
Closes the two highest-stakes screens owed by Ishani; D26 covered three, D28 covers Activity Log
6.3 End-of-day checklist
[ ] Both test files written and passing locally
[ ] Golden files generated, reviewed and committed
[ ] 100% coverage confirmed on both screen files
[ ] Mock payloads confirmed with Suraj (or assumptions noted)
[ ] CI green on the PR; PR opened for Suraj's review
[ ] README or module doc paragraph added (including golden regeneration steps)
[ ] Bugs found are fixed or logged with severity
[ ] Handoff note ready for D28 (Activity Log tests) and D31 (UI-side approval-gate bypass support)