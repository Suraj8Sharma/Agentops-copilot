# AgentOps Copilot — Spec Document

## Owner: Ishani | Day 5 — Friday, 28 August 2026
## Deliverable: Task Composer Screen UI — Text Mode (mock)

*Source: AgentOps Copilot Technical Implementation Manual v2.0, Section 14 (Day-by-Day Plan), Section 6 (App Page Inventory), Section 7 (Database Schema), Section 10 (Backend API Reference).*

---

## 1. Problem Statement

Once a user lands on the Home/Dashboard screen (built D4), they need an actual entry point to create a task. The Task Composer is that entry point. This D5 slice covers **text mode only** — the user typing a request in natural language. Voice mode is a separate, later track owned by Jigyasu (on-device STT integration starts D9, voice UI work runs D7 onward) and must not be built here. Without this screen, the quick-entry affordance on the Home/Dashboard has nowhere to route to.

---

## 2. Functional Requirements

- A text input field where the user types a task request in natural language.
- A submit action that, on D5, is **mock only** — not yet wired to the backend.
- A visual "submitting" state, and a placeholder for the resulting task appearing (eventually) on the Home/Dashboard list built the day before.
- Layout must be structured so a voice-mode toggle can be added later without a rebuild — reserve the affordance, don't build the capture logic.
- Visual design must follow the same D1 design tokens/theme as the Home/Dashboard screen for continuity between the two screens.

---

## 3. API Contract

**Not yet wired on D5.** The screen accepts input and shows a mock "submitted" state only. Its eventual backend dependency, per Section 6 (App Page Inventory) and Section 10 (Backend API Reference), is:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/tasks` | JWT | Submit a new text or voice task; kicks off the LangGraph run |

**Recommended mock submission payload shape** (aligned to the `tasks` table, Section 7, so the D14 wiring — "Wire Task Composer to real `POST /tasks`" — is a straightforward swap, not a redesign):

| Field | Type | Notes |
|---|---|---|
| `input_type` | text | `"text"` for this slice (`"voice"` reserved for Jigyasu's later track) |
| `raw_input` | text | The user's typed request |
| `transcription_text` | text | Nullable — not used in text mode |
| `status` | text | Starts at `submitted` on mock-submit |

---

## 4. Constraints

- Complexity is rated **Medium** (Section 6).
- **Text mode only** for D5 — do not build voice capture, mic permissions, or listening states here; that is explicitly a separate owner (Jigyasu) and a separate week.
- Must reuse the D1 design tokens/theme and stay visually consistent with the D4 Home/Dashboard screen (same owner, adjacent day, same navigation flow).
- No live backend dependency should be introduced yet — the JWT/auth layer (Suraj, also D5) and the eventual `POST /tasks` route both need to be frozen and stable before real wiring (scheduled D14).
- Runs within the project's free-tier-aware architecture (Section 2.3) — the eventual live submission will hit a Render-hosted backend subject to cold-start latency, so the interaction pattern (e.g., a responsive local "submitting" state) should be designed with that future constraint in mind, even though it isn't triggered on D5.

---

## 5. Edge Cases & Error Handling

- **Empty submission**: must be blocked/validated client-side before any (future) network call — a blank task request should never reach mock or real submission.
- **Very long input text**: must not break the composer's layout or scroll behavior.
- **Rapid repeated taps on submit**: consider debouncing/disabling the submit action after the first tap, even at mock stage, to avoid duplicate-submission patterns that would carry over once wired.
- **Placeholder failure state**: reserve a visual state for a future submission failure (e.g., an eventual 4xx/5xx from `POST /tasks`), even though it cannot be triggered for real on D5.
- **Placeholder loading state**: anticipate the eventual Render free-tier cold-start latency (Section 2.3) by including a distinct loading/submitting state now, rather than treating "submitting" and "submitted" as the same instant.

---

## 6. Acceptance Criteria

- Text-mode composer renders, accepts typed input, and shows a mock "submitted" state on tap.
- Empty-input submission is blocked client-side.
- Layout visually reserves space/affordance for a future voice-mode toggle without requiring a redesign when Jigyasu's voice work lands.
- Visual design is consistent with the D4 Home/Dashboard screen.
- Mock submission payload shape aligns with the `tasks` table schema so the D14 real-wiring pass does not require structural rework.
- Screen is reachable from the Home/Dashboard's quick-entry affordance (built D4).