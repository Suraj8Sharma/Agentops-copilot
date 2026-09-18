Spec: Week-3 Review & PR Merge — Core Loop UI Wired End-to-End

Owner: Ishani · Day: D18, Sat 12 Sep · Week 3 close (7–12 Sep)

Derived from the AgentOps Implementation Manual (§13 Working Rhythm, §12 CI/CD, §6 Page Inventory, §7 Data Model, §10 API Reference, §9 Approval Gate, §15.2 Widget Testing, §16.3 Definition of Done, §18 Acceptance Criteria). Points not stated verbatim in the manual are marked [interpreted].

1. Problem Statement

Week 3 (7–12 Sep) is the week the Flutter client stops running on mock data. Across D13–D16, Ishani wired four screens to real backend endpoints one at a time: Home/Dashboard → GET /tasks (D13), Task Composer → POST /tasks (D14), Agent Plan View → real task_plans/plan_steps (D15), Approval Screen → the real approvals endpoint (D16). Each landed as an isolated wiring task against whichever backend piece had just come online.

D18 is the Saturday review-and-merge day (§13: "Saturday of every week is a review + PR-merge day — whatever is in flight gets wrapped up and merged rather than carried forward silently"). Ishani's deliverable is not a new feature: it is proving that those four separately-wired screens work as one continuous user journey against the live backend, and getting that state merged to main.

This matters because the same day Suraj freezes the orchestration core ("Week-3 PR merge — orchestration core frozen"). Anything not merged on D18 gets wired against a moving backend next week instead of a frozen one. It also sets up Gate 2 (19 Sep), where the standing requirement is "Home, Composer, Plan View, Approval Screen, OAuth Connections wired to real data."

