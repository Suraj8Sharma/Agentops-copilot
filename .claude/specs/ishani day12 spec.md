Day 12 Spec — Core Screen Shells Freeze (Gate 1)

Project: AgentOps Copilot — MCP-native multi-agent personal assistant Owner: Ishani (Frontend Design Lead & Trust Surfaces) Day / Date: D12 — Saturday, 5 September 2026 Task (from Day-by-Day Plan, Section 14): "Week-2 review; PR merge — core screen shells complete" Milestone: Gate 1 — End of Week 2: Auth + OAuth layer frozen Source: AgentOps Copilot Technical Implementation Manual v2.0

1. Problem Statement

By the end of Week 2, the team needs a single, mergeable checkpoint proving that the app's entire core trust loop has a UI shell, even though the real backend (auth, OAuth, tasks, approvals) is only partially live. Without this freeze:

Week 3 (7–12 Sep) cannot start wiring screens to real endpoints (D13–D15 depend on shells already existing).
The team has no shared, reviewable baseline for the seven screens Ishani owns — each was built on a separate day (D2–D10) against ad-hoc mock data, so drift in navigation, theming, or state handling would only surface later, when it's expensive to fix.
Gate 1 explicitly requires Ishani's checklist item — "All 7 core screen shells exist (even against mock data)" — to be true before the gate can close alongside Suraj's auth/OAuth freeze, Jigyasu's auth+voice UI shells, Sanskriti's 40 golden cases, and Shivangi's weekly report #1.

Day 12's job is therefore not new screen work — it is to review, reconcile, and merge the seven previously built screens into one frozen, PR-reviewed v1 that Week 3 can safely build on.

2. Functional Requirements

The merged PR must leave main in a state where:

#	Requirement	Screen(s) affected
FR1	All 7 core screens render end-to-end from the navigation shell (router.dart) without crashing, using mock/fixture data only.	Onboarding/Splash, Home/Dashboard, Task Composer, Agent Plan View, Approval Screen, OAuth Connections, Trust Dashboard
FR2	Every screen consumes the shared design system (theme.dart — colour, type, spacing tokens from D1) instead of local hardcoded styles.	All 7
FR3	Navigation between screens matches the routing skeleton defined on D2; no orphaned or unreachable screens.	All 7
FR4	Mock data shapes on each screen mirror the real response/request shape each screen will eventually consume (see Section 3), so Week 3 wiring is a data-source swap, not a UI rewrite.	All 7, esp. Home/Dashboard, Task Composer, Agent Plan View, Approval Screen
FR5	Approval Screen and Agent Plan View — flagged safety-critical / core-of-G2 — render the full risk-card / step-list layout with no partial or placeholder states left in the merged build.	Approval Screen, Agent Plan View
FR6	Widget tests exist for all 7 screens; each screen "renders correctly" per the Frontend Widget Tests row of Section 15.	All 7
FR7	PR is opened against main, passes CI (lint + unit/widget tests + eval-smoke + build check), and is merged by Suraj (sole merger) with the required one review.	Repo-level
3. API / Data Contract (mock shape → future real endpoint)

Per Section 13, Weeks 1–2 build screens against mock data; the real wiring happens in Week 3+. To make that swap painless, each screen's mock fixture on Day 12 must match the shape of the real endpoint it will eventually call (Section 10, Backend API Reference):

Screen	Future endpoint	Method	Notes for the mock fixture
Onboarding / Splash	—	—	Static; no backend dependency
Home / Dashboard	/tasks	GET	Mock a list of task objects with id, title, status
Task Composer	/tasks	POST	Mock the submit payload (text/voice input) and an optimistic "task created" response
Agent Plan View	/tasks/{id}/plan	GET	Mock task_plans + ordered plan_steps (step name, tool, status)
Approval Screen	/approvals/{step_id}, /approvals/pending	POST, GET	Mock a pending step with risk_tier, explanation_text (Section 9.3 format), and approve/reject actions
OAuth Connections	/oauth/{provider}/connect, /oauth/{provider}/callback, /oauth/{provider}	GET, GET, DELETE	Mock 4 provider cards (Calendar, Gmail, GitHub, Slack) with status: active | expired | revoked | scope_mismatch
Trust Dashboard	/dashboard/metrics	GET	Mock aggregate latency/cost/accuracy figures

