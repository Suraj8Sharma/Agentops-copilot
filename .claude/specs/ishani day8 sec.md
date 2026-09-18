# AgentOps Copilot — Spec Document

## Owner: Ishani | Day 8 — Tuesday, 1 September 2026
## Deliverable: Approval Screen UI — Risk Card + Approve/Reject (mock)

*Source: AgentOps Copilot Technical Implementation Manual v2.0, Section 6 (App Page Inventory), Section 7 (Database Schema), Section 9 (Risk Gate & Explanation LLM), Section 10 (Backend API Reference), Section 14 (Day-by-Day Plan), Section 15 (Testing).*

---

## 1. Problem Statement

When the hardcoded risk gate (Section 9.2) flags a plan step as requiring approval, the LangGraph run halts and waits — no code path in the system can execute a high-risk step without an explicit `approved` decision recorded in the `approvals` table. The Approval Screen is where that human decision actually happens. This is the single most safety-critical screen in the app: a bad or missing approval UI is not a cosmetic bug, it is a control-flow bug that could let a high-risk action execute unreviewed, or make a user approve something they didn't understand. It is rated **High complexity (safety-critical)** in the page inventory (Section 6) — the only screen in the app carrying that explicit safety qualifier — and is one of two screens (with Plan View) held to a 100%-coverage, never-mis-render testing bar (Section 3, Section 15).

---

## 2. Functional Requirements

- Render a **mock** risk card for a flagged step, sourced from data shaped like `plan_steps` + `approvals` + `risk_rules` (Section 7) — no backend call yet.
- The risk card must clearly surface: the action about to be taken (`tool_name`, `mcp_server`), its risk tier (`risk_tier: low | medium | high`), and a plain-English explanation of what the action does and why it was flagged.
- The plain-English explanation is written by a small, separate advisory LLM (Section 9.3, owned by Ishani, not the planner) — the screen must render this as **display-only text**. It must never be capable of influencing what happens if approved; the screen's approve/reject logic must not read or depend on the explanation text in any way.
- Provide two clear, unambiguous actions: **Approve** and **Reject**. On D8 these are mock — they update local/mock state only, not a live backend.
- The screen must never present a state where an action is auto-approved, pre-selected, or defaults toward approval. There is no path in this screen's design that skips an explicit human decision.
- Reflect that a decision made here maps to `decision: approved | rejected` in the `approvals` table, and (eventually) resumes or halts the underlying LangGraph run.

---

## 3. API Contract

