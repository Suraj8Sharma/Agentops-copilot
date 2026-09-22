Day 13 Spec — Wire Home/Dashboard to Real GET /tasks

Project: AgentOps Copilot — MCP-native multi-agent personal assistant Owner: Ishani (Frontend Design Lead & Trust Surfaces) Day / Date: D13 — Monday, 7 September 2026 Task (from Day-by-Day Plan, Section 14): "Wire Home/Dashboard to real GET /tasks" Week: Week 3 (7–12 Sep) — "core screens wired" phase begins Source: AgentOps Copilot Technical Implementation Manual v2.0

1. Problem Statement

Through Weeks 1–2, the Home/Dashboard screen was built and frozen (D4, D12) against mock task data only — by design, per Section 13's frontend/backend pattern: screens ship first against mocks while backend infrastructure comes online, then get wired to real endpoints once both sides are ready.

Week 3 is that turning point. Suraj's tasks/task_plans/plan_steps tables and the POST /tasks endpoint went live on D11; the GET /tasks route exists in the Backend API Reference (Section 10) as the one that lists the user's tasks with status. Day 13's job is to replace Home/Dashboard's mock data source with a real, authenticated call to GET /tasks, so the screen shows a real, live, per-user task list for the first time — the anchor screen for Goal G2 ("a user can always see what the agent is about to do") and a direct dependency for Acceptance Criterion A4 (sign-up to first completed task in under 3 minutes), since Home/Dashboard is the "quick-entry point and status at a glance" screen a user lands on immediately after signing in.

2. Functional Requirements
#	Requirement	Detail
FR1	Replace the mock data source on Home/Dashboard with a live call to GET /tasks.	Request must carry the user's JWT access token (Section 5.1); no route on this call is public.
FR2	Render the returned task list with each task's status visible at a glance.	Status must map to one of the seven values in the tasks table: submitted | planning | awaiting_approval | executing | completed | failed | cancelled — each needs a distinct visual treatment.
FR3	Preserve the existing "quick-entry point" affordance on the screen (entry point into Task Composer) — wiring the list must not regress the composer shortcut.	UI/navigation only; no backend change required here.
FR4	Silent token refresh must not interrupt the task-list fetch.	Per Section 5.1, the Flutter app refreshes the JWT silently before expiry — Home/Dashboard should not show an error or blank state due to a routine refresh mid-fetch.
FR5	Show an explicit, non-broken-looking loading state while the request is in flight.	Required specifically because of the Render free-tier cold-start constraint (Section 2.3) — see Constraints below.
FR6	Update or extend the existing widget test for Home/Dashboard to cover the real-data path (success, loading, empty, error), not just the mock-data render.	Frontend Widget Tests (Section 15) require every screen to "render correctly"; this is now judged against live data shapes.
FR7	PR opened and merged through the normal flow (Suraj sole merger, required review, CI green).	Section 12.
3. API Contract

Endpoint: GET /tasks Auth: JWT (Bearer token in Authorization header) — verified against Supabase's JWKS via the backend's JWT-verification dependency (Section 5.1). Not one of the two public routes. Purpose (Section 10): List the user's tasks with status.

Response — task object shape (per the tasks table, Section 7, Group B):

Field	Type	Notes
id	uuid	Primary key
user_id	uuid	Implicit — scoped server-side via RLS (user_id = auth.uid()); not something the client needs to filter by
input_type	text	text | voice
raw_input	text	User's original text, or empty for voice
transcription_text	text, nullable	STT output for voice input
status	text	submitted | planning | awaiting_approval | executing | completed | failed | cancelled
created_at	timestamptz	
completed_at	timestamptz, nullable	

Row-level security: Postgres RLS restricts every row returned to user_id = auth.uid() — the client never needs to (and cannot) request another user's tasks; a well-formed request with a valid JWT for user A can only ever return user A's rows.

Error handling contract: the backend follows the same typed-error convention used elsewhere in the system (Section 8.2's error field: typed error code + human-readable message) — Home/Dashboard should surface the message, not a raw stack trace or generic "something went wrong," on any non-2xx response.

4. Constraints
JWT on every call: GET /tasks sits behind the JWT-verification dependency (Section 5.1) — there is no unauthenticated fallback path for this screen.
Render free-tier cold starts (Section 2.3): a Render web service that has spun down pays a cold-start penalty of tens of seconds on the next request, which "reads as a hang to a first-time user." Home/Dashboard's loading state must be an explicit, purpose-built loading indicator, not a bare spinner that looks broken during a cold start.
Supabase free-tier connection limits (Section 2.3): the fetch should go through the existing pooled connection path already set up server-side; this is a backend concern but shapes expectations on retry behavior (don't hammer the endpoint with aggressive client-side retries).
Design-system lock-in: the wired screen must keep using theme.dart tokens established at shell-freeze (D12) — this is a data-source swap, not a redesign.
Sole merger / branch protection: merge only via PR, one required review, all CI checks green (Section 12).
Scope boundary: Day 13 wires read-only display of the task list. It does not touch POST /tasks (Task Composer's job, D14) or the Agent Plan View drill-down (D15) — those are separate, sequenced wiring days.
5. Edge Cases & Error Handling
Empty state: a brand-new user with zero tasks must see a real empty state (not a loading spinner stuck indefinitely, not a blank screen) — this was already anticipated as a shell-stage requirement at D12 and now needs real-data confirmation.
Cold-start delay: if the backend is asleep, the loading state must persist gracefully through a multi-second (potentially 10s+) wait without implying the app has frozen — directly required by Section 2.3.
Token expiring mid-fetch: if the JWT refreshes silently during the request lifecycle, the screen must not surface a spurious 401/error to the user (FR4).
Non-2xx / network failure: any failed fetch must show the typed, human-readable error message (Section 8.2 convention) with a way to retry — never a raw exception or a permanently blank list.
All seven task statuses must be visually distinguishable: submitted, planning, awaiting_approval, executing, completed, failed, and cancelled each need a clear, at-a-glance treatment — a user should never have to guess what "in progress" means among these.
Stale/partial data on rapid re-entry: if a user backgrounds and quickly reopens the app, the dashboard should refetch rather than show a stale cached list indefinitely (no caching layer is specified in the manual for this screen, so treat each screen-open as a fresh GET /tasks call unless a pull-to-refresh/caching pattern is separately agreed with Suraj).
6. Acceptance Criteria
Live data confirmed: Home/Dashboard displays a real, per-user task list fetched from GET /tasks — verified by creating a task as one test user and confirming it does not appear for a second test user (RLS isolation, consistent with Section 15's Security/RLS Tests row and Acceptance A5's zero-cross-user-leakage bar).
Status rendering complete: all seven tasks.status values render with distinct, correct visual treatment.
Loading state passes the cold-start test: manually simulate a cold Render instance and confirm the loading state reads as "working," not "broken," for the duration of the delay (Section 2.3).
No regression in navigation: the quick-entry point to Task Composer still works from the wired screen.
Widget tests updated and passing: Home/Dashboard's test suite covers success, loading, empty, and error paths against the real contract, contributing to the ≥80% widget-test-coverage bar in Acceptance A7.
A4 dependency intact: as part of the sign-up → first completed task flow, Home/Dashboard's real-data load does not itself become the bottleneck pushing that flow over the 3-minute target (Acceptance A4) — flagged here for awareness even though A4 is measured end-to-end later, not on D13 in isolation.
PR merged: change lands on main via Suraj, required review satisfied, CI (lint + test + eval-smoke + build) green (Section 12).
Content