All of these routes sit behind the JWT-verification dependency (Section 5.1) once wired — the shells don't need to implement auth themselves on Day 12, but the fixtures should assume an authenticated user context.

4. Constraints
Sole merger: only Suraj merges to main; branch protection requires no direct pushes and at least one required review, with all CI checks green (Section 12).
CI gate: every PR must pass lint (dart analyze), flutter test, the eval-smoke subset, and a build check — all four, no exceptions.
Design-system lock-in: screens must use the tokens from mobile/lib/core/theme.dart (D1) rather than ad-hoc styling, since five different build days (D2–D10) produced these screens independently.
Mock-data-only scope: no real backend wiring happens on Day 12 — that is explicitly Week 3's job (D13 onward). Day 12 is a shell freeze, not a feature-complete milestone.
Six-day work week / Saturday review day: D12 falls on the team's standing Saturday review + PR-merge slot (Section 13) — whatever is "in flight" from the week gets wrapped up and merged same-day, not carried forward silently.
Cross-team dependency: Gate 1 only closes if Suraj (auth/OAuth), Jigyasu (auth + voice UI shells), Sanskriti (40 golden cases), and Shivangi (weekly report #1) also land the same day — Ishani's merge doesn't stand alone.
Safety-critical bar: the Approval Screen and Agent Plan View are held to a stricter quality bar than the other five screens even at shell stage, since they are called out separately in Sections 3, 11.1, and 15 as never allowed to mis-render.
5. Edge Cases & Error Handling

Even though Day 12 ships against mock data only, the shells being frozen must already account for the following, so Week 3's real-data wiring doesn't require re-opening screen layouts:

Empty states — Home/Dashboard with zero tasks; Trust Dashboard before any eval_runs/llm_usage_logs exist; OAuth Connections with all four providers disconnected.
Loading states — Agent Plan View while task_plans/plan_steps are (eventually) being fetched; Approval Screen while a decision is pending.
Error / disconnected states — OAuth Connections must visually represent all four status values from oauth_connections (active, expired, revoked, scope_mismatch), since Section 5.2 specifies provider-specific failure behaviour (e.g., a revoked GitHub token, an uninstalled Slack app) that the screen will need to surface once wired.
Never-mis-render bar — Approval Screen and Agent Plan View must not silently fail or render a broken/blank state under any mock input, per their 100%-coverage, safety-critical designation (Section 15).
Navigation dead-ends — no screen in the 7 may be unreachable from the router, and no screen may route to a not-yet-built screen without a guarded stub.
Data-shape mismatches at swap time — because mock fixtures are built to mirror the real endpoint contracts (Section 3 above), a mismatch here would only surface as a known, contract-level bug in Week 3, not a UI redesign.
6. Acceptance Criteria

Day 12 is complete when all of the following hold:

Gate 1 checklist item (Ishani's row, Section 17): "All 7 core screen shells exist (even against mock data)" — verified true for Onboarding/Splash, Home/Dashboard, Task Composer, Agent Plan View, Approval Screen, OAuth Connections, and Trust Dashboard.
PR merged: the Week-2 PR is merged into main by Suraj, with the required review and all CI checks (lint, tests, eval-smoke, build) green — per Section 12's branch-protection rule.
A7 (Acceptance Criteria, Section 18) trending correctly: widget-test coverage exists for all 7 screens now, on track toward the ≥80%-overall / 100%-Approval-Screen-and-Plan-View bar required by project end.
Gate 1 closes as a whole: true only if Suraj's auth/OAuth freeze, Jigyasu's auth + voice UI shells, Sanskriti's 40 golden cases, and Shivangi's weekly report #1 also land same-day (Section 17) — Ishani's item is necessary but not sufficient on its own.
No regression in navigation or theming: a walkthrough from Onboarding → Home → Task Composer → Agent Plan View → Approval Screen → OAuth Connections → Trust Dashboard completes with consistent design tokens and no crashes, against mock data.
Contract-ready fixtures: each screen's mock data matches the shape of its eventual real endpoint (Section 3), confirmed by spot-check against Section 10's Backend API Reference, so Week 3 wiring (D13–D15) can proceed without UI rework.