**Not yet wired on D8.** The screen renders mock risk cards and records mock approve/reject taps only. Its eventual backend dependency, per Section 10 (Backend API Reference), is:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/approvals/{step_id}` | JWT | Record an approve/reject decision; resumes the LangGraph checkpoint |
| GET | `/tasks/{id}/plan` | JWT | Full `task_plans` + `plan_steps`, source of the step(s) needing approval |

**Recommended mock data shape**, combining `plan_steps`, `approvals`, and `risk_rules` (Section 7), so the eventual wiring is a data-source swap, not a UI rewrite:

**Step being reviewed (`plan_steps`):**

| Field | Type | Notes |
|---|---|---|
| `id` (`step_id`) | uuid | Used as the path param for `POST /approvals/{step_id}` |
| `tool_name` | text | e.g. `gmail.send_message` |
| `mcp_server` | text | `calendar \| gmail \| github \| slack` |
| `input_params` | jsonb | Feeds the explanation text; not necessarily shown raw |
| `risk_tier` | text | `low \| medium \| high` — should always be `medium`/`high` on this screen, since only flagged steps land here |
| `requires_approval` | boolean | Should always be `true` for a step reaching this screen |
| `status` | text | `awaiting_approval` on arrival |

**Decision record (`approvals`), created on submit:**

| Field | Type | Notes |
|---|---|---|
| `step_id` | uuid | FK to the step above |
| `decision` | text | `approved \| rejected` |
| `explanation_text` | text | Advisory copy from the Section 9.3 explainer — **display only** |
| `decided_at` | timestamptz | |
| `response_time_ms` | int | Time from surfaced to decided — feeds the Trust Dashboard later |

**Example explanation text** (Section 9.3 format, non-alarming, descriptive, never persuasive):
> "This will send an email to professor.rao@university.edu with the subject 'Agenda for Thursday's call'."

---

## 4. Constraints

- Complexity is rated **High (safety-critical)** — the highest-stakes screen Ishani owns. Scope and review rigor should reflect that, not just visual polish.
- The explanation LLM's output is **advisory only** (Section 9.3, Guardrail 3): the screen's UI logic must not read `explanation_text` to drive approve/reject behavior — this separation must hold even at mock stage, since it's the pattern that will carry into real wiring.
- The screen must never auto-approve, default-select, or visually bias toward "Approve" — the risk gate's entire design premise (Section 9.2) is that no high-risk action executes without an explicit, uncoerced human decision.
- Must reuse the risk-tier visual language established on D7 (Agent Plan View) for consistency — this screen is where that risk vocabulary matters most.
- `risk_rules` itself (which determines `requires_approval` and `risk_tier`) is a hardcoded, migration-only table (Section 7, Group C) — this screen only displays the result of that lookup; it must not imply any user-facing control over risk classification itself.
- No live backend dependency should be introduced yet — real wiring to `POST /approvals/{step_id}` happens once the risk gate and LangGraph checkpointing exist (Week 3, per Section 13), not on D8.
- This screen is explicitly called out for a **100%-coverage, never-mis-render** testing bar (Section 3, Section 15) — later test-writing should be anticipated in how the screen is structured now (e.g., avoid implicit/hidden state that would be hard to assert against).

---

## 5. Edge Cases & Error Handling

- **Missing or malformed explanation text**: the risk card must have a defined fallback (e.g., showing the raw action facts) rather than rendering blank or broken if the advisory explanation is unavailable — this anticipates a real future failure mode of the separate explainer LLM call.
- **Ambiguous or overly long explanation text**: per Section 9.3, Guardrail 3, explanation output is length-capped — the screen must handle that cap gracefully, not truncate mid-sentence in a way that changes meaning.
- **Double-tap / rapid tap on Approve or Reject**: must not be capable of firing two conflicting decisions — decision should be locked in after the first valid tap, even at mock stage.
- **High-risk step with unusually sparse `input_params`**: the risk card layout must not assume rich detail is always available; a minimal action must still render a complete, honest card.
- **User closes/backgrounds the app mid-decision**: not required to be functional at mock stage, but the screen should not silently treat "no decision" as equivalent to an implicit approve or reject — absence of a decision must remain a distinct, unresolved state.
- **A step that is `low`/`medium` risk somehow reaching this screen**: per the risk gate design, only steps with `requires_approval: true` should ever appear here — treat this as a should-never-happen case, but the screen should not silently proceed as if it were normal; flag as a design/data assumption to be validated once real wiring begins.
- **Rejected decision downstream effect**: the screen itself doesn't need to render the downstream halt/skip behavior, but its approve/reject actions must be clearly two distinct, final outcomes — not a single toggle that could be misread.

---

## 6. Acceptance Criteria

- Screen renders a mock risk card showing action, risk tier, and a plain-English explanation.
- Explanation text is rendered as display-only — no code path in the screen ties explanation content to the approve/reject outcome.
- Approve and Reject are two clear, separate, unambiguous actions; neither is pre-selected or visually favored.
- Risk tier visual treatment is consistent with the vocabulary established on the D7 Agent Plan View screen.
- Screen handles a missing/short/long explanation text gracefully without breaking layout.
- Mock data shape aligns with `plan_steps` + `approvals` + `risk_rules` so future wiring to `POST /approvals/{step_id}` does not require structural rework.
- Screen is explicitly flagged and structured for the upcoming 100%-coverage, never-mis-render widget-test requirement (Section 15) — no hidden/implicit state that would make that bar unreachable later.
- No design or interaction choice on this screen makes approval feel like the default or easier path relative to rejection.