Explicitly not in scope for D18: OAuth Connections wiring (D21, since Suraj's OAuth layer only froze at D12 and the screen wiring is scheduled separately), Trust Dashboard wiring (D30), and the notification-banner model work from D17 (independent track).

2. Functional Requirements
FR1 — End-to-end core loop runs against real data. A single task must flow through the wired screens without dropping to mock data at any point: Composer submits → Home reflects status → Plan View renders the real plan → Approval Screen surfaces the flagged step → decision recorded → task completes → Home reflects completion.
FR2 — Home/Dashboard consumes GET /tasks. Renders the user's real task list with live status values (submitted | planning | awaiting_approval | executing | completed | failed | cancelled).
FR3 — Task Composer submits via POST /tasks. Text-mode submission kicks off the real LangGraph run and returns a task the UI can follow. (Voice mode is Jigyasu's D15 integration; Composer must accept it without breaking.)
FR4 — Agent Plan View renders real plan data. Steps drawn from task_plans.plan_json / plan_steps, in step_index order, showing tool_name, mcp_server, risk_tier, and per-step status.
FR5 — Approval Screen renders real pending approvals. Surfaces steps where requires_approval = true and status = awaiting_approval, displays explanation_text as advisory copy, and posts an approve/reject decision.
FR6 — State transitions propagate across screens. A decision made on the Approval Screen must be reflected in Plan View step status and Home task status without requiring a manual app restart. [interpreted — implied by "wired end-to-end", not stated as a line item]
FR7 — Week-3 review conducted. Ishani reviews the week's client-side work, including the screens built by the reports who roll up to her on client-side work (Jigyasu, Sanskriti, Shivangi).
FR8 — PR merged to main. All in-flight Week-3 UI work is merged via reviewed PR — not carried into Week 4 silently.
FR9 — Definition of Done satisfied per §16.3 for every task merged: code merged via reviewed PR, tests exist and pass, linters clean, fail-closed behaviour verified on risk-relevant paths, one paragraph of docs written the same day.
3. API Contract

No new endpoints are authored on D18. The contract is the set of already-live routes the wired screens consume — all behind the JWT-verification dependency (§5.1), and all subject to RLS (user_id = auth.uid()).

Screen	Method	Path	Consumes
Home / Dashboard	GET	/tasks	Task list with status
Task Composer	POST	/tasks	Submits text/voice task, kicks off LangGraph run
Home → detail	GET	/tasks/{id}	Task detail incl. plan and step statuses
Agent Plan View	GET	/tasks/{id}/plan	Full task_plans + plan_steps
Approval Screen	GET	/approvals/pending	Steps awaiting this user's decision
Approval Screen	POST	/approvals/{step_id}	Records approve/reject; resumes the LangGraph checkpoint

Key field shapes the UI must handle (from §7):

tasks.status — submitted | planning | awaiting_approval | executing | completed | failed | cancelled
plan_steps — step_index, tool_name, mcp_server (calendar | gmail | github | slack), risk_tier (low | medium | high), requires_approval, status (pending | awaiting_approval | approved | rejected | executing | done | failed), output
task_plans.status — draft | active | superseded (re-planning creates a new row; the UI must render the active plan, not a superseded one)
approvals — decision (approved | rejected), explanation_text (advisory display only), response_time_ms (feeds the Trust Dashboard)

Merge contract (§12): every PR runs lint (ruff + dart analyze) → unit tests (pytest + flutter test) → smoke subset of the eval suite → build check. All four must pass. Branch protection on main: no direct pushes, one required review, all checks green. Suraj is the sole merger — Ishani prepares and reviews, Suraj merges.

4. Constraints
Suraj is the sole merger for the whole repository. Ishani cannot self-merge; the PR must be review-ready in time for Suraj's merge window on the same day.
Same-day freeze dependency. Suraj freezes the orchestration core on D18. UI work merged after that freeze is wired against a moving target — this is the reason the merge is dated, not optional.
Advisory/decision separation (§9). The Approval Screen displays explanation_text, but nothing in the UI may make or influence the risk decision — risk_rules alone governs that. The client must never be able to auto-approve or bypass the gate.
Free-tier backend behaviour (§2.3). Render free-tier cold starts cost tens of seconds; the Flutter client must show an explicit loading state rather than a spinner that reads as broken. Groq/Gemini rate limits mean plan generation latency is variable, not fixed.
Screen ownership boundary. Only the four core-loop screens are Ishani's wiring scope here; the review covers her reports' work but does not make her responsible for building it.
Coverage floor (A7 / §15.2). 80% widget-test coverage overall, 100% on Approval Screen and Plan View — those two additionally carry golden-file (pixel-reference) tests, since a silent mis-render there is a safety bug, not a cosmetic one.
A9 — zero direct pushes to main across the whole project; CI blocks merge on any failing test or lint error.
5. Edge Cases & Error Handling
Case	Expected Handling
Render cold start on first request of the day	Explicit loading state, never an error or a stalled spinner (§2.3; test_render_cold_start_shows_loading_state_not_error).
Task has no plan yet (status = planning)	Plan View shows a pending/generating state rather than an empty screen or an error. [interpreted]
Plan re-generated mid-task (task_plans.status = superseded)	UI renders the active plan; a superseded plan must not be shown as current.
Multi-step plan with mixed risk tiers	Low-risk steps auto-execute and show as progressing; high-risk steps hold at awaiting_approval — ordering must render correctly (test_mixed_risk_multi_step_plan_orders_correctly).
Approval rejected	Task halts with no side effects; Plan View and Home must both reflect the halt, not show a stuck "executing" state (test_rejected_approval_halts_task_with_no_side_effects).
App closed mid-approval, reopened	The pending approval is still surfaced and the task resumes on decision (test_task_resumes_after_app_closed_mid_approval).
Any client path that could reach execution without approval	Must be blocked — test_approval_screen_never_auto_approves, and the gate-level test_approval_gate_bypass_attempt_always_fails (A2, zero tolerance).
OAuth token expired mid-task	Step fails with a clear re-auth reason; UI surfaces a re-auth prompt, never a silent failure (§5.2, A3). Gmail draft steps degrade to "saved, not sent".
MCP server down	Task marked failed, not left hanging (test_mcp_server_down_marks_task_failed_not_hung) — the UI must show failed, not an indefinite spinner.
Empty task list (new user)	Home renders an empty state. [interpreted — explicit empty/error states are scheduled for other owners' screens; not stated for Home]
Week-3 work not finish-able by end of D18	Sunday is the designated buffer/rest day for slippage (§13) — but the manual's stated intent is that in-flight work is merged, not carried forward silently. Escalate rather than defer quietly.
6. Acceptance Criteria
AC1: A complete core-loop task runs end-to-end against the live backend — submit via Composer, plan renders in Plan View, high-risk step surfaces on the Approval Screen, approve, task completes, Home shows the completed status. No screen falls back to mock data at any point.
AC2: The manual's own demo scenario (§1) is reproducible: a two-step task where one step is low-risk and auto-executes and one is high-risk and requires approval, with both steps visible and correctly ordered in Plan View.
AC3: A rejected approval halts the task cleanly, with no side effects and no stuck state in the UI.
AC4: Widget tests pass for the wired screens, including test_plan_view_renders_all_steps_in_order, test_approval_screen_renders_risk_explanation (golden test), and test_approval_screen_never_auto_approves; Approval Screen and Plan View are at 100% coverage (A7).
AC5: CI is green on the PR — lint (ruff + dart analyze), unit tests (pytest + flutter test), eval smoke subset, and build check all pass (§12).
AC6: PR merged to main by Suraj on D18; no direct pushes (A9). Debug APK builds and lands on Firebase App Distribution so the team is testing the wired build.
AC7: Week-3 review completed across client-side work, with any carry-over into Week 4 explicitly named rather than silently deferred.
AC8: Definition of Done met per §16.3 for each merged task, including the same-day paragraph of module/README docs.
AC9: Week-3 exit state supports Gate 2 (19 Sep): four of the five required screens are wired to real data, with OAuth Connections the known remaining item (scheduled D21). [interpreted]