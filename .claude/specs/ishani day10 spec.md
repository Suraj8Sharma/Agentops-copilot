Day 10 Spec — Trust Dashboard UI (Mock Charts)

Owner: Ishani | Date: Thu, 3 Sep 2026 | Week: 2 (Auth + OAuth phase) Key file: mobile/lib/features/trust_dashboard/trust_dashboard_screen.dart

1. Problem Statement

Users have no visibility into how the agent is performing behind the scenes — how fast it responds, what it's costing, and how accurate its plans are. Goal G2 ("legible Flutter client") requires the user to always be able to see what the agent is doing and why. The Trust Dashboard is the screen that exposes this observability: latency, cost, and accuracy at a glance, for the user (not just internally for the team).

On Day 10, this is a UI-only, mock-data build — Weeks 1–2 follow the "screens built against mock data while backend infrastructure comes online" pattern (Section 13). The real wiring to live metrics doesn't happen until D30, once eval_runs and the /dashboard/metrics endpoint exist.

2. Functional Requirement
Build the Trust Dashboard screen with mock charts covering three metrics:
Latency — response time observability
Cost — LLM spend observability (Groq/Gemini usage)
Accuracy — planner/router/eval performance
Screen complexity is rated Medium in the page inventory (Section 6).
Belongs to Ishani's "core trust loop" set of screens (Onboarding, Home, Task Composer, Agent Plan View, Approval Screen, OAuth Connections, Trust Dashboard) — the screens that carry the product's legibility/trust promise.
This is a mock-data milestone only; no live data wiring is in scope for D10 (that's D30's job, per the frontend/backend pattern in Section 13).
3. API Contract (future wiring — not consumed yet on D10)

Once wired (D30), the screen will consume:

Method	Path	Auth	Purpose
GET	/dashboard/metrics	JWT	Aggregate latency/cost/accuracy for the Trust Dashboard

Backing tables (Section 7, Group F — service-role only, never queried directly by the client; surfaced only via the endpoint above):

eval_runs — one row per eval-suite run (pass_count, fail_count, avg_latency_ms) → feeds the accuracy panel
llm_usage_logs — every LLM call (provider, model, tokens_in/out, latency_ms, cost_estimate via execution_logs, rate_limit_hit) → feeds cost/latency panels
Both tables are indexed (eval_cases.run_id, llm_usage_logs.created_at) specifically to keep dashboard aggregate queries fast on free-tier Postgres (Section 7.2).

On D10 itself, these are not called — the UI is built against hardcoded/mock chart data standing in for this shape.

4. Constraints
Free-tier architecture (Section 2.3) — the metrics this dashboard will eventually show exist because of free-tier limits:
Groq/Gemini rate limits are the reason llm_usage_logs and routing/fallback exist at all — the cost/latency panel is effectively a window into that constraint.
Render cold starts mean latency numbers can spike on a cold instance; the dashboard should not misrepresent a cold-start spike as steady-state performance (relevant once wired).
Supabase free-tier storage cap is why execution_logs/usage logs are kept lean (structured JSON, not raw provider responses) — the dashboard reads aggregates, not raw payloads.
Design system dependency — must use the shared design tokens/theme (mobile/lib/core/theme.dart, built D1) for colour/type/spacing consistency with the rest of the trust-loop screens.
Mock-data discipline — D10's deliverable is explicitly mock; do not backend-couple this screen early, since D13–D30 stage the wiring incrementally per screen.
Not safety-critical — unlike Approval Screen / Plan View, Trust Dashboard does not carry a 100% widget-test coverage bar (Section 15.2), just the general 80% floor.
5. Edge Cases & Error Handling

The manual does not schedule a dedicated "Trust Dashboard edge cases" day the way it does for Digest (D11) or OAuth Connections (D22). What applies, inferred from adjacent sections:

Empty/loading states — covered generally under the Week 6 UI polish pass (D34: "spacing/empty/loading states, all screens") rather than on D10 itself. Since D10 is mock-only, empty-state handling for zero eval runs / zero usage logs should be considered but isn't required to be pixel-final yet.
Render cold-start latency (once live) — Acceptance A6 measures the auto-executed, warm-path case specifically; the dashboard's latency display should not conflate a cold-start penalty with the steady-state p95 figure it will eventually report.
Free-tier rate-limit hits (once live) — llm_usage_logs.rate_limit_hit exists so a Gemini-fallback event is visible on the dashboard rather than silently absorbed — worth designing the chart/legend to distinguish a fallback event from a normal call, even at mock stage.
No explicit error-state requirement is named for D10 — treat this as a gap to flag with Suraj if the mock charts need to model a "metrics unavailable" state before D30's real wiring.
6. Acceptance Criteria

No acceptance criterion targets the Trust Dashboard by name, but two apply to it as one of the 17 MVP screens:

ID	Criterion	Relevance to Trust Dashboard
A6	p95 end-to-end latency for a simple, low-risk, auto-executed task is under 8 seconds.	This is the exact figure the dashboard's latency panel will surface once wired (D30) — the mock chart's shape should anticipate displaying this metric.
A7	Widget-test coverage ≥80% overall; 100% only for Approval Screen & Plan View.	Trust Dashboard needs render + basic-interaction widget test coverage (80% floor) — not the 100%/golden-file bar reserved for the two safety-critical screens.

Gate checkpoint: Trust Dashboard doesn't need to be wired until Gate 2 is not the deadline — it's explicitly still mock at Gate 1 (5 Sep) and gets wired later; Gate 3 (26 Sep) is where "Trust Dashboard wired" is confirmed done (D30, Sat 26 Sep: "Trust Dashboard wired to real metrics; Week-5 review; PR merge").

Compiled from AgentOps Copilot Technical Implementation Manual v2.0 — Sections 2.3, 3, 6, 7, 10, 13, 14 (D10, D30), 15.2, 17, 18.