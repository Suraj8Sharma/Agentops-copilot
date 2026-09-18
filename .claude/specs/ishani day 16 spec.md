Spec Document
Wire Approval Screen to Real Approvals Endpoint
AgentOps Copilot — Build Day 16 (Thu, 10 Sep) · Owner: Ishani
Source: AgentOps_Implementation_Manual.docx — Section 14 (Day-by-Day Plan), Section 10 (API Reference), Section 7 (Database Schema), Section 9 (Risk & Approval Gate), Section 16.3 (Definition of Done), Section 18 (Acceptance Criteria)
1. Problem Statement
The Approval Screen (owned by Ishani) has existed since Day 8 as a risk-card UI with mock approve/reject — a user could see a fake risk-flagged action and tap approve or reject, but nothing real happened. By Day 15, Plan View was wired to real task_plans/plan_steps data, so a user can already see a plan containing a step with requires_approval = true sitting in an awaiting_approval-shaped state. Day 16 closes the loop on the human side of the safety gate: Ishani wires the Approval Screen to the real approvals endpoint, so a genuine approve/reject decision is recorded against a real plan_steps row and resumes the actual LangGraph checkpoint — not a mock.
This is the single most safety-critical wiring task Ishani owns. The Approval Screen is one of only two screens held to a 100%-coverage, never-mis-render bar (Section 15.2), it is the human half of the property Goal G1 depends on — "ship a plan → risk-tag → approve → execute → log loop that never silently takes a risky action" — and Section 9.4's adversarial bypass test exists specifically to prove that a high-risk step can never reach execution through this screen, or any other path, without a real, logged approval.
Sequencing note worth confirming before implementation: Section 14 lists Ishani's Day 16 task as "Wire Approval Screen to real approvals endpoint," but Suraj's Day 17 task is "Approval-gate logic (fail-closed) + approvals table/endpoint." Read literally, the endpoint this task wires is only built the day after. This may mean a minimal approvals table/endpoint already exists earlier (e.g. scaffolded alongside the Day 11 task/task_plans/plan_steps work) and Day 17 hardens the fail-closed enforcement logic around it — but the manual doesn't state that explicitly. Confirm the actual state of POST /approvals/{step_id} and GET /approvals/pending with Suraj before starting; this spec is written assuming a working, if not yet fully fail-closed-hardened, endpoint is reachable on Day 16.
2. Functional Requirements
2.1 Core behaviour
On opening the Approval Screen, the screen fetches GET /approvals/pending with the authenticated user's JWT attached as a Bearer token, replacing the mock risk card, and lists the real steps currently awaiting this user's decision.
Each pending item renders the plain-English risk explanation produced by the Explanation LLM (Section 9.3) exactly as returned — the screen must never edit, summarise, or reinterpret this text, since the explainer is advisory-only by design and its wording is the thing under golden-file test (test_approval_screen_renders_risk_explanation, Section 15.2).
The screen exposes approve and reject controls per pending step. Tapping one sends POST /approvals/{step_id} with the decision (approved | rejected) and the user's JWT, replacing the mock approve/reject actions from Day 8.
A successful decision resumes the real LangGraph checkpoint for that task (Section 8, Node Sequence) — the screen's job ends at recording the decision; it does not simulate or predict what happens next in the graph.
The screen never auto-approves anything, under any input or timing condition — this is directly enforced by test_approval_screen_never_auto_approves (Section 15.2) and is non-negotiable given the fail-closed architecture (Section 1.2, 9.2).
A visible loading state is shown while pending approvals are being fetched, and while a decision is being submitted; the decision controls are disabled once a decision is in flight for that step to prevent a double submit.
On fetch or submit failure, the screen surfaces a clear, non-silent error state — silent failure on this screen is unacceptable by construction (Section 1.2, "Auditability by construction").
2.2 Out of scope for Day 16
Deciding which actions require approval in the first place — that is risk_rules and the hardcoded risk_tag node (Section 9.1–9.2), never this screen.
Rendering the full ordered plan — that is Plan View's job (Day 15); the Approval Screen only needs the specific step(s) awaiting this user's decision plus their explanation text.
Building the approvals table/endpoint or the fail-closed enforcement logic itself — that is Suraj's backend work (Section 14, Day 17); this task only consumes it from the client.
3. API Contract
As defined in Section 10 (Backend API Reference) and Section 7 (approvals table, Group B — Task Orchestration). This task wires both approval endpoints; GET /tasks/{id}/plan (Day 15) and POST /tasks (Day 14) are consumed elsewhere.
3.1 GET /approvals/pending
Field
Value
Method / Path
GET /approvals/pending
Auth
JWT (Bearer token) — required
Purpose
List steps currently awaiting this user's decision (Section 10)


