
Spec Document
Wire Agent Plan View to Real task_plans / plan_steps Data
AgentOps Copilot — Build Day 15 (Wed, 9 Sep) · Owner: Ishani
Source: AgentOps_Implementation_Manual.docx — Section 14 (Day-by-Day Plan), Section 10 (API Reference), Section 7 (Database Schema), Section 9 (Risk & Approval Gate), Section 16.3 (Definition of Done), Section 18 (Acceptance Criteria)
1. Problem Statement
The Agent Plan View screen (owned by Ishani) has existed since Day 7 as a step-by-step visualisation UI running against mock data — it can render a fake plan, but it doesn't show what the agent actually intends to do for a real task. On the backend side, Day 11 brought the tasks / task_plans / plan_steps tables and POST /tasks live, and Day 13 added the LangGraph planning skeleton (intent-classify → plan → risk-tag nodes), so a submitted task now produces a real, risk-tagged plan sitting in Postgres. Day 14 connected task creation itself (Task Composer → POST /tasks). Day 15 is the next link in that chain: Ishani wires the Plan View to the real GET /tasks/{id}/plan endpoint so a user can see the actual ordered plan_steps for their task — tool, MCP server, risk tier, and status — instead of a mock.
This matters more than an average screen-wiring task because Plan View is explicitly one of only two screens in the whole app held to a 100%-coverage, never-mis-render bar (Section 15.2), and it is the concrete mechanism behind Goal G2 — "a user can always see what the agent is about to do and why, before it happens." A mis-rendered or stale plan here is treated as a safety bug, not a cosmetic one.
Note: by Day 15, the LangGraph graph only extends through intent-classify → plan → risk-tag (built Day 13); the execute node, the approvals endpoint, and approval-gate enforcement land Day 16–17. So the real plan_steps this screen renders will be risk-tagged but, for anything requires_approval, not yet actionable end-to-end from within the app — Plan View's Day-15 job is to render the plan accurately, not to drive execution or approval.
2. Functional Requirements
2.1 Core behaviour
On opening Plan View for a given task, the screen fetches GET /tasks/{id}/plan with the authenticated user's JWT attached as a Bearer token, replacing the existing mock plan data.
The screen renders the ordered plan_steps for the task's active task_plan, in step_index order, so the sequence on screen always matches the sequence the agent will execute — this ordering is exactly what test_plan_view_renders_all_steps_in_order (Section 15.2) checks.
Each step displays, at minimum, its tool_name, mcp_server, and risk_tier (low / medium / high), so the user can see what the agent intends to do and how risky each part is, per the worked example in Section 1.3 (a low-risk calendar event alongside a high-risk email send in the same plan).
Each step reflects its current plan_steps.status (pending | awaiting_approval | approved | rejected | executing | done | failed) — the screen shows real status, not an assumed one, since execution for later steps may already be underway by the time the user opens the screen.
A visible loading state is shown while the plan is being fetched, and an explicit empty/waiting state is shown if the task has no task_plans row yet (e.g. the planner node hasn't finished for a just-submitted task).
On fetch failure, the screen surfaces a clear, non-silent error state — silent failure is unacceptable on a safety-critical screen (Section 1.2, "Auditability by construction").
2.2 Out of scope for Day 15
Approving or rejecting a step from this screen — that is the Approval Screen's job, wired Day 16 against the approvals endpoint (Section 14).
Triggering execution — the execute node and approval-gate enforcement are not live until Day 16–17 (Section 14); Plan View only displays state, it never drives it.
Voice-originated tasks are already covered by the same GET /tasks/{id}/plan contract (input_type doesn't change the plan shape), but end-to-end voice submission itself isn't wired until Day 15/16 on Jigyasu's track — Plan View's wiring does not depend on that.
3. API Contract
As defined in Section 10 (Backend API Reference) and Section 7 (task_plans and plan_steps tables, Group B — Task Orchestration). This is the only endpoint this Day-15 task wires; POST /tasks (Day 14) and the approvals endpoints (Day 16–17) are consumed elsewhere.
3.1 GET /tasks/{id}/plan
Field
Value
Method / Path
GET /tasks/{id}/plan
Auth
JWT (Bearer token) — required; every route is behind the JWT-verification dependency except the two marked Public in Section 10
Purpose
Full task_plans + plan_steps for the Agent Plan View (Section 10)


3.2 Success response — 200 OK
Shape inferred from the task_plans and plan_steps table columns (Section 7, Group B). The manual does not print a literal JSON example for this endpoint, so field names/types below are taken directly from the schema. task_plans.plan_json holds the planner's raw ordered step list; plan_steps is the normalised, per-step row set this screen should actually render from, since it alone carries live status and output per step.
{
  "task_plan": {
    "id": "uuid",
    "task_id": "uuid",
    "planner_version": "string",
    "status": "active",        // draft | active | superseded
    "created_at": "timestamptz"
  },
  "plan_steps": [
    {
      "id": "uuid",
      "plan_id": "uuid",
      "step_index": 0,
      "tool_name": "calendar.create_event",
      "mcp_server": "calendar",         // calendar | gmail | github | slack
      "input_params": { "...": "..." },
      "risk_tier": "medium",            // low | medium | high
      "requires_approval": false,
      "status": "pending",              // pending | awaiting_approval | approved |
                                        // rejected | executing | done | failed
      "output": null,
      "executed_at": null
    }
  ]
}
Assumption flagged: the manual specifies the table columns for task_plans and plan_steps (Section 7) and states the endpoint returns "full task_plans + plan_steps," but does not print the exact response envelope. The nested { task_plan, plan_steps } shape above is a reasonable reading of "full task_plans + plan_steps" — confirm the literal wire shape with Suraj (e.g. whether it's this nested object or two flat arrays) before finalising the Flutter model classes.
3.3 Error responses
Status
Meaning
Client handling
401
Missing/expired/tampered JWT
Attempt token refresh (existing flow, Section 15.4); if refresh fails, route to Sign In
404
Task exists but has no task_plans row yet (planner hasn't run/finished)
Treat as a normal "plan not ready yet" state, not an error — show the waiting state from FR6, not an error banner
403 (implicit via RLS)
Task belongs to another user
Should be unreachable from normal navigation; if received, treat as a generic error state — never render another user's plan
5xx
Backend/Render/Supabase failure
Show a visible retry-able error; never fail silently (Section 1.2)


4. Constraints
Read-only screen. Plan View only fetches and renders; it must not write to task_plans or plan_steps, and must not call the (not-yet-built) approvals endpoint — that boundary belongs to the Approval Screen, Day 16.
Backend maturity: by Day 15, the LangGraph graph covers intent-classify → plan → risk-tag only (Section 14, Day 13); execute, approval-gate enforcement, and the approvals table/endpoint are Day 16–17 work. Rendering plan_steps whose status stays at pending or awaiting_approval indefinitely is expected backend state on Day 15, not a Plan View bug.
Safety-critical coverage bar: Plan View is one of two screens (with Approval Screen) held to 100% widget-test coverage and a golden-file (pixel-level reference image) test, because a silent mis-render here is classified as a safety bug (Section 15.2).
Re-planning creates a new task_plans row rather than overwriting the old one (Section 7, task_plans.status: draft | active | superseded) — the screen must fetch and render the active plan, not assume a task has exactly one plan ever.
Row-level security: plan_steps and task_plans are join-based tables scoped via plan_id → task_plans → tasks.user_id = auth.uid() (Section 7) — the client never needs to (and must not attempt to) pass user_id; access is enforced server-side.
Every non-public route sits behind the JWT-verification dependency (Section 5.1) — reuse the existing JWT/refresh handling already used for GET /tasks (Day 13) and POST /tasks (Day 14) rather than reimplementing it here.
Free-tier architecture (Section 2.3): Render's free-tier service cold-starts after inactivity. The screen must show an explicit loading state on fetch rather than a spinner that reads as a hang.
MCP servers are only partially live at this point in the schedule — Calendar since Day 14, Gmail as of Day 15 itself; GitHub and Slack land Day 16–17 (Section 14). Steps with mcp_server = github or slack may appear in a plan (the planner isn't gated by MCP readiness) but should render with the same generic step UI — no special-casing that assumes only Calendar/Gmail steps exist.
Definition of Done (Section 16.3) applies: code merged via a reviewed PR; flutter test coverage for this screen's real-data path exists and passes; fail-closed/fail-open behaviour is verified for this user-facing, risk-relevant path; logging is present since this path is on the agent loop; one paragraph of docs is written the same day.
5. Edge Cases & Error Handling
Task has no task_plans row yet (planner still running or hasn't started) — show an explicit "plan not ready yet" waiting state, not an error and not a blank screen; this is a normal transient state, especially given Render cold-start latency (Section 2.3).
Plan exists but has zero plan_steps — render a clear empty state rather than a blank list; flag as worth confirming with Suraj whether this is a valid planner outcome or should never occur.
A step's risk_tier/requires_approval doesn't match the seeded risk_rules table (Section 9.1) at a glance (e.g. an unexpected action_type shows high/true) — this is the fail-closed default working as intended (Section 9.2: no matching risk_rules entry → high risk, requires_approval = true), not a data bug; the screen should render it exactly as returned, without trying to "correct" it.
Re-planning mid-view — because a new plan is a new task_plans row rather than an overwrite (Section 7), a plan open on screen could be superseded while the user is looking at it. Define whether Day 15's scope includes live-refresh on this (e.g. pull-to-refresh) or whether it's explicitly deferred; if deferred, the screen should still never silently show a stale superseded plan as if it were active — flag as an open question for scope confirmation.
Steps whose mcp_server isn't live yet (github, slack — Day 16/17) can still appear in a fetched plan — render them with the same generic step UI; do not assume every step belongs to a currently-wired MCP server.
JWT expired while viewing — trigger the existing refresh flow (test_jwt_refresh_issues_new_access_token, Section 15.4) transparently; if refresh fails, route to Sign In rather than surfacing a raw 401 on a safety-critical screen.
Render cold start on first open after inactivity — request may take tens of seconds; show the explicit loading state from Section 2.3 rather than a spinner that looks broken.
Backend/network failure (5xx, timeout, offline) — show a visible, retry-able error; never fail silently, and never fall back to rendering stale mock data in place of a real error.
Attempting to view another user's task/plan (e.g. a stale deep link) — RLS should make this unreachable server-side; the client must not render partial or cached data in this case and should fall back to a generic error/not-found state.
6. Acceptance Criteria
Task-level criteria for Day 15, combining the plan-level requirement ("Wire Agent Plan View to real task_plans/plan_steps data", Section 14) with the standing Definition of Done (Section 16.3) and the project-wide Acceptance Criteria this task feeds into (Section 18).
Opening Plan View for a real task fetches and renders its actual plan_steps via GET /tasks/{id}/plan — not mock data.
Steps render in step_index order, matching test_plan_view_renders_all_steps_in_order (Section 15.2).
Each step visibly shows tool_name, mcp_server, risk_tier, and current status, sourced directly from the API response.
A task with no plan yet shows an explicit waiting state, not an error or a blank screen.
A fetch failure (401/404/5xx) results in a visible, non-silent, appropriately differentiated state per the table in Section 3.3 — never a silent failure or a frozen UI.
A loading state is visible between screen-open and data arriving, including on a Render cold start.
The screen never writes to task_plans/plan_steps and never calls the approvals endpoint — it remains strictly read-only, consistent with Day 16 owning approval actions.
Widget-test coverage for Plan View reaches the 100% bar specified for this screen, including a golden-file test (Section 15.2).
Code is merged to main via a reviewed PR; fail-closed/fail-open behaviour on this path is verified; one paragraph of docs is written the same day (Section 16.3).
Contributes toward project Acceptance Criterion A7 — widget-test coverage ≥80% overall, 100% on Approval Screen and Plan View — and supports G2's measurement that a user can always see what the agent is about to do and why (Section 1.1, 18).

Items marked as assumptions or open questions above are not explicitly stated in the Implementation Manual and should be confirmed with Suraj (backend owner) before or during implementation.

