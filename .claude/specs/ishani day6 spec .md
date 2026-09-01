# AgentOps Copilot — Spec Document

## Owner: Ishani | Day 6 — Saturday, 29 August 2026
## Deliverable: Design QA on Auth Screens + Week-1 Review

*Source: AgentOps Copilot Technical Implementation Manual v2.0, Section 14 (Day-by-Day Plan), Section 3 (Team Structure & Ownership), Section 13 (7-Week Roadmap).*

---

## 1. Problem Statement

D6 is the first Saturday of the build — per the team's standing cadence, "Saturday of every week is a review + PR-merge day: whatever is in flight gets wrapped up and merged rather than carried forward silently" (Section 13). Over D3–D5, Jigyasu built the three auth-flow screens (Sign Up, Sign In, Forgot Password/OTP) independently against the D1 design tokens. As Frontend Design Lead — who owns the app's design system and oversees Jigyasu, Sanskriti, and Shivangi on client-side work (Section 3) — Ishani has not yet formally verified that these screens are visually and behaviorally consistent with each other and with the design system before Week 1 closes. Without this pass, inconsistencies (spacing, type, color, validation-state patterns) risk compounding into Week 2 and beyond, when more screens are built on top of these patterns.

---

## 2. Functional Requirements

- Perform a design QA review across the three auth screens built so far: **Sign Up** (D3), **Sign In** (D4), **Forgot Password / OTP** (D5) — all owned by Jigyasu.
- Verify each screen against the D1 design tokens (colour, type, spacing) and Flutter theme for consistency: shared components, spacing rhythm, typography scale, colour usage, and button/input styles must match across all three.
- Verify consistency of interaction patterns across the three screens — e.g., validation-state styling, error-message presentation, loading-state treatment — since a returning user moves between these screens as one continuous flow.
- Log any design deviations found as follow-up items (bugs/tasks) rather than fixing them ad hoc mid-review, so fixes are trackable and attributable.
- Participate in the Week-1 review: confirm Week-1 foundations are in a mergeable state — design system, screen shells, and the auth-screen set are ready to be wrapped up per the Saturday review-and-merge cadence (Section 13).
- Feed any design QA findings into the PR-merge conversation for the day, so known issues are visible before merge rather than discovered later.

---

## 3. API Contract

**N/A.** This is a design-consistency review and process/review checkpoint, not a feature with a request/response contract. No new or modified endpoints are introduced on D6 by this task. (The auth screens' own eventual API bindings — `POST /auth/login`, `POST /auth/reset-password` — were scoped in their respective D4/D5 specs and remain unchanged here.)

---

## 4. Constraints

- Review is scoped to the **auth screens only** (Sign Up, Sign In, Forgot Password/OTP) — it is not a full design audit of every screen shell stubbed on D2.
- This is a review/QA task, not a rebuild — Ishani should not silently redesign Jigyasu's screens during this pass; deviations are logged and handed back, keeping ownership and attribution clear per the team's role structure (Section 3).
- Must reference the D1 design tokens as the source of truth — QA judgment should be traceable to the documented tokens/theme, not personal preference.
- Falls on the standing Saturday review + PR-merge cadence (Section 13) — the review needs to be timely enough to inform same-day merge decisions, not deferred past the Week-1 boundary.
- Week 1's stated scope (Section 13) is foundations — repo, DB v1, FastAPI scaffold, JWT, design system, screen shells, logo direction — so review commentary should stay within that frame rather than pulling in Week 2+ concerns (auth/OAuth backend work, core tables).

---

## 5. Edge Cases & Error Handling

- **Conflicting patterns across screens** (e.g., Sign In and Forgot Password use different error-message styling) — must be explicitly flagged as a deviation, not silently accepted as "close enough."
- **A screen technically matches tokens but reads inconsistently in context** (e.g., correct colours but different spacing rhythm) — QA should catch contextual/relative inconsistency, not just token-value matching in isolation.
- **Deviation found but screen already in the day's merge queue** — flag severity (blocking vs. follow-up) so the Week-1 review can decide whether it blocks the Saturday merge or is logged as a fast-follow task early in Week 2.
- **Ambiguity in the design tokens themselves** (a case the D1 tokens didn't anticipate) — treat as a design-system gap to resolve/document, not something to paper over screen-by-screen.

---

## 6. Acceptance Criteria

- All three auth screens (Sign Up, Sign In, Forgot Password/OTP) have been reviewed against the D1 design tokens and against each other.
- Any deviations found are logged as trackable follow-up items, each tagged with enough detail (screen, element, expected vs. actual) to action later.
- Findings are communicated in time to inform the D6 Week-1 review and PR-merge decision.
- Week-1 review is completed with Ishani's design QA input included, closing out Week 1 per the Section 13 Saturday cadence.
- No undocumented, ad hoc design changes are made to Jigyasu's screens during this pass — all changes flow through logged follow-up items.