Day 26 Spec: Widget Tests for Onboarding, Home/Dashboard & Task Composer
Owner: Ishani (Frontend Design Lead & Trust Surfaces) · Date: Tue 22 Sep 2026 (D26, Week 5) · Source: AgentOps Implementation Manual, Sections 3, 6, 10, 15.2, 16.3, 17, 18
Note on sources. Everything below comes from the manual except items marked (proposed). The manual names only the Day 26 task ("Widget tests — Onboarding, Home/Dashboard, Task Composer") and the general widget-testing rules, so the test names, payload shapes and thresholds marked (proposed) are suggestions to confirm, not existing decisions.
1. Problem Statement
The three entry-point screens of the core trust loop (Onboarding/Splash, Home/Dashboard and Task Composer) were built against mock data on D3–D5 and wired to real endpoints on D13–D14. They have no automated tests. Until they do, a change to the theme, router or backend payload can silently break the first screens a user sees, and nothing in CI would catch it.
Day 26 closes that gap. Ishani writes flutter test widget tests for these three screens so each has render and basic-interaction coverage running in CI, as required by Gate 3 ("Widget tests written for every screen") and Acceptance Criterion A7.
Where Day 26 sits:
Item
Detail
Depends on
D25: widget-test framework and golden-screen baseline set up; D13/D14: Home and Composer wired to real GET /tasks and POST /tasks
Feeds into
D27 (Plan View, Approval Screen tests), D28 (Activity Log tests), D35 (full frontend regression), Gate 3
Screens in scope
onboarding_screen.dart, home_screen.dart, task_composer_screen.dart
Out of scope today
Plan View, Approval Screen (D27), Activity Log (D28), OAuth Connections, Trust Dashboard, Voice Input internals (Jigyasu's tests, D24/D26), backend tests, e2e tests (D31)
2. Functional Requirements
The requirements describe what the tests must verify. Test IDs are (proposed) and follow the manual's test_<screen>_<behaviour> naming style.
2.1 Onboarding / Splash (static, no backend dependency)
ID
Requirement
Proposed test
FR-ON-1
The screen renders its first-run intro content without errors, using the design tokens from theme.dart.
test_onboarding_renders_intro
FR-ON-2
Permission priming content is shown (microphone, and notifications where applicable) before any system permission prompt fires.
test_onboarding_shows_permission_priming
FR-ON-3
The primary action advances through the flow and ends by navigating to the next route via router.dart.
test_onboarding_continue_navigates_forward
FR-ON-4
Completing onboarding results in profiles.onboarding_completed = true being requested (mocked in the test), so the screen is not shown again.
test_onboarding_completion_marks_profile_complete
2.2 Home / Dashboard (GET /tasks)
ID
Requirement
Proposed test
FR-HM-1
With a populated response, the task list renders every task with its status (submitted, planning, awaiting_approval, executing, completed, failed, cancelled).
test_home_renders_task_list_with_statuses
FR-HM-2
With an empty list, a clear empty state is shown with an obvious path to create a task.
test_home_renders_empty_state_when_no_tasks
FR-HM-3
While the request is in flight, an explicit loading state is shown.
test_home_shows_loading_state
FR-HM-4
The quick-entry control navigates to the Task Composer.
test_home_quick_entry_opens_composer
FR-HM-5
Tapping a task opens its detail or plan route.
test_home_task_tap_navigates_to_task
FR-HM-6
A failed request shows an error state with a retry action, and retry re-issues the request.
test_home_error_state_retry_refetches
2.3 Task Composer (POST /tasks)
ID
Requirement
Proposed test
FR-TC-1
The screen renders the text-entry mode with an enabled-state submit control and a way to switch to voice mode.
test_composer_renders_text_mode
FR-TC-2
Submit is disabled (or blocked) for empty or whitespace-only input.
test_composer_blocks_empty_submit
FR-TC-3
Valid text input is submitted as input_type: "text" with the user's text, and the screen shows a submitting state.
test_composer_submits_text_task
FR-TC-4
On success, the app navigates onward (to the new task's plan view or Home) using the returned task id.
test_composer_success_navigates_with_task_id
FR-TC-5
Voice mode hands off to the Voice Input screen and, on return, populates the task with the transcription and submits it as input_type: "voice". Jigyasu's voice internals are mocked here.
test_composer_voice_mode_submits_transcription
FR-TC-6
A failed submission shows an error, keeps the user's typed text, and allows retry.
test_composer_error_preserves_input_and_allows_retry
FR-TC-7
Double-tapping submit sends exactly one request.
test_composer_double_tap_submits_once
2.4 Cross-cutting
ID
Requirement
FR-X-1
All tests run under flutter test with all network access replaced by mocks or fakes; no test calls the real backend.
FR-X-2
Tests live under mobile/test/screens/ (one file per screen, e.g. onboarding_test.dart, home_test.dart, task_composer_test.dart), reusing the D25 harness and golden-screen baseline.
FR-X-3
Tests run automatically in CI (ci.yml) on every PR.
3. API Contract
The widget tests mock the backend, so the contract below defines exactly what the mocks must return. Endpoint paths, auth rules and the tasks columns come from Sections 7 and 10 of the manual. The request and response JSON shapes are not specified in the manual: they are derived from the tasks table and marked (proposed). Confirm them with Suraj before mocking (the D14 digest-style "payload contract" step applies here too).
3.1 Endpoints used by these screens
Screen
Method
Path
Auth
Purpose
Home/Dashboard
GET
/tasks
JWT
List the user's tasks with status
Task Composer
POST
/tasks
JWT
Submit a new text or voice task; kicks off the LangGraph run
Onboarding
none
n/a
n/a
Static screen; completion flag lives in profiles.onboarding_completed (write path not defined in the manual: confirm which endpoint or Supabase call sets it)
Both /tasks routes sit behind the JWT-verification dependency (Section 5.1). The Flutter app sends the Supabase access token as a bearer token.
3.2 GET /tasks (response shape proposed)
[
  {
    "id": "uuid",
    "input_type": "text",
    "raw_input": "Schedule a call with Priya tomorrow at 4pm",
    "transcription_text": null,
    "status": "awaiting_approval",
    "created_at": "2026-09-22T09:30:00Z",
    "completed_at": null
  }
]
• status is one of: submitted, planning, awaiting_approval, executing, completed, failed, cancelled.
• input_type is text or voice. For voice tasks raw_input is empty and transcription_text holds the STT output.
• Results are scoped to the caller by RLS (user_id = auth.uid()), so mocks must never include another user's rows.
3.3 POST /tasks (request and response shapes proposed)
Request:
{ "input_type": "text", "raw_input": "Draft an email to my team about Friday's review" }
Voice request:
{ "input_type": "voice", "transcription_text": "draft an email to my team about Friday's review" }
Success response (201):
{ "id": "uuid", "status": "submitted", "created_at": "2026-09-22T09:31:00Z" }
3.4 Error responses the mocks must cover (proposed shapes, standard HTTP semantics)
Status
Meaning
Expected UI behaviour
401
Expired or invalid JWT
Client attempts silent refresh; if that fails, route to Sign In (owned by the auth flow, only the hand-off is asserted here)
422
Invalid input (e.g. empty text)
Inline validation message; input preserved
429
Rate limited (LLM free tier)
Friendly retry message; input preserved
5xx or timeout
Backend error or Render cold start
Explicit loading, then error state with retry; never an infinite spinner
4. Constraints
Constraint
Source
Impact on Day 26
Tooling is flutter test (widget + golden tests)
Section 15
No integration_test or device tests today; those belong to the auth suite and e2e on D31
Coverage floor is 80% of screens overall (100% for Approval Screen and Plan View)
A7
Today's three screens count toward the 80%; they are not held to the 100% bar but must have render and basic-interaction coverage at minimum
Every screen gets at least render + basic-interaction coverage
Section 15.2
Defines the minimum bar for FR-ON, FR-HM and FR-TC
Golden tests are mandatory only for Approval Screen and Plan View
Section 15.2
Golden files for these three screens are optional (proposed: add one baseline each for stable states only, to avoid brittle diffs)
Definition of Done: merged via a reviewed PR, tests pass, linters clean, fail-closed behaviour verified where relevant, one paragraph of docs the same day
Section 16.3
PR goes to Suraj (sole merger); a short testing note goes in the README or module doc before end of day
CI blocks merge on any failing test or lint error; no direct pushes to main
A9
New tests must be green and stable (non-flaky) on CI, not just locally
Saturday is review + PR-merge day
Section 13
Day 26 work may merge on D26 or at the latest on D30 (Week-5 merge), but must be done in time for Gate 3 on 26 Sep
Render free-tier cold starts read as a hang
Section 2.3
The client must show an explicit loading state; Home and Composer tests assert it
Groq/Gemini free-tier limits can return 429
Section 2.3
Composer must handle a rate-limited submission gracefully
Screen files are owned by Ishani
Section 11 / Appendix D
Fixes to the screens themselves are in scope when a test exposes a bug; changes to backend payloads are not (raise with Suraj)
Design tokens come from theme.dart
Section 3
Tests should use the real theme so a token change shows up in the render
5. Edge Cases & Error Handling
5.1 Onboarding
Case
Expected behaviour
Covered by
User denies a permission after priming
Flow continues; the app does not block on denied mic or notifications
test_onboarding_continues_when_permission_denied (proposed)
Onboarding re-entered after completion
Screen is skipped (redirect based on the flag)
test_onboarding_skipped_when_already_completed (proposed)
Small screen or large text scale
No overflow errors; primary action remains reachable
test_onboarding_no_overflow_on_small_screen_and_large_text (proposed)
5.2 Home / Dashboard
Case
Expected behaviour
Covered by
Empty task list
Empty state with a call to action
FR-HM-2
Slow response / cold start
Explicit loading state, not a frozen or blank screen
FR-HM-3
Backend error (5xx, timeout)
Error state with retry
FR-HM-6
Task with failed or awaiting_approval status
Visually distinct and understandable at a glance; never rendered as completed
test_home_distinguishes_failed_and_awaiting_approval (proposed)
Very long raw_input
Text truncates cleanly; no overflow
test_home_truncates_long_task_text (proposed)
Voice task with empty raw_input
Displays the transcription instead of a blank row
test_home_shows_transcription_for_voice_task (proposed)
Large list (50+ tasks)
List scrolls; renders lazily
test_home_large_list_scrolls (proposed)
Unknown status value from the backend
Rendered with a safe neutral fallback; no crash (the app treats unrecognised states cautiously)
test_home_unknown_status_does_not_crash (proposed)
5.3 Task Composer
Case
Expected behaviour
Covered by
Empty or whitespace-only input
Submit blocked; no request sent
FR-TC-2
Double tap on submit
Exactly one POST /tasks
FR-TC-7
Network failure or timeout
Error shown; typed text preserved; retry possible
FR-TC-6
429 rate limit
Friendly message; text preserved
test_composer_rate_limited_shows_retry_message (proposed)
401 mid-submit
Silent refresh attempt, then hand-off to Sign In; no lost input where possible
test_composer_401_triggers_auth_handoff (proposed)
Voice permission denied or STT returns empty
User returned to text mode with a clear message; no empty task submitted
test_composer_voice_empty_transcription_not_submitted (proposed)
Very long input
Handled by a documented limit (manual defines none: confirm a max length with Suraj)
test_composer_long_input_handling (proposed)
Back navigation with unsent text
Defined behaviour (keep draft or confirm discard) (proposed: ask before discarding)
test_composer_back_with_draft (proposed)
5.4 Test-suite hygiene
• Fail loudly, not silently: an unmocked network call must fail the test rather than hit the real backend.
• No flakiness: use pumpAndSettle with bounded timeouts and fake clocks. A test that passes locally but intermittently fails on CI blocks other people's merges (A9).
• Bugs found while testing: if a test exposes a real bug in one of these screens, fix it in the same PR or log it with severity (P0/P1 must be closed by Gate 4 on 3 Oct) and tell Suraj during triage.
• Safety posture: these screens are not safety-critical, but the same rule applies as elsewhere in the system: when the UI is unsure what a task's state is, it must not present it as completed or approved.
6. Acceptance Criteria
6.1 Day 26 completion criteria
ID
Criterion
How verified
D26-1
Test files exist for Onboarding, Home/Dashboard and Task Composer under mobile/test/screens/.
File review in PR
D26-2
Every FR in Section 2 has at least one passing test (FR-ON-1 to 4, FR-HM-1 to 6, FR-TC-1 to 7).
flutter test output mapped to FR IDs
D26-3
The edge cases in Section 5 are covered, or any exception is listed in the PR description with a reason.
PR description checklist
D26-4
All tests pass locally and in CI on a clean checkout, with no flaky reruns across 3 consecutive CI runs (proposed threshold).
CI history
D26-5
No test makes a real network call; all backend interactions go through mocks that match the contract in Section 3.
Code review; tests fail if network is attempted
D26-6
Linters are clean and the PR is opened for Suraj's review, with no direct push to main.
PR and CI status
D26-7
A short docs paragraph on how to run and extend these tests is added to the README or a module doc the same day.
Docs diff in PR
D26-8
Mock payload shapes (Section 3) are confirmed with Suraj or flagged as assumptions in the PR.
PR comment or message thread
D26-9
Any real bugs found are fixed or filed with severity, and none is left unlogged.
Issue tracker
6.2 Project-level criteria this work supports
ID
How Day 26 contributes
A7 (widget-test coverage ≥ 80% of screens overall, 100% on Approval Screen and Plan View)
Adds the first three of Ishani's seven core screens to the covered set
A9 (CI blocks merge on any failing test or lint error)
Tests run in CI and must be stable enough not to block merges spuriously
A4 (first-time user goes from sign-up to first completed task in under 3 minutes)
Onboarding, Home and Composer form the first-run path; regressions here would hurt this metric
Gate 3 ("Widget tests written for every screen")
Closes three of the screens owed by Ishani on 26 Sep; D27 and D28 cover Plan View, Approval Screen and Activity Log
6.3 End-of-day checklist
[ ] Three test files written and passing locally
[ ] Mock payloads confirmed with Suraj (or assumptions noted)
[ ] CI green on the PR
[ ] PR opened for Suraj's review
[ ] README or module doc paragraph added
[ ] Bugs found are fixed or logged
[ ] Handoff note ready for D27 (Plan View and Approval Screen tests: safety-critical, golden tests, 100% coverage)