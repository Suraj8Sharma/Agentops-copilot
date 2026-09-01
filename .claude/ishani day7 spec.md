# AgentOps Copilot — Spec Document

## Owner: Ishani | Day 7 — Monday, 31 August 2026
## Deliverable: Agent Plan View Screen UI (mock)

*Source: AgentOps Copilot Technical Implementation Manual v2.0, Section 14 (Day-by-Day Plan), Section 6 (App Page Inventory), Section 7 (Database Schema), Section 10 (Backend API Reference).*

---

## 1. Problem Statement

Once a task moves past submission (Task Composer, D5), the agent produces a step-by-step plan before doing anything. Users need to actually see that plan — what tools it intends to call, in what order, and with what risk level — before execution happens. Without this screen, the agent's plan is invisible, which directly undermines Goal G2 (a legible client the user can trust) and is a prerequisite for the Approval Screen (built D8), which acts on individual steps surfaced here. This is rated a **High-complexity** screen (Section 6) — the first of Ishani's screens to carry that rating, since it must represent an ordered, multi-step, risk-annotated structure rather than a flat list.

---

## 2. Functional Requirements

- Render a **mock** step-by-step visualization of a task's plan, sourced from mock data shaped like `task_plans` + `plan_steps` (Section 7) — no backend call yet.
- Display the plan as an ordered sequence (`step_index`), not an unordered list — order conveys execution sequence and must be visually unambiguous.
- Each step must show: the tool being called (`tool_name`, e.g. `calendar.create_event`), which integration it belongs to (`mcp_server`: `calendar | gmail | github | slack`), its risk tier (`risk_tier`: `low | medium | high`), and its current status (`pending | awaiting_approval | approved | rejected | executing | done | failed`).
- Visually distinguish risk tiers — this screen is the first place a user sees risk surfaced per-step, ahead of the Approval Screen's dedicated risk-card treatment (D8).
- Visually distinguish step statuses, especially `awaiting_approval` and `failed`, since those are the states most likely to require user attention.
- Screen must be reachable from a task's detail context (i.e., tapping into a task from the Home/Dashboard, built D4, should be able to route here once wired).

---

## 3. API Contract

**Not yet wired on D7.** The screen consumes hardcoded mock data only. Its eventual backend dependency, per Section 6 (App Page Inventory) and Section 10 (Backend API Reference), is:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/tasks/{id}/plan` | JWT | Full `task_plans` + `plan_steps` for a given task |
| GET | `/tasks/{id}` | JWT | Task detail including its plan (summary-level) |

**Recommended mock data shape**, aligned to the `task_plans` and `plan_steps` tables (Section 7), so the eventual wiring (Week 3, per Section 13) is a data-source swap, not a UI rewrite:

**Plan-level (`task_plans`):**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `task_id` | uuid | |
| `planner_version` | text | Not user-facing; useful for QA/debug states |
| `plan_json` | jsonb | Ordered step list as produced by the planner |
| `status` | text | `draft \| active \| superseded` |

**Step-level (`plan_steps`), one array entry per step:**

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `step_index` | int | Execution order — drives the visual sequence |
| `tool_name` | text | e.g. `calendar.create_event` |
| `mcp_server` | text | `calendar \| gmail \| github \| slack` |
| `input_params` | jsonb | Not necessarily shown in full on this screen — may be summarized |
| `risk_tier` | text | `low \| medium \| high` |
| `requires_approval` | boolean | |
| `status` | text | `pending \| awaiting_approval \| approved \| rejected \| executing \| done \| failed` |
| `output` | jsonb | Nullable until executed |

---

## 4. Constraints

- Complexity is rated **High** (Section 6) — this is a materially bigger build than Ishani's prior mock screens (Home/Dashboard, Task Composer) and should be scoped/time-boxed accordingly within D7.
- Scope on D7 is the **visualization only** — this screen displays the plan; it does not approve, reject, or otherwise act on steps. That interaction belongs to the Approval Screen (D8), a separate screen built the next day.
- Must follow the D1 design tokens/theme, and should establish the visual vocabulary for risk tiers (`low | medium | high`) and step status that the Approval Screen (D8) and Trust Dashboard (D9 UI, wired later) will reuse or echo — set this pattern deliberately since three screens depend on reading risk consistently.
- No live backend dependency should be introduced yet — real wiring to `GET /tasks/{id}/plan` happens once the LangGraph planner and MCP clients exist (Week 3, per Section 13), not on D7.
- `plan_json` and `input_params` are `jsonb` and could in principle be arbitrarily complex — the mock should assume the UI needs to summarize/render structured tool-call data cleanly, not dump raw JSON to the screen.

---

## 5. Edge Cases & Error Handling

- **Empty or single-step plan**: not every task produces a multi-step plan — the layout must not assume at least 2+ steps.
- **Long plans**: a plan with many steps must scroll cleanly without losing the sense of sequence/order.
- **Mixed risk tiers within one plan**: a plan can contain both a `low`-risk step and a `high`-risk step side by side — both must be simultaneously legible, not just the highest-risk one.
- **`awaiting_approval` step blocking later steps**: the visualization should make it clear that later steps may be gated on an earlier step's approval — since execution is sequential per `step_index`.
- **`failed` step mid-plan**: must be visually distinct from `done`/`executing`, and it should be evident that a failure can affect the steps that follow it.
- **Re-planning**: per the `task_plans` table note, "re-planning creates a new row, not an overwrite" — the mock/screen design should not assume a task has exactly one plan forever; consider (even if not fully built now) how a superseded plan (`status: superseded`) would be distinguished from the `active` one.
- **Long or technical `tool_name` / `input_params` values**: must degrade gracefully in the UI rather than overflowing or requiring horizontal scroll.

---

## 6. Acceptance Criteria

- Screen renders a mock plan as an ordered, step-by-step sequence reflecting `step_index`.
- Each step visibly shows tool name, integration (`mcp_server`), risk tier, and status.
- Risk tiers (`low | medium | high`) are visually distinguishable from one another using a consistent scheme intended for reuse by the Approval Screen (D8).
- Step statuses — particularly `awaiting_approval` and `failed` — are visually distinguishable from normal in-progress/completed states.
- Screen handles both a short (1-step) and a long (multi-step) mock plan without layout breakage.
- Mock data shape aligns with the `task_plans` + `plan_steps` schema so the future wiring to `GET /tasks/{id}/plan` does not require structural rework.
- Given the High-complexity/step-by-step nature of this screen, it is flagged for the 100%-coverage widget-testing bar Ishani's screens are held to for trust-critical surfaces (Section 3) once test-writing begins (Section 15).