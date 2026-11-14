# D32 Spec — Ishani: UI Observation Under Load

AgentOps Copilot · Tue 29 Sep 2026 · Owner: Ishani · Reviewer/merger: Suraj

## 1. Plain-language summary

On D32 Suraj runs a load test: many simulated users hit the backend at once, to see whether the free-tier limits (Groq/Gemini, Render, Supabase) cause trouble. Ishani does not run the load. Her job is to **watch the app while it is under that load** and record what a real user would see: slow screens, spinners that look broken, error messages, wrong data, or anything on the Approval Screen that looks unsafe.

The manual gives this one line for her: *"Support load test — observe UI under backend load/latency."* This spec turns that line into a concrete checklist so the observation is repeatable and the results are usable by Suraj on D34–D36.

## 2. Where this fits in the manual

- **Day plan (Section 14):** D32, Ishani column.
- **Suraj's side of D32:** load test with concurrent users vs free-tier LLM/MCP limits, verifying backoff.
- **Named backend tests she is observing the UI side of (Section 15.4):** `test_50_concurrent_users_no_5xx_errors`, `test_groq_rate_limit_triggers_gemini_fallback_under_load`, `test_render_cold_start_shows_loading_state_not_error`.
- **Acceptance criteria touched:** A2 (high-risk steps never run without approval), A6 (p95 under 8 s for a simple low-risk task), A5 (no cross-user data).
- **Risk register:** Render cold start causing visible lag; Groq/Gemini rate limit hit mid-demo.

## 3. Preconditions (must be true before starting)

- Trust Dashboard wired to real metrics (D30) and widget tests in place (D26–D28).
- A debug APK from the latest merge on `main` installed on one real device or emulator (CI pushes it to Firebase App Distribution).
- Two test accounts: one **observer account** Ishani uses by hand, and the accounts Suraj's script uses. They must be different, so her session is not part of the simulated load.
- Agreed start time and the target environment (deployed Render backend, not local) confirmed with Suraj.
- Suraj tells her when each load phase starts and stops.

## 4. Scope

**In scope:** observing and logging UI behaviour on Home, Task Composer, Agent Plan View, Approval Screen, Activity Log and Trust Dashboard during load; filing bugs.

**Out of scope:** writing or running the load script, changing backend behaviour, fixing UI bugs on the day (fixes go to D34 polish and D36 bug-fix day unless P0), OCR.

## 5. Scenarios to observe

| # | Scenario | When | What Ishani does | What she watches for |
| --- | --- | --- | --- | --- |
| S1 | Baseline | Before any load | Submit one low-risk task (e.g. list calendar events) and time it by stopwatch; open each screen once | Reference timings and normal look of every screen |
| S2 | Ramp under concurrent load | During Suraj's ramp to \~50 users | Repeat the same low-risk task; navigate Home → Plan View → Activity Log → Trust Dashboard | Slow loads, spinners that never end, raw error text, blank screens, stale lists |
| S3 | Groq rate limit → Gemini fallback | When Suraj saturates Groq | Submit a task; open Trust Dashboard afterwards | Task still completes; no hard crash; provider/model shown reflects Gemini; any degradation message is clear and non-alarming |
| S4 | Cold start | After Render has been idle (Suraj coordinates) | Open the app and submit a task as the first request | An explicit loading state, not a frozen screen or an error; app recovers without restart |
| S5 | Approval Screen under load | During peak load | Submit a task with a high-risk step (e.g. send email) | Step appears on Approval Screen with correct explanation; nothing auto-approves; nothing executes before approval; screen does not mis-render or show another step's data |
| S6 | Recovery | After load stops | Repeat S1 task | Timings and screens return to baseline; no leftover error banners |

## 6. Pass / fail criteria

- **Fail (P0):** any high-risk step executes without an approval, the Approval Screen shows wrong or another user's content, or any cross-user data renders.
- **Fail (P1):** the app crashes, a screen stays on an unexplained spinner for more than 15 s, or a raw stack trace or 5xx text reaches the user.
- **Flag (P2):** noticeably slow but functional screens, awkward wording in loading or degradation messages, layout glitches.
- **Reference target (A6):** a simple low-risk task finishing in under 8 s on the warm path. Ishani's stopwatch figures are a UI-side cross-check of Suraj's p95, not a replacement for it.

## 7. Step-by-step procedure

1. Confirm preconditions in Section 3 with Suraj and agree the phase schedule (S1 to S6).
2. Install the latest debug APK and sign in with the observer account.
3. Run S1 and record baseline timings and screenshots.
4. At each phase start announced by Suraj, run the matching scenario and record observations in the log (Section 8) as they happen, with timestamps.
5. Take a screenshot or screen recording for every P0, P1 or P2 finding.
6. After load stops, run S6.
7. Within the same day, finish the log, file bugs, and send the summary to Suraj.

## 8. Observation log format

One row per observation:

| Time | Scenario | Screen | Action | Expected | Observed | Seconds to complete | Severity | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## 9. Deliverables

- The completed observation log (proposed location: `docs/eval/d32_ui_load_observations.md`. The manual names no file for this, so confirm with Suraj).
- Screenshots or recordings for each finding.
- Bugs filed as GitHub issues with severity labels, linked to the log row.
- A short summary to Suraj: which scenarios passed, the worst finding, and which items need backend changes versus UI changes.
- Sanskriti's diary entry and Shivangi's weekly report #5 can pull from this summary.

## 10. Handoff and follow-up

- Backend-caused issues (5xx, slow endpoints, fallback not engaging) go to Suraj.
- UI-caused issues (missing loading states, unclear messages, layout) are scheduled for D34 UI polish.
- P0 items go to Suraj immediately and block the release candidate at Gate 4.

## 11. Open questions to settle before D32

1. Does Suraj run the load against the deployed Render service or a local backend?
2. Exact ramp schedule and how long each phase lasts.
3. Is Ishani's observer account excluded from the simulated user pool?
4. Where the observation log should live in the repo.
