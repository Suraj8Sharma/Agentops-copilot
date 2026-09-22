Spec: Approval Screen Edge Cases — Multi-Step, Rejected Mid-Flow

Owner: Ishani · Day: D23, Fri 19 Sep · Week 4 close (14–19 Sep)

Derived from the AgentOps Implementation Manual (§7 Data Model — approvals/plan_steps, §8.1 LangGraph State Management/Node Sequence/Retries & Multi-Step Ordering, §9 Approval Gate, §10 API Reference, §14 Day Plan D16/D23, §15.2/§15.3 Testing, §16.3 Definition of Done, §17 Gate 2). Points not stated verbatim are marked [interpreted].

1. Problem Statement

The Approval Screen was wired to real approvals on D16: a single pending step, rendered, decided, resolved. That covers the simplest case — one plan, one approval, one decision. It does not cover what the LangGraph node sequence actually allows: a mixed-risk plan where several steps are in flight at once, a rejection that has to propagate correctly depending on what depends on it, and a decision that arrives after the app was closed and reopened mid-approval.

D23 closes that gap, on the last day of Week 4 — the day before Gate 2. The planner's own node sequence draws the exact fork this task has to render correctly: risk_tag routes a step either straight to execute or through approval_gate, and on rejection the graph goes to log → skip_step / halt_task — not always halt. Whether a rejection skips just that step or halts the whole task depends on whether later steps depend on the rejected one's output. A mixed-risk multi-step plan (the manual's own example: create an event, then email an attendee) executes low-risk steps as they become ready and pauses only the specific high-risk step — later low-risk steps that don't depend on it are not blocked behind it. The Approval Screen, as of D16, has never had to represent any of that.

This also has to hold up against interruption: the checkpointer persists graph state keyed by thread_id = task_id, so a task mid-approval when the app is closed must resume exactly where it left off — not re-plan from scratch — when the user reopens it.

Explicitly not in scope for D23: the LangGraph node/checkpointer logic itself (already implemented, Suraj); the single-approval happy path (Ishani, D16, already done); the Notifications-screen payload contract (Jigyasu with Suraj, same day, separate task); OAuth edge cases (Ishani, D22, already done).

2. Functional Requirements
FR1 — Multiple pending approvals render correctly at once. When a mixed-risk plan has more than one step flagged for approval, or one pending approval alongside steps already executing, the screen must represent all of it without collapsing to a single-approval assumption.
FR2 — Low-risk steps are shown progressing independently of a paused high-risk step. Per §8.1: steps that don't depend on the paused step's output continue; the screen must not visually imply the whole task is frozen when only one step is gated.
FR3 — Rejecting a step halts or skips correctly, and the screen reflects which. A rejection routes to skip_step (if nothing downstream depends on it) or halt_task (if it does); the Approval Screen and the task's overall status must show the outcome that actually occurred, not a generic "rejected."
FR4 — Rejected step has no side effects. Consistent with test_rejected_approval_halts_task_with_no_side_effects — nothing the rejected step would have done should appear as having happened.
FR5 — Mid-flow rejection on a multi-step plan doesn't corrupt already-completed steps. Steps executed before the rejection keep their completed state and output; rejection only affects the rejected step and whatever depends on it.
FR6 — Resume after app closed mid-approval. Reopening the app on a task with a pending approval must show the same pending state, not a re-planned or reset one — the checkpointer already guarantees this server-side; the screen must render it correctly.
FR7 — Ordering is always correct for mixed-risk plans. Consistent with test_mixed_risk_multi_step_plan_orders_correctly — step order on screen must match plan_steps.step_index, regardless of which steps are auto-executing versus gated.
FR8 — Never auto-approves. Carries forward from D18/D16 — no client-side path, including these new multi-step and resume flows, may approve a step without an explicit user decision (test_approval_screen_never_auto_approves).
3. API Contract

No new endpoints — D23 is UI handling for state combinations the existing contract already allows.

Method	Path	Auth	Purpose
GET	/approvals/pending	JWT	List steps awaiting this user's decision — may now return more than one row for a single task
POST	/approvals/{step_id}	JWT	Record approve/reject; resumes the LangGraph checkpoint for that step
GET	/tasks/{id}/plan	JWT	Full plan with per-step status, for rendering multi-step state alongside pending approvals

approvals fields the screen must use correctly (§7):

Column	Notes
step_id	FK plan_steps(id) — ties the decision to a specific step, not the whole task
decision	approved | rejected
explanation_text	Advisory copy only (§9.3) — display, never a decision input
response_time_ms	Time from surfaced to decided — feeds the Trust Dashboard

plan_steps.status values the screen must render simultaneously across a multi-step plan: pending | awaiting_approval | approved | rejected | executing | done | failed.

Graph-side outcome on rejection (not an API field — inferred client-side from resulting step/task status): skip_step (only that step is marked rejected, plan continues) vs. halt_task (task moves to status = failed/halted with no further steps executing). [interpreted — the manual states this branch exists in the graph; it does not specify how the client distinguishes the two outcomes from the API response. Confirm with Suraj whether this is a distinct field or inferred from subsequent step statuses.]

4. Constraints
The fork is graph-level and cannot be influenced by the client or a prompt. §8.1 calls this out directly: risk_tag's routing is "the only branch in the whole planner that a prompt cannot influence." The Approval Screen must respect that boundary — it renders the outcome, it never causes it.
Idempotency is already handled server-side. Each MCP call carries an idempotency key derived from plan_id + step_index, so a retried call can't double-execute — the screen doesn't need its own guard against double-submission causing a double action, but should still guard against double-submitting the same decision UX-wise.
Checkpointer guarantees resume, not the client. The client's job is to render the resumed state correctly, not to reconstruct it — state is already correctly persisted server-side keyed by thread_id = task_id.
Advisory/decision separation still applies (§9.3). explanation_text shown alongside a multi-step approval remains descriptive only, same as the single-approval case.
Coverage requirement is strict here. Approval Screen is one of two screens (with Plan View) required at 100% widget-test coverage, plus golden-file tests — this is explicitly the safety-critical UI in the app, and multi-step/rejection paths are exactly the kind of case that tier exists for.
Last day before Gate 2 (19 Sep). No slack in the schedule to defer this — Gate 2 requires the core loop working correctly, and multi-step/rejected-mid-flow is squarely inside "correctly," not an edge polish item.
Definition of Done (§16.3): reviewed PR, passing tests, clean linters, fail-closed behaviour verified — directly relevant, since a rejection that fails to actually halt dependent steps is a fail-closed violation, not just a UI bug.
5. Edge Cases & Error Handling
Case	Expected Handling
Mixed-risk plan: one high-risk step pending, later low-risk steps independent of it	Low-risk steps shown executing/completing; the pending approval doesn't visually block them (§8.1, FR2).
Mixed-risk plan: low-risk step depends on output of a still-pending high-risk step	That dependent step correctly shows as blocked/pending, not executing — ordering must be right (test_mixed_risk_multi_step_plan_orders_correctly).
Rejection with no downstream dependents	skip_step — only that step shows rejected; the rest of the plan proceeds and completes normally.
Rejection with downstream dependents	halt_task — task-level status reflects the halt; steps that would have depended on the rejected step never execute.
Rejected step already had partial output from a prior attempt/retry	No side effects surface from it regardless (test_rejected_approval_halts_task_with_no_side_effects) — partial state must not leak into the UI as if it happened.
App closed while multiple approvals are pending, reopened later	All pending approvals are still surfaced correctly, matching plan_steps state — not just the first one (test_task_resumes_after_app_closed_mid_approval, extended to the multi-approval case).
Two approvals on the same task decided out of order	Each decision only affects its own step and whatever depends on it; deciding step 3 before step 1 (if independent) must not corrupt step 1's still-pending state. [interpreted]
MCP call retried after a transient failure on an approved step	Idempotency key prevents duplication server-side; screen should not show a duplicate execution or double-approval prompt.
A step fails after 3 retry attempts (unrelated to approval)	Task halts with a clear error surfaced to the Activity Log — Approval Screen must not conflate this failure with a rejection; they are different outcomes.
User attempts to approve a step twice (double-tap, slow network)	Must not create two approvals rows or double-resume the checkpoint — same idempotency principle applied client-side. [interpreted]
6. Acceptance Criteria
AC1: A mixed-risk multi-step plan (create-event-then-email-attendee style) renders correctly: low-risk steps progress while only the high-risk step pauses, in correct order.
AC2: test_mixed_risk_multi_step_plan_orders_correctly passes.
AC3: test_rejected_approval_halts_task_with_no_side_effects passes for both the skip_step and halt_task outcomes, verified separately.
AC4: A rejection with no downstream dependents is shown as a skipped step with the rest of the plan completing; a rejection with downstream dependents is shown as a halted task — the two are visually and functionally distinct on screen.
AC5: test_task_resumes_after_app_closed_mid_approval passes with more than one pending approval outstanding at close time.
AC6: test_approval_screen_never_auto_approves continues to pass across all new multi-step and resume paths.
AC7: Approval Screen remains at 100% widget-test coverage including golden-file tests, extended to cover the new multi-step and rejection-branch states.
AC8: Definition of Done met per §16.3, PR reviewed and merge-ready ahead of Gate 2.
AC9: Feeds Gate 2 (19 Sep) as part of the core loop being confirmed correct, not just wired.