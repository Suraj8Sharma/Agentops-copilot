Spec Document
Wire Task Composer to Real POST /tasks
AgentOps Copilot — Build Day 14 (Tue, 8 Sep) • Owner: Ishani
Source: AgentOps_Implementation_Manual.docx — Section 14 (Day-by-Day Plan), Section 10 (API Reference), Section 7 (Database Schema), Section 16.3 (Definition of Done), Section 18 (Acceptance Criteria)
1. Problem Statement
Since Day 5, the Task Composer screen (owned by Ishani) has existed as a text/voice entry point UI running against mock data — a user can type into it, but nothing is actually persisted or acted on. In parallel, the backend has progressed independently: the tasks table and the POST /tasks endpoint went live on Day 11 (Suraj), and the LangGraph planning skeleton — intent-classify → plan → risk-tag nodes — landed on Day 13. Day 14 is the point where these two tracks connect on the task-creation path: Ishani wires the Task Composer's submit action to the real POST /tasks endpoint instead of a mock response.
Concretely: today, submitting a task in the Composer does not create a row in the tasks table, does not trigger the LangGraph run, and is invisible to every other screen that depends on real task data (Home/Dashboard's GET /tasks, wired Day 13; Agent Plan View, wired Day 15). The task is to remove that mock boundary for the text-input path so a submitted task is real, persisted, RLS-scoped to the authenticated user, and visible elsewhere in the app immediately after submission.
Note: Day 14's plan explicitly keeps voice-mode wiring separate — Jigyasu's Day 15 row is "Wire real transcription into Task Composer voice mode." This spec therefore scopes Ishani's Day 14 work to the text-input submission path; voice submission continues against mock/disabled behaviour until Day 15–16.
2. Functional Requirements
2.1 Core behaviour
1.	On tapping Submit in text mode, the Composer sends a POST /tasks request carrying the user's typed input, with the authenticated user's JWT attached as a Bearer token (per Section 5.1's JWT-verification dependency, which every non-public route sits behind).
2.	The request body sets input_type = "text" and raw_input to the exact text entered by the user.
3.	While the request is in flight, the screen shows a visible loading/submitting state and disables the Submit control to prevent duplicate taps.
4.	On a successful response, the Composer treats the task as created (status = submitted) and returns the user to a state where they can see it reflected — either by navigating to Home/Dashboard or by triggering the task list (already wired to GET /tasks on Day 13) to refresh so the new task appears without an app restart.
5.	On failure, the screen surfaces a clear, non-silent error state and leaves the user's typed input intact so they can retry — consistent with the manual's architecture principle that failures are surfaced, never silent (Section 1.2, "Auditability by construction").
6.	Voice mode remains on mock behaviour / disabled for real submission on Day 14; only the text-input path is wired to the live endpoint.
2.2 Client-side validation
●	Submit is disabled (or blocked) when the input is empty or whitespace-only — no request is sent for empty input.
●	Submit is disabled while a previous submission for the same input is still in flight.
3. API Contract
As defined in Section 10 (Backend API Reference) and Section 7.2 (tasks table). This is the only endpoint this Day-14 task wires; GET /tasks, GET /tasks/{id}, and GET /tasks/{id}/plan are consumed by other screens on other days (Home/Dashboard — Day 13; Agent Plan View — Day 15).
3.1 POST /tasks
Field	Value
Method / Path	POST /tasks
Auth	JWT (Bearer token) — required; every route is behind the JWT-verification dependency except the two marked Public in Section 10
Purpose	Submit a new text or voice task; kicks off the LangGraph run (Section 10)

3.2 Request body
Derived from the tasks table columns (Section 7, Group B — Task Orchestration) that are client-suppliable at creation time. user_id, id, status, created_at, and completed_at are server-assigned and are not part of the request.
{
  "input_type": "text",        // "text" | "voice" — this task wires "text" only
  "raw_input": "string"        // required for input_type = "text"; the user's typed input
}
3.3 Success response — 201 Created
Shape inferred from the tasks table schema (Section 7). The manual does not print a literal JSON example for this endpoint, so field names/types below are taken directly from the table's column definitions.
{
  "id": "uuid",
  "user_id": "uuid",
  "input_type": "text",
  "raw_input": "string",
  "transcription_text": null,
  "status": "submitted",         // tasks.status default, per Section 7.2
  "created_at": "timestamptz",
  "completed_at": null
}
Assumption flagged: the manual states POST /tasks "kicks off the LangGraph run" but does not specify whether the HTTP response waits for planning to finish. Given the free-tier latency constraints in Section 2.3 (Groq/Gemini rate limits, Render cold starts) and that Home/Dashboard already polls via GET /tasks, this spec assumes POST /tasks returns immediately with status = submitted, and later status transitions (planning → awaiting_approval → executing → completed/failed) are observed by re-fetching GET /tasks or GET /tasks/{id} — not by the Composer waiting on the original request. Confirm this with Suraj before implementation if not already documented elsewhere.
3.4 Error responses
Status	Meaning	Client handling
401	Missing/expired/tampered JWT	Attempt token refresh (existing flow, Section 15.4); if refresh fails, route to Sign In
422	Validation failure (e.g. empty raw_input)	Should not occur if client-side validation runs first; if received, surface inline field error
5xx	Backend/Render/Supabase failure	Show a visible retry-able error; never fail silently (Section 1.2)

4. Constraints
●	Text-mode only. Voice submission through Task Composer is out of scope for Day 14 — the STT pipeline is wired to the Composer on Day 15 (Jigyasu) and its error states (permission, timeout, retry) on Day 16.
●	Backend maturity: the tasks table and POST /tasks endpoint are live since Day 11, and the LangGraph planner only reached intent-classify → plan → risk-tag on Day 13 (the day before this task). The approval_gate and execute nodes are not confirmed complete at this point in the schedule, so a submitted task may legitimately sit at submitted/planning without progressing further — that is expected backend state on Day 14, not a Composer wiring bug.
●	Every non-public route sits behind the JWT-verification dependency (Section 5.1) — the Composer must attach a valid Bearer token to every request, and must reuse the existing JWT refresh handling rather than re-implementing it.
●	Row-level security: tasks.user_id is scoped by user_id = auth.uid() (Section 7.2). The client never needs to (and must not attempt to) pass user_id in the request body — it is derived server-side from the JWT.
●	Free-tier architecture (Section 2.3): Render's free-tier service cold-starts after inactivity, adding tens of seconds of latency to the first request. The Composer must show an explicit loading state rather than a spinner that reads as a hang — this is the same handling pattern the manual specifies for the Day-39 demo warm-up.
●	Definition of Done (Section 16.3) applies: code merged via a reviewed PR; flutter test coverage for the new submit flow exists and passes; fail-closed/fail-open behaviour is verified for this user-facing path; logging is present if this path touches the agent loop (task creation does); one paragraph of docs is written the same day.
5. Edge Cases & Error Handling
1.	Empty or whitespace-only input — blocked client-side; no request is sent; Submit stays disabled.
2.	Double-submit (user taps Submit twice, or a slow network causes a retry tap) — Submit is disabled for the duration of the in-flight request to prevent duplicate task rows. The manual's idempotency-key pattern (Section 8.2 / "Retries, Idempotency & Multi-Step Ordering") is documented for MCP tool-call steps (plan_id:step_index), not explicitly for POST /tasks — treat client-side submit-locking as the Day-14 mitigation and flag true request-level idempotency as an open question for Suraj.
3.	JWT expired at submit time — trigger the existing refresh flow (test_jwt_refresh_issues_new_access_token, Section 15.4) transparently before retrying the submit; if refresh itself fails, route to Sign In rather than surfacing a raw 401.
4.	Render cold start on first submit after inactivity — request may take tens of seconds; show the explicit loading state described in Section 2.3 rather than letting the UI look frozen; consider a timeout with a distinct "still working" message rather than an indefinite spinner.
5.	Backend/network failure (5xx, timeout, offline) — show a visible, retry-able error; preserve the user's typed input so nothing is lost; never silently drop the submission.
6.	Task created but not yet reflected elsewhere — after a successful 201, the Home/Dashboard task list (GET /tasks) must be refreshed or updated so the new task is visible without a manual app restart, since that screen was already wired to real data on Day 13.
7.	Voice mode selected before its real wiring lands — voice submission must not call the real POST /tasks endpoint yet; keep it on mock/disabled behaviour consistent with the Day 15/16 dependency, rather than sending a request the backend voice pipeline isn't ready to support end-to-end.
8.	Backend planning stalls after creation (e.g. Groq/Gemini rate-limited, Section 2.3) — this is invisible to the Composer itself: the screen's responsibility ends at a successful 201/submitted status, not at task completion. It should not block or spin waiting for the LangGraph run to finish.
9.	No documented request-size or raw_input length limit — flagged as an open question; until confirmed, apply a reasonable client-side cap and rely on backend validation (422) as the ultimate guard.
6. Acceptance Criteria
Task-level criteria for Day 14, combining the plan-level requirement ("Wire Task Composer to real POST /tasks", Section 14) with the standing Definition of Done (Section 16.3) and the project-wide Acceptance Criteria this task feeds into (Section 18).
●	Submitting non-empty text in the Composer creates a real row in the tasks table via POST /tasks (verifiable against Supabase) — not a mock response.
●	The created task carries input_type = "text", the exact raw_input the user entered, and status = submitted.
●	The new task appears in the Home/Dashboard task list (GET /tasks) after submission, without requiring an app restart.
●	Empty/whitespace input is blocked client-side; no request is sent.
●	An expired/invalid JWT is handled via the existing refresh flow rather than crashing the screen or silently failing.
●	A backend error (4xx/5xx) results in a visible, retry-able error state — never a silent failure or a frozen UI.
●	A loading state is visible between submit and response, including on a Render cold start.
●	Voice-mode submission is not wired to the real endpoint on Day 14 — it remains scoped out per the Day 15/16 dependency.
●	Code is merged to main via a reviewed PR; flutter test coverage exists for the submit flow and passes; fail-closed/fail-open behaviour on this user-facing path is verified; one paragraph of docs is written the same day (Section 16.3).
●	Contributes toward project Acceptance Criterion A4 — sign-up to first completed task in under 3 minutes in usability testing — and A9 — CI blocks merge on any failing test or lint error (Section 18).

Items marked as assumptions or open questions above are not explicitly stated in the Implementation Manual and should be confirmed with Suraj (backend owner) before or during implementation.