Response shape inferred from plan_steps (Section 7, Group B) joined with its risk-explanation text (Section 9.3). Not printed verbatim in the manual — flagged as an assumption below.
// 200 OK
[
  {
    "step_id": "uuid",           // plan_steps.id
    "task_id": "uuid",
    "tool_name": "gmail.send_message",
    "mcp_server": "gmail",
    "risk_tier": "high",
    "input_params": { "...": "..." },
    "explanation_text": "This will send an email to professor.rao@
                          university.edu with the subject 'Agenda
                          for Thursday's call'.",   // Section 9.3
    "status": "awaiting_approval"
  }
]
3.2 POST /approvals/{step_id}
Field
Value
Method / Path
POST /approvals/{step_id}
Auth
JWT (Bearer token) — required
Purpose
Record an approve/reject decision, resumes the LangGraph checkpoint (Section 10)


Request/response fields taken directly from the approvals table columns (Section 7). id, step_id linkage, user_id, decided_at, and response_time_ms are server-assigned/derived; the client only supplies the decision.
// Request
{
  "decision": "approved"     // "approved" | "rejected" — approvals.decision
}

// 200/201 response
{
  "id": "uuid",
  "step_id": "uuid",
  "user_id": "uuid",
  "decision": "approved",
  "explanation_text": "string",   // copy shown at decision time
  "decided_at": "timestamptz",
  "response_time_ms": 4210         // feeds the Trust Dashboard
}
Assumption flagged: the manual documents the approvals table's columns (Section 7) and the two endpoint purposes (Section 10), but does not print literal JSON for either. The shapes above are a direct reading of those columns — confirm the exact wire format, and in particular whether GET /approvals/pending returns plan_steps fields flattened as shown or nested under a step object, with Suraj before finalising Flutter models.
3.3 Error responses
Status
Meaning
Client handling
401
Missing/expired/tampered JWT
Attempt token refresh (existing flow, Section 15.4); if refresh fails, route to Sign In
404
step_id doesn't exist, or isn't in an awaiting_approval state
Treat as "already decided or no longer pending" — refresh the pending list rather than showing a raw error
409 (assumed)
Step was already decided (e.g. by a concurrent session) before this decision landed
Refresh and show the step's actual current state; never silently apply the user's tap as if it succeeded
403 (implicit via RLS)
Step belongs to another user's task
Should be unreachable from normal navigation; treat as a generic error, never render or act on another user's approval
5xx
Backend/Render/Supabase failure
Show a visible retry-able error; never fail silently, and never assume the decision was recorded


