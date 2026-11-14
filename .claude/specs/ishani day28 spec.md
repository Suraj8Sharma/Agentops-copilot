Day 28 Spec: Widget Tests for the Activity Log / Audit Trail Screen
Owner: Ishani (Frontend Design Lead & Trust Surfaces) · Date: Thu 24 Sep 2026 (D28, Week 5) · Source: AgentOps Implementation Manual, Sections 3, 4.2, 6, 7, 10, 11.1, 15.2, 16.3, 17, 18
Note on sources. Everything below comes from the manual except items marked (proposed). The manual names the Day 28 task ("Widget tests — Activity Log") and one test name. The remaining test names, query parameters, JSON shapes and thresholds are suggestions to confirm, not existing decisions.
Ownership note. The Activity Log screen is built by Jigyasu (Section 3), and the manual says each owner tests their own screens, but the Section 14 day plan assigns the Activity Log widget tests to Ishani on D28 while Jigyasu is on OAuth/JWT bug fixes. This spec follows the day plan. Ishani should tell Jigyasu she is writing the tests so the two of them do not duplicate work, and so Jigyasu can answer questions about the screen's intended behaviour.
1. Problem Statement
The Activity Log is the user-facing half of the system's auditability principle (Section 4.2): every planner decision, gate decision, MCP call and LLM call is written to execution_logs before it has any external effect, and the Activity Log is where the user can actually see that trail. It is described as a "searchable history of every decision and action taken". If this screen drops entries, shows them in the wrong order, mislabels an event, or leaks another user's data, the audit trail the whole safety story depends on becomes untrustworthy, even though the backend logged everything correctly.
The screen was built as a mock on D8, extended with filtering and search on D14, and wired to the real execution_logs table on D22. It has no automated tests. Day 28 adds widget tests, centred on the manual-named test_activity_log_filters_by_date_and_type, so that render, filter, search and pagination behaviour is enforced in CI.
Where Day 28 sits:
Item
Detail
Depends on
D25: widget-test framework; D26 and D27: testing patterns and mock setup reused; D14/D22: Activity Log filter/search built and wired to real execution_logs; D22: logging middleware live on every agent step
Feeds into
D29 (Ishani's banner-model quality pass), D30 (Week-5 PR merge, Gate 3), D33 (RLS-adjacent UI audit), D35 (full frontend regression)
Screen in scope
mobile/lib/features/activity_log/activity_log_screen.dart (owner: Jigyasu; tests: Ishani)
Out of scope today
Backend logging middleware and RLS tests (Suraj), Plan View and Approval Screen (D27), Notifications screen, e2e flows (D31)
2. Functional Requirements
The requirements describe what the tests must verify. The test name without a mark comes straight from Section 15.2. The others are (proposed) and follow the manual's test_<screen>_<behaviour> convention.
2.1 Activity Log screen (GET /activity-log)
ID
Requirement
Test
FR-AL-1
With a populated response, the screen renders each log entry with its event type, source (agent_name), timestamp and a readable summary of its payload.
test_activity_log_renders_entries (proposed)
FR-AL-2
Entries appear in a defined order (newest first) (proposed: confirm intended order with Jigyasu) and none are dropped or duplicated.
test_activity_log_entries_in_expected_order (proposed)
FR-AL-3
Filtering by date limits the list to entries within the chosen range, and clearing the filter restores the full list.
test_activity_log_filters_by_date_and_type
FR-AL-4
Filtering by type (event_type) limits the list to the selected type(s), and clearing the filter restores the full list.
test_activity_log_filters_by_date_and_type
FR-AL-5
Date and type filters can be combined, and the result is the intersection.
test_activity_log_filters_by_date_and_type
FR-AL-6
Search narrows the list to entries matching the query, and clearing the search restores the list.
test_activity_log_search_filters_entries (proposed)
FR-AL-7
Every event_type value (plan_created, risk_tagged, approval_requested, approval_decided, tool_called, tool_result, error) renders with a distinct, accurate label, and error entries are clearly distinguishable.
test_activity_log_renders_each_event_type (proposed)
FR-AL-8
Approval-related entries (approval_requested, approval_decided) show the step and the decision accurately (approved or rejected), since these are the entries a user relies on to verify the approval gate.
test_activity_log_approval_entries_show_decision (proposed)
FR-AL-9
Further pages load as the user scrolls (or taps load more), appending to the list without duplicating or losing entries.
test_activity_log_pagination_appends_next_page (proposed)
FR-AL-10
While the first page is loading, an explicit loading state is shown.
test_activity_log_shows_loading_state (proposed)
FR-AL-11
With no entries (new user, or filters that match nothing), an empty state is shown, and it distinguishes "no activity yet" from "no results for these filters".
test_activity_log_empty_states (proposed)
2.2 Cross-cutting
ID
Requirement
FR-X-1
All tests run under flutter test with the backend replaced by mocks or fakes. No test calls the real backend.
FR-X-2
The file is mobile/test/screens/activity_log_test.dart, reusing the D25 harness.
FR-X-3
Coverage for activity_log_screen.dart meets the overall 80% screen-coverage floor (proposed: aim well above it, since the screen has limited branching). The 100% bar applies only to Plan View and Approval Screen.
FR-X-4
Tests run automatically in CI on every PR.
3. API Contract
The widget tests mock the backend, so this contract defines exactly what the mocks return. The endpoint, its auth rule and its purpose, and the execution_logs columns, come from Sections 7 and 10. The query parameters and JSON shapes are not given in the manual, so they are marked (proposed). Confirm them with Suraj and Jigyasu before writing the mocks. Jigyasu wired this screen on D22 and knows the real parameters in use.
3.1 Endpoint used by this screen
Screen
Method
Path
Auth
Purpose
Activity Log
GET
/activity-log
JWT
Paginated, filterable execution_logs for the Activity Log screen
The route sits behind the JWT-verification dependency (Section 5.1). The app sends the Supabase access token as a bearer token. The data is read-only for the client: execution_logs allows INSERT only for the service role, and SELECT is restricted by RLS to the user's own tasks (task_id -> tasks.user_id = auth.uid()).
3.2 Query parameters (proposed)
Parameter
Type
Meaning
event_type
string (repeatable)
Filter by event_type: plan_created, risk_tagged, approval_requested, approval_decided, tool_called, tool_result, error
from, to
ISO 8601 date-time
Inclusive date range on created_at
q
string
Free-text search over entry content
cursor or page / limit
string or int
Pagination (manual says "paginated" without specifying the scheme: confirm cursor vs page)
3.3 Response shape (proposed)
{
  "items": [
    {
      "id": 1042,
      "task_id": "uuid",
      "step_id": "uuid",
      "agent_name": "risk_gate",
      "event_type": "approval_requested",
      "payload": { "tool_name": "gmail.send_message", "risk_tier": "high" },
      "latency_ms": 12,
      "model_used": null,
      "created_at": "2026-09-24T09:15:30Z"
    }
  ],
  "next_cursor": "opaque-string-or-null"
}
• id is a bigint identity column, so the client must treat it as a number that can be large, and not assume any particular range.
• step_id is nullable: planner-level events have no step yet.
• agent_name is one of planner, risk_gate, mcp_calendar, mcp_gmail, mcp_github, mcp_slack, llm_router, banner_model.
• model_used is groq:<model>, gemini:<model>, or null for non-LLM events. tokens_used and cost_estimate may also be present for LLM events.
• payload is lean structured JSON, not raw provider responses (Section 2.3), so it can be summarised for display.
3.4 Error responses the mocks must cover (proposed shapes, standard HTTP semantics)
Status
Meaning
Expected UI behaviour
401
Expired or invalid JWT
Silent refresh attempt, then hand-off to Sign In
422
Invalid filter value (e.g. from after to)
Inline message; previous results retained
429
Rate limited
Friendly retry message; previous results retained
5xx or timeout
Backend error or Render cold start
Explicit loading, then error state with retry; never an infinite spinner
4. Constraints
Constraint
Source
Impact on Day 28
Every screen gets at least render + basic-interaction coverage
Section 15.2
Defines the minimum bar for FR-AL-1 to FR-AL-11
The manual-named test is test_activity_log_filters_by_date_and_type
Section 15.2
It must exist with that exact name and cover date, type and their combination
Coverage floor is 80% of screens overall; 100% applies only to Approval Screen and Plan View
A7
Activity Log counts toward the 80%. No golden test is required (proposed: one golden for a mixed-event list is optional, only if stable)
The Activity Log is the user-facing half of "auditability by construction"
Section 4.2
The screen must show entries faithfully, with no silent omission or reordering, and error entries must never be hidden by default
execution_logs is read-only to the client; INSERT is service-role only
Section 7
The screen has no write path, and tests assert that no create, edit or delete action exists
RLS restricts rows to the user's own tasks
Section 7
Mocks contain only the current user's rows; a test confirms nothing the response wrongly includes from another user is presented as the user's activity (proposed)
No plaintext secrets in logs
Section 15.4 (test_tokens_never_logged_in_plaintext)
The UI must not render token-like values if one ever appears in a payload (proposed: test that payload display does not expose fields named like secrets)
execution_logs payloads are kept lean
Section 2.3
Payload rendering is a summary view, with the full detail reachable (proposed)
Large tables are possible (one row per agent step)
Section 2.3
List must be lazy and paginated. Tests use a long mocked list to confirm it does not render everything at once
execution_logs.task_id is indexed for RLS
Section 7.2
Backend concern only; no client impact
Definition of Done: merged via reviewed PR, tests pass, linters clean, one paragraph of docs the same day
Section 16.3
PR goes to Suraj (sole merger); docs note added the same day
CI blocks merge on any failing test or lint error
A9
Tests must be stable and non-flaky, particularly date-based filter tests (use a fixed clock, never the real current time)
Saturday is review + PR-merge day
Section 13
Work may merge on D28, or at the latest on D30 (Week-5 merge), in time for Gate 3 on 26 Sep
Render free-tier cold starts and rate limits
Section 2.3
Loading and error states are asserted, since a cold start would otherwise look like an empty log
5. Edge Cases & Error Handling
5.1 Filtering and search
Case
Expected behaviour
Covered by
Date range with no matching entries
"No results for these filters" empty state, with a way to clear filters
FR-AL-11
Date range boundaries (entry exactly at from or to)
Inclusive as defined by the API contract; timezone handled consistently (stored in UTC, displayed in local time)
test_activity_log_date_filter_boundaries (proposed)
Invalid range (from after to)
Inline validation or 422 message; previous list is not wiped
test_activity_log_invalid_date_range_message (proposed)
Multiple types selected
Union of the selected types, then intersected with the date filter
test_activity_log_multiple_type_filters (proposed)
Filter changed while a request is in flight
Only the latest request's results are shown; stale responses are ignored
test_activity_log_ignores_stale_response_after_filter_change (proposed)
Search with special characters or very long input
No crash and no injection into the query; request is properly encoded
test_activity_log_search_special_characters (proposed)
Search typed quickly
Requests are debounced or cancelled, not one per keystroke (proposed: confirm intended behaviour)
test_activity_log_search_is_debounced (proposed)
Filters and search persist across scroll and pagination
Next page uses the same filters
test_activity_log_pagination_preserves_filters (proposed)
5.2 Rendering
Case
Expected behaviour
Covered by
Unknown event_type or agent_name from the backend
Rendered with a safe neutral label; no crash; entry still shown
test_activity_log_unknown_event_type_does_not_crash (proposed)
Null optional fields (step_id, model_used, latency_ms, tokens_used)
Rendered without errors or literal "null" text
test_activity_log_handles_null_optional_fields (proposed)
Empty or very large payload
Summarised cleanly, no overflow, full detail reachable
test_activity_log_large_payload_no_overflow (proposed)
Payload containing a secret-like field
The value is not displayed
test_activity_log_does_not_render_secret_like_fields (proposed)
error entries
Distinct styling plus a text label (not colour alone), and never hidden by default
FR-AL-7
Many entries share the same timestamp
Stable ordering by id; no flicker or reshuffle on refresh
test_activity_log_stable_order_for_equal_timestamps (proposed)
Long text or large text scale on a small screen
No overflow; filters remain reachable
test_activity_log_small_screen_large_text (proposed)
Large id values (bigint)
Handled as numbers or strings without precision loss
test_activity_log_handles_large_ids (proposed)
5.3 Pagination and loading
Case
Expected behaviour
Covered by
Last page reached (next_cursor null)
No further requests; an end-of-list indicator or nothing, not a spinner
test_activity_log_stops_at_last_page (proposed)
Next-page request fails
Error shown at the bottom of the list with retry; already-loaded entries remain
test_activity_log_next_page_failure_keeps_existing_entries (proposed)
Duplicate entries across page boundaries
Not shown twice (de-duplicated by id)
test_activity_log_deduplicates_across_pages (proposed)
First load fails or times out
Error state with retry; not shown as an empty log
test_activity_log_first_load_error_not_shown_as_empty (proposed)
Cold start (slow first response)
Explicit loading state until data arrives
FR-AL-10
Pull-to-refresh
Reloads from the first page and keeps the current filters
test_activity_log_pull_to_refresh (proposed)
401 mid-scroll
Silent refresh, retry once, then hand-off to Sign In without losing loaded entries
test_activity_log_401_handoff (proposed)
5.4 Test-suite hygiene
• Use a fixed clock: date-filter tests must not depend on the real current date. Inject a fixed "now" and build entries relative to it.
• Assert exact lists: after each filter, verify the exact set and order of entries on screen, not just that the list is non-empty.
• No real network: an unmocked call fails the test.
• Bugs found while testing: fix them in the same PR if in scope, or log them with severity and tell Jigyasu, who owns the screen. P0/P1 bugs on core screens must be closed by Gate 4 on 3 Oct. Any case where the log hides or misreports an error or approval decision is treated as P0.
6. Acceptance Criteria
6.1 Day 28 completion criteria
ID
Criterion
How verified
D28-1
activity_log_test.dart exists under mobile/test/screens/.
File review in PR
D28-2
The manual-named test test_activity_log_filters_by_date_and_type exists and passes, and covers date only, type only and both combined.
flutter test output
D28-3
Every FR in Section 2 has at least one passing test (FR-AL-1 to 11).
Test output mapped to FR IDs
D28-4
The edge cases in Section 5 are covered, or any exception is listed in the PR description with a reason.
PR checklist
D28-5
Date-filter tests use a fixed clock and pass regardless of the date they are run on.
Code review; run with a changed system date
D28-6
Screen coverage for activity_log_screen.dart meets or exceeds the 80% floor.
flutter test --coverage report
D28-7
No test calls the real backend. Mock payloads and query parameters match Section 3, confirmed with Suraj and Jigyasu or flagged as assumptions.
Code review, PR comment
D28-8
The screen exposes no write action on log entries (read-only), verified by a test.
Named test
D28-9
Linters are clean, CI is green, and the PR is opened for Suraj's review with no direct push to main.
PR and CI status
D28-10
A short docs paragraph on how to run and extend the test is added the same day.
Docs diff in PR
D28-11
Jigyasu has been told which tests were added and any screen bugs found.
PR comment or message
D28-12
No flaky failures across 3 consecutive CI runs (proposed threshold).
CI history
6.2 Project-level criteria this work supports
ID
How Day 28 contributes
A7 (widget-test coverage ≥ 80% of screens overall)
Adds another screen to the covered set, bringing Ishani's D26–D28 total to six of her screens plus Activity Log
A9 (CI blocks merge on any failing test or lint error)
Tests run in CI and must be stable, in particular the date-based ones
Section 4.2, Auditability by construction
Gives automated protection to the screen where users can verify that the audit trail is complete and accurate
A2 (high-risk actions blocked pending approval)
The approval entries shown here are the user's way to confirm gate decisions, so correct rendering of approval_requested and approval_decided supports the user-visible evidence for A2
Gate 3 ("Widget tests written for every screen")
Closes the Activity Log; with D26 and D27 this completes the screens in Ishani's test scope. Trust Dashboard and OAuth Connections are the ones to check against the gate before D30
6.3 End-of-day checklist
[ ] Test file written and passing locally
[ ] Clock injected so filters are date-independent
[ ] Mock payloads and query params confirmed with Suraj and Jigyasu (or assumptions noted)
[ ] CI green on the PR; PR opened for Suraj's review
[ ] README or module doc paragraph added
[ ] Jigyasu informed of tests added and any bugs found
[ ] Bugs found are fixed or logged with severity
[ ] Handoff note ready for D29 (banner-model quality pass) and D30 (Week-5 merge and Gate 3 check)