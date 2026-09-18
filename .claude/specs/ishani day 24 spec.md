Spec: Week-4 Review & PR Merge — Gate 2 (Core Loop + Notifications Live)

Owner: Ishani · Day: D24, Sat 19 Sep · Week 4 close — also Gate 2

Derived from the AgentOps Implementation Manual (§12 CI/CD, §13 Working Rhythm, §14 Day Plan D17–D24, §16.3 Definition of Done, §17 Gate 2). Points not stated verbatim are marked [interpreted].

1. Problem Statement

D24 is structurally the same kind of day as D18: the Saturday review-and-merge close of a work week. But it carries more weight than D18 did, because D24 is also the date the manual names Gate 2 — Core loop + notifications live. Everything Week 4 built has to land as a coherent, merged whole on this exact day, not just be "in progress and reviewable."

Week 4 was notifications week, and it fans out across all five people landing simultaneously on D24: Suraj brings the notifications table and FCM push endpoint live and merges the planner/MCP-clients/approval-gate/notifications-table work; Ishani's own OAuth Connections wiring (D21) and its edge cases (D22), plus the Approval Screen edge-case work (D23), need to be in mergeable state; Jigyasu wires the Notifications list to the real notifications/push endpoint the same day the endpoint goes live, on top of voice input and Activity Log; Sanskriti and Shivangi close out their own Week-4 items (Memory/Preferences wiring, banner eval cases, Digest screen, weekly report #3).

Unlike D18 — where the constraint was "don't merge after Suraj's freeze" — D24's constraint runs the other way: Suraj's notifications table lands the same day Jigyasu depends on it, and Ishani's own OAuth/Approval-Screen edge-case work from D21–D23 has to already be merge-ready so it doesn't become the thing that blocks Gate 2. The review-and-merge task is therefore also the checkpoint where Ishani's specific Gate 2 line item gets verified: Home, Composer, Plan View, Approval Screen, OAuth Connections all wired to real data.

Explicitly not in scope for D24: building any new screen or endpoint (all Week-4 build work is D17–D23); Trust Dashboard wiring (D30); Week 5's frontend test-suite setup (D25).

2. Functional Requirements
FR1 — Week-4 review conducted. Ishani reviews the week's client-side work, spanning her own D21–D23 tasks and the work of her reports (Jigyasu, Sanskriti, Shivangi) that touches the client.
FR2 — All five of Ishani's Gate 2 screens verified wired to real data. Home, Composer, Plan View, Approval Screen, OAuth Connections — the last two (Approval Screen edge cases, OAuth Connections + edge cases) only finished landing D21–D23, so this is the first point they're confirmed together as a set.
FR3 — PR(s) prepared and merged. All in-flight Week-4 client work reviewed and merged to main via Suraj — not carried into Week 5 silently (§13).
FR4 — Coordination with Jigyasu's same-day Notifications-list wiring. Since the notifications table and push endpoint go live the same day Jigyasu wires the list screen to them, Ishani's review should confirm that dependency lands cleanly rather than discovering a mismatch after merge. [interpreted]
FR5 — Gate 2 checkpoint met for Ishani's line item. The specific Gate 2 table entry for Ishani (Home, Composer, Plan View, Approval Screen, OAuth Connections wired to real data) is satisfied and demonstrable, not just "mostly true."
FR6 — Definition of Done satisfied (§16.3) for every task merged this week: reviewed PR, passing tests, clean linters, fail-closed behaviour verified on risk-relevant paths (directly relevant given OAuth and Approval Screen edge cases are in this batch), same-day doc paragraph.
FR7 — Carry-over, if any, named explicitly. If any Week-4 item can't close by end of day, it's flagged rather than silently deferred — consistent with the same principle D18 was built on.
3. API Contract

No new endpoints are authored by Ishani on D24. The relevant contract is the same set of core-loop routes verified at D18, now joined by the notification routes going live the same day (Suraj) and consumed the same day (Jigyasu) — Ishani's review has to confirm her own five screens still function correctly against this now-larger merged surface.

Ishani's Gate 2 screens and the routes behind them (already wired, D13–D16, D21–D23):

Screen	Method	Path
Home / Dashboard	GET	/tasks
Task Composer	POST	/tasks
Agent Plan View	GET	/tasks/{id}/plan
Approval Screen	GET	/approvals/pending
Approval Screen	POST	/approvals/{step_id}
OAuth Connections	GET	/oauth/{provider}/connect
OAuth Connections	GET	/oauth/{provider}/callback
OAuth Connections	DELETE	/oauth/{provider}

