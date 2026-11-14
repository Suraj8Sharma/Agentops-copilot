Day 30 Spec: Trust Dashboard Wired to Real Metrics + Week-5 Review & PR Merge
Owner: Ishani (Frontend Design Lead & Trust Surfaces) · Date: Sat 26 Sep 2026 (D30, Week 5, Gate 3 day) · Source: AgentOps Implementation Manual, Sections 1.3, 3, 6, 7, 10, 12, 13, 15, 16.3, 17, 18 and the Section 14 day plan (D10, D25–D30)
Note on sources. Everything below comes from the manual except items marked (proposed). The manual names the Day 30 tasks ("Trust Dashboard wired to real metrics; Week-5 review; PR merge") and the endpoint (GET /dashboard/metrics: "Aggregate latency/cost/accuracy for the Trust Dashboard"), but it does not define the response JSON, the panels in detail, or the dashboard's test names. Those are suggestions to confirm, not existing decisions.
1. Problem Statement
The Trust Dashboard is the screen that makes the system's behaviour observable to the user: how accurate the agent's models are, how fast and how costly its LLM calls are, and whether its integrations are healthy. It was built on D10 as a UI with mock charts (latency, cost, accuracy). Until it reads real data, it shows invented numbers, which is worse than showing nothing on a screen whose entire purpose is trust.
On D30, Suraj ships the metrics endpoint and Ishani wires the screen to it. The same day is the Week-5 review and PR-merge day (Section 13) and the date of Gate 3, which requires, for Ishani, "Widget tests written for every screen; Trust Dashboard wired". Day 30 therefore has two jobs: connect the dashboard to real metrics, and close Week 5 by reviewing and merging the week's frontend work so nothing is carried forward silently.
Where Day 30 sits:
Item
Detail
Depends on
D10: Trust Dashboard UI (mock charts); D21: llm_usage_logs live; D25–D26: eval_cases / eval_runs tables, eval suite v1 in CI; D29: banner-model eval run (feeds the accuracy panel); D30 (same day): Suraj's GET /dashboard/metrics endpoint
Feeds into
D31–D32 (e2e and load tests: the dashboard is where load results become visible), D33 (UI audit: no cross-user data), D34 (UI polish), D35 (full regression), D39 demo rehearsal (Section 1.3 demo ends on the dashboard)
Files in scope
mobile/lib/features/trust_dashboard/trust_dashboard_screen.dart, mobile/test/screens/trust_dashboard_test.dart (proposed)
Out of scope today
Building the endpoint (Suraj), eval pipeline internals, new metrics beyond latency/cost/accuracy and MCP health, push notifications, OCR backlog item
Same-day dependency. The endpoint and the screen wiring both land on D30. Ishani can only wire against the contract until Suraj's endpoint is live, so agreeing the response shape with Suraj early in the day (or before) decides whether this fits in one day.
2. Functional Requirements
2.1 Trust Dashboard (GET /dashboard/metrics)
ID
Requirement
FR-TD-1
The screen loads its data from GET /dashboard/metrics and no longer uses mock data in any build that is merged.
FR-TD-2
Accuracy panel: shows eval results per suite (planner_eval, router_eval, risk_explainer_eval, banner_model_eval) from eval_runs: pass count, fail count, a pass rate, and when the last run happened.
FR-TD-3
Latency panel: shows LLM latency from llm_usage_logs (for example average, and p95 (proposed)), ideally split by provider (groq / gemini).
FR-TD-4
Cost panel: shows LLM usage cost or its closest available measure (see the open question in Section 3.3: llm_usage_logs stores tokens, not currency; per-call cost_estimate lives in execution_logs).
FR-TD-5
Model / routing view: shows which provider and model answered requests, and how often the Gemini fallback engaged. The manual's demo (Section 1.3) says the dashboard shows "the latency, the model used, and which rung of the LLM cost ladder answered the request"; the term "cost ladder" is not defined elsewhere in the manual, so confirm with Suraj what this panel must show.
FR-TD-6
Integration health: shows the status (healthy, degraded, down) and last check time for each of the four MCP servers (calendar, gmail, github, slack) from mcp_server_registry.
FR-TD-7
Approvals: shows decision response time from approvals.response_time_ms (manual says this field "feeds the Trust Dashboard").
FR-TD-8
The screen shows when the data was generated, so a user can tell how fresh the numbers are.
FR-TD-9
Loading, empty, error and stale states exist for the screen and for each panel independently, so one failing panel does not blank the others.
FR-TD-10
The screen is read-only: no control on it can change data, rules or settings.
FR-TD-11
The screen never presents a missing or zero value as a good result (for example "0 failures" when there were no runs).
2.2 Widget test for the Trust Dashboard
Gate 3 requires widget tests for every screen. The Section 14 plan schedules widget tests on D26 (Onboarding, Home, Composer), D27 (Plan View, Approval Screen) and D28 (Activity Log) but not for the Trust Dashboard or OAuth Connections. This spec adds the Trust Dashboard test to Day 30 and flags OAuth Connections as a gap to close by the end of the day or confirm as already done.
ID
Requirement
Test (proposed names)
FR-WT-1
Renders all panels with a populated response.
test_trust_dashboard_renders_all_panels
FR-WT-2
Shows each of the four eval suites with correct counts and pass rate.
test_trust_dashboard_accuracy_panel_values
FR-WT-3
Shows MCP server health with the correct status per server.
test_trust_dashboard_shows_mcp_health_per_server
FR-WT-4
Loading, empty, error-with-retry and partial-failure states render correctly.
test_trust_dashboard_loading_empty_error_states
FR-WT-5
A zero or missing value is not displayed as a success.
test_trust_dashboard_missing_data_not_shown_as_zero
FR-WT-6
OAuth Connections: test_oauth_connections_shows_correct_connect_state_per_provider (the name in Section 15.2) exists and passes.
oauth_connections_test.dart
2.3 Week-5 review and PR merge
ID
Requirement
FR-RV-1
Review the week's frontend PRs and the work they contain: the test framework and baseline (D25), widget tests for Onboarding, Home, Composer (D26), Plan View and Approval Screen (D27), Activity Log (D28), the banner-model quality pass (D29), and today's Trust Dashboard wiring.
FR-RV-2
Everything in flight is either merged or has a written reason and an owner for carrying it over. Nothing is carried forward silently (Section 13).
FR-RV-3
All PRs go through a reviewed PR to Suraj, the sole merger; CI is green on each.
FR-RV-4
Run the Gate 3 checklist for Ishani's line items (Section 6.3) and for the team where Ishani oversees client-side work (Jigyasu, Sanskriti, Shivangi).
FR-RV-5
Confirm coverage against A7: 100% on Approval Screen and Plan View, 80% across screens overall.
FR-RV-6
Record the Week-5 review outcome and hand a short summary to Shivangi for weekly report #4, which she finalises today.
3. API Contract
3.1 Endpoint defined by the manual
Method
Path
Auth
Purpose
GET
/dashboard/metrics
JWT
Aggregate latency/cost/accuracy for the Trust Dashboard
The route sits behind the JWT-verification dependency (Section 5.1). The app sends the Supabase access token as a bearer token.
3.2 Source tables and access rules (from the manual)
Table
Used for
Access
eval_runs (suite_name, pass_count, fail_count, avg_latency_ms, run_date)
Accuracy panel
Internal, service-role only
llm_usage_logs (provider, model, tokens_in, tokens_out, latency_ms, request_type, rate_limit_hit, created_at)
Latency, routing and cost panels
Internal, service-role only, never exposed to the client
mcp_server_registry (server_name, status, last_health_check, version)
Integration health
Internal, service-role only
approvals (response_time_ms, user_id)
Approvals panel
RLS: user_id = auth.uid()
Because three of the four sources are service-role only, the client must not and cannot read them directly. It sees them only as aggregates returned by /dashboard/metrics. The endpoint therefore must return aggregates only, never raw rows.
3.3 Response shape (proposed)
Confirm every field with Suraj before wiring.
{
  "generated_at": "2026-09-26T09:00:00Z",
  "period": "7d",
  "accuracy": {
    "suites": [
      {
        "suite_name": "planner_eval",
        "pass_count": 27,
        "fail_count": 3,
        "pass_rate": 0.9,
        "avg_latency_ms": 1240,
        "last_run": "2026-09-25T18:30:00Z"
      }
    ]
  },
  "latency": {
    "avg_ms": 820,
    "p95_ms": 2100,
    "by_provider": [
      { "provider": "groq", "avg_ms": 640, "requests": 410 },
      { "provider": "gemini", "avg_ms": 1500, "requests": 38 }
    ]
  },
  "cost": {
    "tokens_in": 182000,
    "tokens_out": 41000,
    "estimated_cost_usd": 0.0
  },
  "routing": { "fallback_rate": 0.08, "rate_limit_hits": 12 },
  "mcp_health": [
    { "server_name": "calendar", "status": "healthy", "last_health_check": "2026-09-26T08:58:00Z" }
  ],
  "approvals": { "avg_response_time_ms": 8400, "decided_count": 14 }
}
• Every panel object is optional in the response, so a missing panel can show its own empty state instead of failing the whole screen.
• pass_rate is computed by the server from pass_count and fail_count and is null when both are zero.
• period is a proposed query parameter (?period=7d|30d); confirm whether the manual's plan includes a time range at all.
Open questions to settle with Suraj before wiring:
• Scope: eval_runs, llm_usage_logs and mcp_server_registry have no user_id column, so these panels are system-wide aggregates, not per-user. Only the approvals panel is per-user. The screen should say so, so users do not read global numbers as their own.
• Cost: llm_usage_logs stores tokens, not currency; execution_logs.cost_estimate stores a per-event estimate. Decide which source the cost panel uses and what it shows when all calls are free-tier (zero).
• "Cost ladder": what the demo's "rung of the LLM cost ladder" maps to in the data (likely provider/model, with Groq primary and Gemini fallback).
3.4 Error responses the mocks and screen must handle (proposed shapes, standard HTTP semantics)
Status
Meaning
Expected UI behaviour
401
Expired or invalid JWT
Silent refresh attempt, then hand-off to Sign In
403
Not permitted
Clear "not available" state; no data shown
429
Rate limited
Friendly retry message; previous data retained and marked as stale
5xx or timeout
Backend error or Render cold start
Explicit loading, then error state with retry; never an infinite spinner or fabricated numbers
4. Constraints
Constraint
Source
Impact on Day 30
eval_runs, llm_usage_logs, mcp_server_registry are service-role only and never exposed to the client
Section 7
The client talks only to /dashboard/metrics; no client code reads these tables. A review check confirms there is no direct Supabase table access in the screen
No cross-user data may ever render (A5: leakage = 0)
A5, D33
Only aggregates are shown; no per-user rows or identifiers from other users; Ishani's D33 UI audit will re-check this screen
Dashboard data is read-only for the user
Section 6
The screen has no write path and no action that changes risk rules, eval data or settings
The dashboard's accuracy panel is fed by eval_runs rows from CI
Section 15.1
An empty or old eval_runs table is a normal state early on, and must be shown honestly
Free-tier hosting and database limits
Section 2.3
Aggregate queries must be light (indexes on llm_usage_logs.created_at and eval_cases.run_id exist for this); the screen should not poll aggressively (proposed: fetch on open and on manual refresh)
Render cold starts read as a hang
Section 2.3
The screen shows an explicit loading state
Same-day endpoint dependency
Section 14, D30
Wiring is against a contract agreed with Suraj; any difference found at integration is fixed on D30 or recorded as an open item
Gate 3 → Ishani: "Widget tests written for every screen; Trust Dashboard wired"
Section 17
Both halves must be true at the end of D30, which includes a Trust Dashboard test and the OAuth Connections test
Coverage floor 80% overall; 100% on Approval Screen and Plan View
A7
Confirm numbers at the Week-5 review; the Trust Dashboard test counts toward the 80%
Definition of Done: merged via reviewed PR, tests pass, linters clean, one paragraph of docs the same day
Section 16.3
Applies to the Trust Dashboard PR; docs note describes the panels and their data sources
CI blocks merge on any failing test or lint error; one required review; Suraj is sole merger; no direct pushes
Section 12, A9
Every PR today needs green CI (lint, flutter test, eval smoke subset, build check) and Suraj's review. Merges take time: queue PRs early
Saturday is review + PR-merge day
Section 13
Nothing new is started after the dashboard is wired; remaining time goes to review, fixes and merging
A p95 latency target exists for simple auto-executed tasks (under 8 seconds)
A6
If the dashboard shows p95, label what it measures so it is not confused with A6's end-to-end task latency
5. Edge Cases & Error Handling
5.1 Data states
Case
Expected behaviour
Test (proposed)
No eval runs yet
Accuracy panel shows "no runs yet", not 0% or 100%
test_trust_dashboard_no_eval_runs_empty_state
Suite exists with zero passes and zero failures
Pass rate shown as unavailable, not as a number
test_trust_dashboard_zero_total_pass_rate_unavailable
One suite has data and others do not
Each suite shown independently; missing ones labelled, not hidden
test_trust_dashboard_partial_suites
Very old last-run date
Marked as stale so the numbers are not read as current
test_trust_dashboard_stale_data_marked
No LLM calls in the period
Latency and cost panels show an empty state, not zeros
test_trust_dashboard_no_llm_calls_empty_state
All traffic on free tier (cost zero)
Cost panel explains zero cost rather than looking broken
test_trust_dashboard_zero_cost_free_tier
Gemini fallback share is high (rate limit pressure)
Shown plainly, with no alarming language
test_trust_dashboard_fallback_rate_displayed
MCP server degraded or down
Clearly distinguished from healthy, with a text label as well as colour
test_trust_dashboard_mcp_status_variants
MCP server missing from the response
Shown as "unknown", never assumed healthy
test_trust_dashboard_missing_mcp_server_unknown
Unknown status or suite name from the backend
Neutral display, no crash
test_trust_dashboard_unknown_values_do_not_crash
Approvals panel with no decisions
Empty state, not 0 ms
test_trust_dashboard_no_approvals_empty_state
Very large or very small numbers
Formatted readably (units, thousands separators), no overflow
test_trust_dashboard_number_formatting
5.2 Request and error handling
Case
Expected behaviour
Test (proposed)
First load is slow (cold start)
Explicit loading state
test_trust_dashboard_shows_loading_state
Request fails or times out
Error state with retry, never fabricated numbers; previous data (if any) kept and marked stale
test_trust_dashboard_error_state_retry
One panel's data is absent while others are present
Only that panel shows an empty or error state
FR-TD-9
401
Silent refresh, retry once, then hand-off to Sign In
test_trust_dashboard_401_handoff
429
Retry message, data retained as stale
test_trust_dashboard_429_keeps_stale_data
Refresh pressed repeatedly
One in-flight request at a time
test_trust_dashboard_refresh_not_duplicated
Response contains unexpected extra fields
Ignored
test_trust_dashboard_ignores_unknown_fields
Response is not valid JSON or has wrong types
Treated as an error state, not a crash
test_trust_dashboard_malformed_response_handled
Small screen or large text scale
Panels stack or scroll without overflow
test_trust_dashboard_small_screen_large_text
Charts with a single data point or flat data
Render without errors or misleading axes
test_trust_dashboard_single_point_chart
5.3 Week-5 review and merge risks
Case
Expected behaviour
Endpoint not live or contract differs at integration time
Wire against what is agreed, raise the difference with Suraj immediately, fix on D30 if small. If it cannot be resolved, record it as an open item against Gate 3 with a named owner and date, rather than merging mock data as if it were real
A PR conflicts or CI fails on merge day
Fix and re-run the same day; if not possible, record why and carry it with an owner (never silently)
Many PRs queue for Suraj, the only merger
Open and request review early, order PRs by dependency, keep each PR small
Widget-test gap found at the review (a screen with no test)
Add a minimal render and basic-interaction test, or log it against Gate 3
Coverage on Approval Screen or Plan View below 100%
Treated as a blocker for the review, not a note
A bug is found during review
Fix it if small, otherwise file with severity; P0/P1 on core screens must be closed by Gate 4 on 3 Oct
Mock data left in a merged build
Must not happen. Confirm no mock path remains reachable in production builds
6. Acceptance Criteria
6.1 Day 30 completion criteria
ID
Criterion
How verified
D30-1
The Trust Dashboard reads from GET /dashboard/metrics and shows no mock data in the merged build.
Code review; run against the live or staging backend
D30-2
Accuracy, latency, cost (or agreed equivalent), routing/model, MCP health and approvals panels all display real values, or an honest empty state when data is absent.
Manual check against real data, widget tests
D30-3
The response contract (Section 3.3) and the open questions (scope, cost source, "cost ladder") are settled with Suraj and recorded.
PR comment or message
D30-4
The screen reads no service-role-only table directly; only the endpoint is used.
Code review
D30-5
Only aggregates are displayed, with no per-user rows or identifiers from other users.
Code review; D33 audit later
D30-6
trust_dashboard_test.dart exists and passes for FR-WT-1 to FR-WT-5 and the Section 5 edge cases, or exceptions are listed in the PR.
flutter test output
D30-7
test_oauth_connections_shows_correct_connect_state_per_provider exists and passes, or its absence is recorded against Gate 3 with an owner.
flutter test output
D30-8
Loading, empty, error, stale and partial-failure states work, and no state shows fabricated or zero-as-success numbers.
Widget tests
D30-9
CI is green on every Week-5 frontend PR (lint, flutter test, eval smoke subset, build check), and each has Suraj's review.
PR and CI status
D30-10
All Week-5 frontend PRs are merged, or each unmerged PR has a written reason, owner and date.
PR list
D30-11
Coverage report shows 100% for approval_screen.dart and plan_view_screen.dart and at least 80% across screens.
flutter test --coverage
D30-12
The Gate 3 checklist has been run for Ishani's items and for the client-side team, with results recorded.
Review note
D30-13
A one-paragraph docs update (panels, data sources, how to test) and a short Week-5 review summary for Shivangi's weekly report #4 are written.
Docs diff; message to Shivangi
D30-14
No direct pushes to main.
Repository history
6.2 Project-level criteria and gates this work supports
ID
How Day 30 contributes
Gate 3 → Ishani ("Widget tests written for every screen; Trust Dashboard wired")
Completes both halves, once the Trust Dashboard and OAuth Connections tests are in
A7 (widget-test coverage ≥ 80% overall, 100% on Approval Screen and Plan View)
Verified at the review; Trust Dashboard test raises the covered-screen count
A9 (CI blocks merge on any failing test or lint error; zero direct pushes)
Every PR merged today goes through CI and a reviewed merge
A5 (no cross-user leakage)
Dashboard shows aggregates only; reviewed again on D33
G1 / G2 (agent loop that never silently takes a risky action; legible client)
The dashboard makes accuracy, routing and integration health visible to the user
Section 1.3 demo
The demo ends on this screen showing latency, model used and routing rung, so it must show real data by D39
6.3 Gate 3 checklist (Ishani and the client-side team)
Owner
Item
Day 30 check
Ishani
Widget tests written for every screen
Onboarding, Home, Composer (D26); Plan View, Approval Screen (D27); Activity Log (D28); Trust Dashboard and OAuth Connections (today); plus each owner's own screens, as listed in Section 15.2
Ishani
Trust Dashboard wired
D30-1 to D30-8
Jigyasu
STT + push-notification test suites passing
Confirm status with Jigyasu
Sanskriti / Shivangi
Exploratory pass complete on every screen; bugs filed
Confirm status; collect bug list
Suraj
LLM eval, OAuth/JWT, sign-in/sign-up, MCP suites running in CI
Not Ishani's item; note the status for the review
6.4 End-of-day checklist
[ ] Response contract and open questions settled with Suraj
[ ] Trust Dashboard wired; mock data removed from merged build
[ ] Trust Dashboard and OAuth Connections widget tests passing
[ ] All Week-5 frontend PRs reviewed, CI green, and merged (or carried with reason, owner, date)
[ ] Coverage checked against A7
[ ] Gate 3 checklist run and recorded
[ ] Docs paragraph and Week-5 review summary written; summary sent to Shivangi
[ ] Open items listed for Week 6 (D31: UI-side support for the approval-gate bypass e2e test)