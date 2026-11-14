Day 31 Spec: UI-Side Support for the Approval-Gate Bypass & Agent-Loop E2E Tests
Owner: Ishani (Frontend Design Lead & Trust Surfaces), supporting Suraj · Date: Mon 28 Sep 2026 (D31, first day of Week 6) · Source: AgentOps Implementation Manual, Sections 1.3, 4.2, 5, 8.1, 8.2, 9, 10, 15, 16.3, 17, 18, 19 and the Section 14 day plan (D31)
Note on sources. Everything below comes from the manual except items marked (proposed). The manual names Ishani's Day 31 task ("Support e2e test from UI side (approval-gate bypass)"), lists the backend test names, and fixes the acceptance bar (A2). It does not say what tooling the UI side uses, what the test environment looks like, or the exact error codes for blocked attempts. Those are suggestions to confirm with Suraj, not existing decisions.
Role boundary. Suraj owns the approval-gate bypass adversarial test and the agent-loop e2e test (pytest + LangGraph harness). Ishani supports from the UI side: she drives and observes the real screens during those scenarios, confirms the UI never presents a blocked action as approved or done, and reports any gap at once. She does not change gate logic (approval_gate.py) or risk_rules.
1. Problem Statement
The approval gate is, in the manual's words, "the single most safety-critical subsystem in AgentOps": no action tagged high-risk may execute without an explicit, logged, human approval, 100% of the time, including under adversarial testing (Acceptance A2). Suraj's backend test attacks the gate directly through every code path the team can think of (direct API calls, replayed requests, malformed plan JSON, missing risk_rules rows) and asserts every attempt is blocked.
That backend test proves the gate holds. It does not prove the user can see that it holds. A user's trust depends on the Plan View, Approval Screen and Activity Log telling the truth during a bypass attempt: a blocked high-risk step must look blocked, a rejected step must look rejected, and nothing may appear sent or approved that was not. A UI that misreports a correctly blocked action is a safety bug even when the backend is right (Goal G2: "A user can always see what the agent is about to do and why, before it happens").
Day 31 is also the first day of Week 6 (integration, load and security testing), the week the manual keeps free of new features. The day's work is therefore verification only: run the full flow through the real UI, run the bypass scenarios while watching the UI, and record evidence.
A single failing bypass run blocks the release candidate at Gate 4, with no override (Sections 15, 17, 19). Any hole Ishani sees from the UI side is a P0.
Where Day 31 sits:
Item
Detail
Depends on
D17: approval-gate logic and approvals endpoint; D16: Approval Screen wired; D23: Approval Screen edge cases; D27: Plan View and Approval Screen widget tests (100% coverage); D28: Activity Log tests; D30: Week-5 frontend merged; Suraj's D31 tests (test_approval_gate.py, test_agent_e2e.py)
Feeds into
D32 (load test: UI observes behaviour under load), D33 (security/RLS audit and UI audit), D35 (full regression), Gate 4, D39 demo rehearsal (Section 1.3 demo script)
Screens involved
Home, Task Composer, Plan View, Approval Screen, Activity Log (plus Notifications for the approval push)
Out of scope today
Writing or changing gate logic, backend adversarial attempts themselves (Suraj), voice flow e2e (Jigyasu supports test_e2e_voice_task_completes_full_loop), load and RLS audits (D32–D33), new features
2. Functional Requirements
The backend tests below are named in Section 15.4. Ishani's UI-side requirement for each is what she must observe and confirm.
2.1 Backend tests Ishani supports and the UI-side check for each
ID
Backend test (Suraj, Section 15.4)
UI-side requirement (Ishani)
FR-E2E-1
test_e2e_text_task_completes_full_loop
Through the real UI: submit the demo task (calendar event + email). Plan View shows two steps in order; the low-risk calendar step auto-executes to done; the high-risk email step shows awaiting_approval; the Approval Screen shows the action and explanation; after Approve the task completes; Plan View shows both steps done; Activity Log shows both steps with payloads and timing
FR-E2E-2
test_low_risk_action_auto_executes_without_approval
A low-risk-only task (for example calendar.list_events) completes with no Approval Screen shown and no pending approval created
FR-E2E-3
test_high_risk_action_blocks_pending_approval
With no decision made, the high-risk step stays awaiting_approval indefinitely, the task stays awaiting_approval, and the external side effect (the email) has not happened (checked against the mock/sandbox, Section 3.4)
FR-E2E-4
test_rejected_approval_halts_task_with_no_side_effects
After Reject, Plan View marks the step rejected, the task is not shown as completed, subsequent dependent steps are not shown as run, and the mock/sandbox records no side effect
FR-E2E-5
test_mixed_risk_multi_step_plan_orders_correctly
In a plan with low-risk steps and one high-risk step, low-risk steps run as they become ready and only the high-risk step is paused; the UI shows this ordering accurately
FR-E2E-6
test_task_resumes_after_app_closed_mid_approval
Close (kill) the app while a step awaits approval, reopen it, and confirm the pending approval is shown again and the task resumes from where it paused after a decision
FR-E2E-7
test_approval_gate_bypass_attempt_always_fails (A2)
While Suraj's attempts run, confirm in the UI that no blocked high-risk step ever appears as approved, executing or done, and that no email/event exists in the mock for it (see Section 2.2)
FR-E2E-8
test_e2e_voice_task_completes_full_loop
Supported by Jigyasu, not Ishani. Ishani only confirms that the voice task appears correctly in Home, Plan View and Approval Screen
2.2 UI-side bypass scenarios Ishani drives and observes (proposed set; Suraj adds the backend-level attempts)
ID
Scenario
Expected result in the UI and system
FR-BP-1
Approve button tapped twice quickly, or the same approval replayed
Exactly one decision is recorded, exactly one action executes (idempotency key plan_id:step_index), and the screen locks after the first tap
FR-BP-2
Open the Approval Screen for a step that is already decided, rejected, superseded or cancelled
The screen refreshes to the real state and offers no actionable Approve control
FR-BP-3
Approve after the task was rejected, cancelled or halted
Refused; the step stays in its terminal state; nothing executes
FR-BP-4
Decision for a step belonging to another user (replayed or forged step_id)
Refused by RLS/authorisation; no data from that step renders; nothing executes
FR-BP-5
Unknown or missing risk_tier / unlisted action_type for a step
Treated as high-risk and requiring approval (fail-closed, Section 9.2); the UI shows it as needing a decision, never as safe
FR-BP-6
Malformed or tampered plan data reaching the client
The UI does not crash, does not mark any step as approved, and surfaces an error state
FR-BP-7
Leave the Approval Screen open, background the app, or navigate away without deciding
No decision is sent; the step remains pending
FR-BP-8
Notification approval_needed is tapped after the step was already decided
Opens the current state of that step, not a stale approval prompt
FR-BP-9
Token expiry mid-approval
Silent refresh, then retry; if refresh fails, the user is taken to sign-in and no decision is assumed recorded
FR-BP-10
Approve tapped but the network drops before the response arrives
The UI treats the outcome as unknown, re-fetches state, and does not show "approved" or "sent" until the server confirms
2.3 Audit-trail check (auditability by construction, Section 4.2)
ID
Requirement
FR-AU-1
In the Activity Log for the demo task, approval_requested appears before the high-risk tool_called, and approval_decided (approved) appears before it, since logs are written before any external effect
FR-AU-2
For a rejected step, the Activity Log shows approval_requested and approval_decided (rejected) and no tool_called for that step
FR-AU-3
For a blocked bypass attempt, no tool_called entry for the high-risk step exists
2.4 Evidence and reporting
ID
Requirement
FR-EV-1
Each scenario run is recorded with: date and time, build, test user, scenario ID, result, and evidence (screen recording or screenshots of Plan View, Approval Screen and Activity Log, plus the mock/sandbox call log)
FR-EV-2
Any deviation, however small (a step shown with the wrong status, an Approve button still active, an email in the sandbox), is reported to Suraj immediately and logged as P0
FR-EV-3
Results feed the report appendix (D38–D40) and the Gate 4 checklist
3. API Contract
The screens use only endpoints already defined in Section 10. This section lists them with the behaviour the e2e and bypass scenarios depend on. Request and response JSON shapes are the (proposed) ones from the Day 27 and Day 28 specs and should be confirmed with Suraj. Error codes for blocked attempts are (proposed), since the manual says "blocked" without naming codes.
3.1 Endpoints exercised
Method
Path
Auth
Role in Day 31
POST
/tasks
JWT
Submit the demo task; kicks off the LangGraph run
GET
/tasks, /tasks/{id}
JWT
Task status shown in Home and detail
GET
/tasks/{id}/plan
JWT
Plan View: steps, risk_tier, requires_approval, status
GET
/approvals/pending
JWT
Approval Screen: steps awaiting this user's decision
POST
/approvals/{step_id}
JWT
Record approve or reject; resumes the LangGraph checkpoint
GET
/activity-log
JWT
Audit trail verification (FR-AU-1 to FR-AU-3)
GET
/notifications
JWT
approval_needed notification and its tap-through
All routes sit behind the JWT-verification dependency (Section 5.1).
3.2 Expected behaviour the tests rely on (from the manual)
Rule
Source
No code path calls execute() on a high-risk step without passing gate() and receiving an explicit approved decision recorded in approvals
Section 9.2
A step with no matching risk_rules row defaults to high / requires_approval = true
Sections 4.2, 9.2
The gate is a plain table lookup, with no LLM involved
Section 9.2
The graph halts at approval_gate with a checkpoint saved; POST /approvals/{step_id} resumes it
Sections 8.1, 10
A rejected step logs and then skips or halts the task
Section 8.1
Each MCP call carries idempotency_key = plan_id:step_index, so a retry cannot double-create or double-send
Sections 8.1, 8.2
Every node transition, tool call and approval decision writes to execution_logs before it has any external effect
Section 4.2
explanation_text is display-only; nothing in the gate reads it
Section 9.3
3.3 Expected responses to bypass attempts (proposed codes)
Attempt
Expected API result
Expected UI
Approve a step that is not awaiting_approval
409
Screen refreshes to current state; no stale controls
Approve a step of another user
403 or 404 (no existence leak)
Generic "not available"; no foreign data
Replay of an already-applied approval
409 or idempotent 200 with no second execution
One effect only; no duplicate entries
Approve with an invalid body or decision value
422
Error shown; nothing assumed approved
Call with expired or tampered JWT
401
Silent refresh, then sign-in; no decision assumed
Plan with an unlisted action_type
Step created with high / requires_approval = true
Shown as needing approval
3.4 Test data and environment (proposed; confirm with Suraj)
Section 15 says MCP tests run against sandbox or mock servers. The UI-side scenarios need the same, so that no real email or calendar event is ever sent.
Need
Proposal
Test user(s)
At least two dedicated test users (needed for FR-BP-4), cleaned up afterwards through account deletion
MCP backends
Mock/sandbox Calendar and Gmail that record every call, so "no side effect" is checkable. Real Google accounts are not used for bypass scenarios
Seeded risk_rules
Production seed set (Section 9.1): calendar.list_events low; calendar.create_event medium, no approval; gmail.create_draft low; gmail.send_message high, approval required; plus one deliberately unlisted action for the fail-closed case
Planner determinism
Bypass scenarios must not depend on LLM output: use a stubbed or fixed plan for them. Keep one live-LLM run for the happy-path demo script only
Build under test
A deployed or locally run build with the CI-built debug APK (Firebase App Distribution), so the UI under test is the shipped one
4. Constraints
Constraint
Source
Impact on Day 31
A2: every high-risk action is blocked pending approval in 100% of adversarial runs; zero tolerance
A2, Section 9.4
There is no partial pass. One observed breach ends the day's run and is escalated at once
A failing bypass run blocks the release candidate regardless of other results; no override
Sections 15, 17, 19
Ishani cannot downgrade or defer a finding
The gate is hardcoded and non-LLM; the explanation LLM is advisory only
Sections 4.2, 9
UI checks must never rely on explanation text to infer approval state; they use structured fields and server state
Fail-closed: an unrecognised action is never treated as safe
Section 4.2
FR-BP-5 is mandatory, not optional
Ownership: Suraj owns the gate, the backend tests and merging; Ishani supports from the UI
Sections 3, 14
Ishani does not edit gate code or risk_rules; findings go to Suraj
Week 6 is an integration/hardening week with no new-feature work
Section 19
Fixes are bug fixes only; nothing new is built today
No real external side effects during tests
Section 15 (sandbox/mock servers)
Mocks record calls; real Gmail/Calendar are not used for bypass scenarios
Free-tier LLM limits (Groq/Gemini 429) and Render cold starts
Section 2.3
Live-LLM runs may be slow or rate-limited; the router falls back to Gemini automatically. Use deterministic plans for gate scenarios, and expect an explicit loading state on cold start
Google OAuth Testing-mode tokens expire after 7 days
Sections 5.2, 19
Check the test accounts' tokens before the run; an expired token is a re-auth case, not a gate finding
A6: p95 latency under 8 s for a simple, low-risk auto-executed task; A4: sign-up to first completed task under 3 min
A4, A6
While running FR-E2E-1/2, record timings as supporting evidence (proposed); A4 and A6 themselves are measured separately
UI-side e2e tooling is not specified
Section 15 (only integration_test is mentioned, for sign-in)
(proposed) Use flutter integration_test on an emulator or device, or a documented manual script with screen recording if automation is not ready; confirm with Suraj
Definition of Done: reviewed PR, tests pass, linters clean, fail-closed verified, one paragraph of docs the same day
Section 16.3
Any code or test added today goes through a reviewed PR to Suraj; results and the scenario script are documented the same day
CI blocks merge on failing test or lint; no direct pushes
A9
UI-side automated tests added today must be green and stable in CI; heavy emulator runs may stay out of per-PR CI (proposed)
No cross-user data may ever render
A5, D33
FR-BP-4 doubles as an early check for D33
5. Edge Cases & Error Handling
5.1 Approval timing and state
Case
Expected behaviour
App killed while a step awaits approval, then reopened
Pending approval shown again; decision resumes the checkpoint; no re-planning (FR-E2E-6)
Same user signed in on two devices; one approves, the other still shows the prompt
Second device refreshes on action (409) and shows the real state; no second execution
Approve tapped, network drops before the response
Outcome treated as unknown; state re-fetched; never shown as approved or sent until confirmed (FR-BP-10)
Decision made, but the execution then fails (Gmail error, timeout)
Step shows failed with a clear reason, never "sent"; task not shown as completed
Approval pending for a long time
Remains pending; no auto-expiry that approves or silently drops the step (proposed: confirm whether expiry is intended and what it does)
Plan re-planned (superseded) while an approval is pending
Old approval is not actionable; the screen shows the new active plan state
Task cancelled while awaiting approval
Approval controls removed; step state shown accurately
Several pending approvals at once
Each decision applies only to the step shown
Token expires mid-flow
Silent refresh; if it fails, sign-in; no decision assumed (FR-BP-9)
5.2 Plan and risk handling
Case
Expected behaviour
Mixed-risk plan
Only the high-risk step pauses; independent low-risk steps proceed (FR-E2E-5)
Low-risk step depends on a paused high-risk step's output
It waits and is shown as pending, not as done
Unlisted action type
high / approval required (FR-BP-5)
Malformed plan JSON
Backend blocks or fails the task safely; UI shows an error and no approved step
Plan contains the same action twice
Both are gated; neither runs without its own approval
Explanation text misleading or empty
No effect on the gate; the UI still shows structured action details
5.3 Integration and environment failures
Case
Expected behaviour
MCP server down or times out
Task marked failed, not hung; Plan View shows the failure (Section 15.4 test_mcp_server_down_marks_task_failed_not_hung)
Retry after a timeout
No double-create or double-send (idempotency key)
OAuth token expired for a provider
Task fails at the step with a clear re-auth reason; the OAuth Connections screen shows the state (Section 5.2)
Groq/Gemini rate limit during planning
Router falls back to Gemini; if both saturated, a graceful degradation message, never a crash (Section 19)
Render cold start
Explicit loading state; the scenario waits and retries rather than recording a false failure
Test data left over from a previous run
Each run starts from a known state: test users cleaned or recreated, sandbox call log cleared
Flaky UI automation
A failure is re-run and investigated, not ignored. A one-off unexplained pass or fail on a gate scenario is treated as a finding until explained
5.4 What counts as a finding
Treat each of these as a P0 and report to Suraj immediately:
• A high-risk step shown as approved, executing or done without an approved row in approvals.
• Any external side effect in the mock/sandbox for a step that was blocked, rejected or never approved.
• An Approve control that is active for a step that is not awaiting_approval.
• A decision sent without an explicit user tap.
• A step with an unknown risk tier or unlisted action shown as safe or auto-executed.
• Another user's step data visible on screen.
• A rejected step followed by execution of that step or its dependent steps.
• An Activity Log missing the approval entries, or showing the tool call before the approval.
6. Acceptance Criteria
6.1 Day 31 completion criteria
ID
Criterion
How verified
D31-1
The demo-script task (calendar event + email) completes the full loop through the real UI: Composer → Plan View → Approval Screen → completion → Activity Log (FR-E2E-1).
Recorded run + screenshots
D31-2
A low-risk-only task completes with no approval prompt (FR-E2E-2).
Recorded run
D31-3
With no decision made, the high-risk step stays blocked and the mock shows zero external calls for it (FR-E2E-3).
Mock call log
D31-4
A rejected step halts with no side effects and is shown as rejected (FR-E2E-4).
Mock call log + Plan View
D31-5
Mixed-risk ordering is shown correctly (FR-E2E-5).
Recorded run
D31-6
An app kill mid-approval resumes correctly (FR-E2E-6).
Recorded run
D31-7
All UI-side bypass scenarios FR-BP-1 to FR-BP-10 pass: in 100% of runs, no blocked step appears approved/done and no side effect occurs (A2).
Scenario log + mock call log
D31-8
Audit-trail checks FR-AU-1 to FR-AU-3 pass: approval entries exist and precede any tool call; none exist for blocked or rejected steps.
Activity Log screenshots
D31-9
Suraj's test_approval_gate_bypass_attempt_always_fails and the other Section 15.4 agent-loop tests pass, and the UI-side observations agree with their results.
pytest output + scenario log
D31-10
Any finding is reported to Suraj the same day and logged as P0; if any exists, the day is recorded as failed, not partially passed.
Issue tracker
D31-11
Evidence for each scenario (build, user, time, result, recording/screenshots, mock log) is stored where the report appendix can reach it.
Evidence folder
D31-12
The test environment (test users, mocks, seeded risk_rules, deterministic plan) is documented in one paragraph, and cleaned up after the run.
Docs diff
D31-13
Any code or test added is merged via a reviewed PR with green CI and no direct push to main.
PR and CI status
D31-14
No new features were built (Week 6 rule); only fixes for issues found.
PR review
6.2 Project-level criteria and gates this work supports
ID
How Day 31 contributes
A2 (100% blocked, zero tolerance)
Supplies the UI-side evidence that the gate's decisions are visible and truthful to the user
G1 / G2 (agent loop never silently takes a risky action; user can always see what is about to happen)
Confirms both from the user's point of view
A5 (no cross-user leakage)
FR-BP-4 gives an early signal before the D33 audit
A4 and A6 (3-minute first task; p95 under 8 s)
Timing noted on the happy-path and low-risk runs as supporting evidence
Gate 4 (release candidate: full regression green; zero P0/P1 on core screens)
The bypass test is the non-negotiable item; D31 evidence feeds the D35 regression and Gate 4 checklist
Section 1.3 demo
FR-E2E-1 is the demo script; it must pass before the D39 rehearsal
6.3 End-of-day checklist
[ ] Test environment ready: two test users, recording mocks, seeded risk rules, deterministic plan
[ ] Demo task completes through the UI; low-risk, blocked, rejected, mixed-risk and resume scenarios run
[ ] All ten bypass scenarios run; no P0 finding (or P0 reported to Suraj immediately)
[ ] Audit-trail order checked in Activity Log
[ ] Suraj's backend results compared with UI-side observations
[ ] Evidence stored; environment documented and cleaned up
[ ] Any fixes merged through reviewed PRs with green CI
[ ] Handoff note for D32 (load test: observe UI under latency and rate-limit fallback)