Landing the same day, owned by others, relevant to review coordination:

Owner	What	Notes
Suraj	notifications table + FCM push endpoint	The backend half of Week 4's notifications work going live
Jigyasu	Wires Notifications list to the above	Depends on the table/endpoint landing correctly the same day

Merge contract (§12, unchanged from D18): lint (ruff + dart analyze) → unit tests (pytest + flutter test) → smoke subset of eval suite → build check, all green; branch-protected main; Suraj is the sole merger — Ishani prepares and reviews, Suraj merges.

4. Constraints
Gate 2 lands exactly on this day. Unlike a normal Saturday review, there's a named external checkpoint attached — "core loop + notifications live" — so this isn't just internal hygiene, it's the thing the gate measures.
Suraj is the sole merger for the whole repository, same as every week — Ishani cannot self-merge; PRs must be review-ready in time for his merge window the same day.
Same-day dependency, not a frozen one. D18's constraint was "don't merge after the freeze"; D24's is the opposite — the notifications table lands today, and Jigyasu's wiring depends on it landing correctly before his own piece can be verified. Ishani's review should account for that ordering risk.
Ishani's own D21–D23 edge-case work is fresh going into this review. OAuth Connections edge cases and Approval Screen edge cases were only finished one and two days prior respectively — this is the first time they're being verified as merge-ready alongside everything else, not work that's had a week to settle.
Coverage floor (A7, §15.2) still applies. 80% widget-test coverage overall, 100% on Approval Screen and Plan View, both with golden-file tests — the edge-case work from D22/D23 must not have dropped coverage on those two screens.
A9 — zero direct pushes to main, no exceptions for gate-day pressure.
Sunday remains the buffer/rest day (§13). If Week-4 work genuinely can't close by end of D24, that's what Sunday is for — but the manual's stated intent is still that in-flight work gets merged and named, not quietly rolled forward.
5. Edge Cases & Error Handling
Case	Expected Handling
notifications table lands with a shape Jigyasu's wiring doesn't match	Caught in review before merge, not discovered post-merge — this is exactly the kind of same-day-dependency risk the review exists to catch. [interpreted]
OAuth Connections edge-case work (D22) regresses the D21 happy path	Review must re-verify the happy path still passes, not just the new edge-case tests — a regression here would silently break a Gate 2 item. [interpreted]
Approval Screen edge-case work (D23) drops coverage below the 100% tier	Blocks merge under the Definition of Done / A7 coverage floor — must be caught before Suraj's merge window, not after.
One of the five Gate 2 screens can't be confirmed working by end of day	Named explicitly as a gap, not presented as done — consistent with the "wrapped up and merged rather than carried forward silently" principle (§13).
PR fails CI (lint, tests, eval smoke, or build) on gate day	Same as any other day — no shortcut around CI just because it's a gate checkpoint; failing checks block merge (§12).
Multiple Week-4 PRs need merging the same day, competing for Suraj's single-merger bandwidth	Prioritise whichever blocks Gate 2 items first (Ishani's five screens, the notifications table/endpoint pairing) over lower-stakes cleanup. [interpreted]
6. Acceptance Criteria
AC1: All five of Ishani's Gate 2 screens — Home, Composer, Plan View, Approval Screen, OAuth Connections — are confirmed wired to real data and demonstrable end-to-end.
AC2: OAuth Connections happy path (D21) and edge cases (D22) both verified working together, not just the edge cases in isolation.
AC3: Approval Screen happy path (D16) and edge cases (D23) both verified working together, including the multi-step and rejected-mid-flow scenarios.
AC4: Approval Screen and Plan View remain at 100% widget-test coverage with golden-file tests passing; overall coverage remains ≥80% (A7).
AC5: CI green on all Week-4 PRs — lint, unit tests, eval smoke subset, build check (§12).
AC6: PR(s) merged to main by Suraj on D24; no direct pushes (A9).
AC7: Gate 2's Ishani line item — "Home, Composer, Plan View, Approval Screen, OAuth Connections wired to real data" — is met in full, not partially.
AC8: Coordination with Jigyasu's Notifications-list wiring confirmed clean — no mismatch between the notifications table/endpoint shape and what the list screen expects.
AC9: Definition of Done met per §16.3 for every task merged this week; any genuine carry-over into Week 5 is named explicitly rather than silently deferred.