4. Constraints
Fail-closed by construction. This screen cannot be the thing that makes an action safe — risk_rules and approval_gate.py already decided the step requires approval (Section 9.1–9.2); the screen's only job is to record a real human decision and never to auto-approve, default-approve, or approve on any error path.
Explanation is advisory only. The explanation_text shown here is produced by a separate, advisory-only LLM (Section 9.3) and must be rendered verbatim; nothing in the Approval Screen may alter it or use it to pre-select a decision — the risk gate is hard, the explanation is soft (Section 4.2).
Safety-critical coverage bar: Approval Screen is one of two screens held to 100% widget-test coverage plus a golden-file test, and to a never-mis-render bar (Section 15.2) — the same standard applied to Plan View on Day 15.
This is the direct subject of the non-negotiable adversarial bypass test (test_approval_gate_bypass_attempt_always_fails, Section 9.4/15) — a failing run blocks the release candidate regardless of what else is green. The Approval Screen's decision-submission path is one of the code paths that test exercises.
Backend sequencing risk (see Section 1 warning): Suraj's Day 17 task explicitly builds the approvals table/endpoint and fail-closed enforcement logic, one day after this task wires the client to it — verify the endpoint's actual readiness before or at the start of Day 16 rather than assuming it from the plan text alone.
Row-level security: approvals rows are scoped by user_id = auth.uid() (Section 7); the client never supplies user_id — it is derived server-side from the JWT.
Every non-public route sits behind the JWT-verification dependency (Section 5.1) — reuse the existing JWT/refresh handling already used on the Task Composer, Home/Dashboard, and Plan View screens rather than reimplementing it.
Free-tier architecture (Section 2.3): Render's free-tier service cold-starts after inactivity — show an explicit loading state on both the pending-list fetch and the decision submit, not a spinner that reads as a hang.
Definition of Done (Section 16.3) applies: code merged via a reviewed PR; flutter test coverage for this screen's real-data and real-decision paths exists and passes; fail-closed/fail-open behaviour is explicitly verified for this path (it is the single most relevant screen for that check in the whole project); logging is present since this path is on the agent loop; one paragraph of docs is written the same day.
5. Edge Cases & Error Handling
No pending approvals — show a clear empty state ("nothing waiting on you right now"), not a blank screen or an error.
Decision submitted but the network drops before a response arrives — do not assume success; keep the step in its pending UI state, show a retry-able error, and re-fetch GET /approvals/pending to reconcile with the server's actual state rather than trusting an optimistic local update.
Step already decided elsewhere (e.g. same account open on a second device, or a stale cached pending list) — a 404/409 on submit must not be silently swallowed; refresh the list and reflect the step's real current status to the user.
Double-tap on approve/reject — the control must be disabled the instant a decision is submitted for that step, so a duplicate POST /approvals/{step_id} can never be sent for the same tap.
Explanation text missing or empty from the API response — the screen must not fabricate or infer an explanation to fill the gap (Guardrail 1, Section 9.3: no false claims about the action); show a neutral "no explanation available" placeholder instead and still allow the underlying risk_tier/tool_name/input_params to inform the user's decision.
A step's risk_tier is high but requires_approval looks inconsistent, or vice versa — render exactly what the API returns; this is backend risk-gate output, and the Approval Screen must never attempt to second-guess or "correct" it client-side (Section 4.2, "risk gate hard, explanation soft").
JWT expired mid-session — trigger the existing refresh flow (test_jwt_refresh_issues_new_access_token, Section 15.4) transparently before retrying the pending-list fetch or the decision submit; if refresh fails, route to Sign In rather than silently dropping a decision attempt.
Render cold start on first open after inactivity — request may take tens of seconds; show the explicit loading state from Section 2.3 rather than a spinner that looks broken, on both the initial fetch and a decision submit.
Backend/network failure (5xx, timeout, offline) on fetch or submit — show a visible, retry-able error; never fail silently, and never fall back to mock/cached approve-reject behaviour in place of a real error.
Attempting to act on another user's step (e.g. a stale deep link or tampered request) — RLS should make this unreachable server-side; the client must never render or allow a decision on data it cannot verify belongs to the current user.
6. Acceptance Criteria
Task-level criteria for Day 16, combining the plan-level requirement ("Wire Approval Screen to real approvals endpoint", Section 14) with the standing Definition of Done (Section 16.3) and the project-wide Acceptance Criteria this task feeds into (Section 18).
Opening the Approval Screen fetches and renders real pending steps via GET /approvals/pending — not mock data.
Each pending item shows its real, verbatim risk explanation, matching test_approval_screen_renders_risk_explanation (golden test, Section 15.2).
Tapping approve or reject sends a real POST /approvals/{step_id} decision and the corresponding LangGraph checkpoint is actually resumed — verifiable against Supabase/execution_logs, not a mock UI transition.
The screen never auto-approves under any tested condition, matching test_approval_screen_never_auto_approves (Section 15.2).
A decision-submission failure never results in an action being treated as approved on the client when it was not recorded on the server — verified by re-fetching state after a simulated failure.
Empty pending list, fetch failure, and submit failure all show distinct, non-silent, appropriately handled UI states per Section 3.3/Section 5.
A loading state is visible on both fetch and submit, including on a Render cold start.
Widget-test coverage for the Approval Screen reaches the 100% bar specified for this screen, including a golden-file test (Section 15.2).
The screen's decision-submission path is included in scope for, and does not undermine, the adversarial bypass test (test_approval_gate_bypass_attempt_always_fails, Section 9.4) — this remains the single non-negotiable acceptance bar tied to this area of the app.
Code is merged to main via a reviewed PR; fail-closed/fail-open behaviour on this path is explicitly verified; one paragraph of docs is written the same day (Section 16.3).
Contributes toward project Acceptance Criterion A2 — every high-risk action blocked pending approval in 100% of adversarial bypass-test runs, zero tolerance — and A7 — 100% widget-test coverage on the Approval Screen (Section 18).

Items marked as assumptions, open questions, or sequencing risks above are not explicitly stated (or are ambiguous) in the Implementation Manual and should be confirmed with Suraj (backend owner) before or during implementation.
