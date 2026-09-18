# AgentOps Copilot — Spec Document

## Owner: Ishani | Day 4 — Thursday, 27 August 2026
## Deliverable: Home / Dashboard Screen UI (mock task list)

*Source: AgentOps Copilot Technical Implementation Manual v2.0, Section 14 (Day-by-Day Plan), Section 6 (App Page Inventory), Section 7 (Database Schema), Section 10 (Backend API Reference).*

---

## 1. Problem Statement

Users need a single landing screen that shows their task list and current status at a glance, plus a quick-entry point into creating a new task. This is the app's home base — the first substantive screen a user lands on after onboarding — and it must exist as a navigable, mock-data screen on D4 before it can be wired to real data in Week 3 (D13, per Section 14). Without it, there is no place for a user to see what the agent has done, is doing, or is about to do.

---

## 2. Functional Requirements

- Render a scrollable list of tasks sourced from **mock data** — no backend call yet.
- Each task row must convey status at a glance. Statuses to represent (matching the `tasks` table, Section 7): `submitted | planning | awaiting_approval | executing | completed | failed | cancelled`.
- Each row should show the task's original input (text) alongside its status.
- Provide a quick-entry affordance (e.g., a button or input bar) that will later route into the Task Composer screen — built the following day, D5, by the same owner.
- The screen must exist as a reachable stub inside the navigation shell (the shell itself was built D2).
- Visual design must use the design tokens and Flutter theme established on D1 for consistency with the rest of the app.

---

## 3. API Contract

**Not yet wired on D4.** The screen consumes hardcoded mock data only. Its eventual backend dependency, per Section 6 (App Page Inventory) and Section 10 (Backend API Reference), is:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/tasks` | JWT | List the user's tasks with status |

**Recommended mock data shape** (aligned to the `tasks` table, Section 7, so the later swap to live data is a data-source change, not a UI rewrite):

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `input_type` | text | `text \| voice` |
| `raw_input` | text | User's original text (empty for voice) |
| `transcription_text` | text | Nullable — STT output for voice input |
| `status` | text | `submitted \| planning \| awaiting_approval \| executing \| completed \| failed \| cancelled` |
| `created_at` | timestamptz | |
| `completed_at` | timestamptz | Nullable |

---

## 4. Constraints

- Complexity is rated **Medium** (Section 6) — scope is list rendering + a quick-entry point only. Do not build the step-by-step plan visualization or approval flow here; those are separate, higher-complexity screens (Agent Plan View, Approval Screen) owned later in the build.
- Must follow the D1 design tokens/theme — no ad hoc styling.
- No live backend dependency should be introduced yet. Wiring this screen to a real `GET /tasks` call before the JWT/auth layer exists (built D5, frozen at Gate 1) would break the build.
- Runs within the project's free-tier-aware architecture (Section 2.3) — once wired, this screen will be one of the more frequently polled endpoints, so the mock's data shape and interaction pattern should not assume unlimited or instant backend responses.

---

## 5. Edge Cases & Error Handling

- **Empty state**: a first-run user has zero tasks — the screen must have a defined empty state even at mock stage, not just an assumed non-empty list. (Full empty/loading/error state polish is scheduled for D34, but the layout should not break without data now.)
- **Long task titles / input text**: must not overflow or break the row layout.
- **Mixed / unusual statuses**: `failed` and `cancelled` states should be visually distinguishable from `completed` and in-progress states, since this screen is the first place a user learns something went wrong.
- **Large task lists**: scrolling behavior should be considered even with a small mock dataset, since real usage could produce many rows over time.
- **Future error state placeholder**: once wired, a failed `GET /tasks` call (e.g., due to Render free-tier cold start, Section 2.3) will need a loading/error state — not required to be functional on D4, but the layout should reserve space for it conceptually.

---

## 6. Acceptance Criteria

- Screen renders a mock task list with all relevant statuses represented and visually distinguishable.
- A quick-entry point is present and tappable (navigation wiring to Task Composer can be a stub for now — Task Composer itself ships D5).
- Screen is reachable from the navigation shell built on D2.
- Empty-state layout is defined, even if unpolished.
- Visual design matches the D1 design tokens/theme.
- Mock data shape aligns with the `tasks` table schema so the D13 real-data wiring does not require structural rework.
- Widget-test scaffolding is at least plannable against this screen (full ≥80% coverage requirement, Acceptance Criterion A7, is due later in the build, Section 15.2).