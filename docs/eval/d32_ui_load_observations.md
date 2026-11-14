# D32 UI load observations — Ishani

**Owner:** Ishani
**Date:** 2026-11-14
**Scope:** UI observation during Suraj's D32 free-tier load / latency test
**Environment:** deployed backend + observer account, excluding the simulated load accounts
**Run status:** Pending — the live load schedule and evidence have not been provided.

## 1) Preconditions checklist

- [ ] Latest debug APK from `main` installed on a real device or emulator.
- [ ] Observer account signed in and configured separately from Suraj's load-test accounts.
- [ ] Suraj confirmed the target environment (deployed Render backend vs local) and phase schedule.
- [ ] The app is opened once on a clean session before the first measurement.
- [ ] A stopwatch or timing source is ready for the warm-path baseline.
- [ ] Screenshots / screen recordings are enabled before S2–S5 start.
- [ ] A note is recorded for the exact time each load phase begins and ends.

## 2) Run plan

### S1 — Baseline

- Submit one low-risk task (for example: calendar list events).
- Time the submission to visible completion with a stopwatch.
- Open each screen once: Home, Task Composer, Plan View, Approval Screen, Activity Log, Trust Dashboard.
- Capture a baseline screenshot for each screen.

Expected:
- Warm-path timing under 8 s for a simple low-risk task.
- Stable, clear UI states with no error or raw stack traces.

### S2 — Ramp under concurrent load

- At Suraj's signal, repeat the same low-risk task during the concurrent-user ramp.
- Navigate Home → Plan View → Activity Log → Trust Dashboard.
- Record all visible differences from baseline.

Watch for:
- unbounded spinners, hanging screens, blank data, stale lists, slow navigation, raw backend text, visible 5xxs.

### S3 — Groq rate limit → Gemini fallback

- Trigger a task while Groq is saturated.
- Open Trust Dashboard immediately after the task.
- Confirm the provider/model indicator reflects the fallback path, if it is shown.

Watch for:
- no hard crash, no silent false-complete state, no unsafe approval behavior, clear degradation messaging without alarmism.

### S4 — Render cold start

- After Suraj indicates the backend has been idle long enough for cold start.
- Open the app and submit a task as the first request.

Expected:
- explicit loading state, not frozen UI or an unexplained spinner for longer than 15 s.
- app recovers without needing a restart.

### S5 — Approval Screen under load

- Submit a task with a high-risk step that requires approval.
- Confirm the approval step appears in the correct state.
- Do not approve or reject unless the task is intentionally being observed for a decision path.

Must never show:
- an approved task while still pending,
- the wrong task or another user's step,
- a step executing before approval,
- stale approval controls after the decision has already been made.

### S6 — Recovery

- After load stops, rerun the S1 flow.
- Confirm the app returns to baseline behavior and that the prior error state is cleared.

## 3) Pass / fail criteria

### Fail — P0

- Any high-risk step executes without approval.
- Approval Screen shows wrong, stale, or another user's content.
- Any cross-user data renders.
- Step or task appears approved/done when backend state is blocked or rejected.

### Fail — P1

- App crashes.
- Screen stays on an unexplained spinner for more than 15 s.
- Raw stack trace or 5xx text reaches the user.
- Users are forced into a broken state without a recoverable loading message.

### Flag — P2

- Noticeably slow but still functional screens.
- Awkward/unclear loading or degradation messaging.
- Layout glitches, clipped labels, or visually misleading empty states.

### Reference target

- A simple low-risk task should complete in under 8 s on the warm path.
- Ishani's stopwatch timings are a UI-side cross-check of Suraj's p95 measurement, not a replacement for backend telemetry.

## 4) Observation log template

Use one row per observation.

No live observations are recorded yet. Add rows only after the load-test run, with screenshots or recordings linked as evidence.

| Time | Scenario | Screen | Action | Expected | Observed | Seconds to complete | Severity | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## 5) Finding capture checklist

For every P0, P1, or P2 item:

- [ ] Timestamp captured.
- [ ] Scenario ID recorded.
- [ ] Exact screen and action noted.
- [ ] Expected state written before observing the UI.
- [ ] Actual state recorded with the wording the user saw.
- [ ] Stopwatch duration recorded if relevant.
- [ ] A screenshot or screen recording captured.
- [ ] Severity labeled as P0 / P1 / P2.
- [ ] Summary filed in the issue tracker or in the D32 notes.

## 6) Issue / bug template

**Title:** D32 UI load: [screen] during [scenario] shows [problem]

- **Severity:** P0 / P1 / P2
- **Scenario:** S1 / S2 / S3 / S4 / S5 / S6
- **Environment:** deployed Render / device / emulator
- **Observed:** [what the user saw]
- **Expected:** [what should have happened]
- **Evidence:** screenshot or recording link
- **Impact:** [task blocked, UI unsafe, data misrepresented, etc.]
- **Owner:** Ishani
- **Suggested triage:** backend / UI / handed off to Suraj

## 7) Summary to Suraj

Short summary format:

- Scenarios passed: [list]
- Worst issue observed: [one sentence]
- D32 backend causes: [rate limiting, latency, fallback behavior, cold start]
- D32 UI causes: [loading state, copy, layout]
- Release impact: [pass / hold / P0 block]

## 8) Execution note for this repo

This repo is currently ready for the observation process, but the actual live load test and the device-level UI observation must be executed in the deployed environment with Suraj's load schedule and observer credentials. The key artifact here is the structured observation log and the required bug / evidence template so the run is repeatable and reviewable without guesswork.

## 9) Open questions to settle before the live D32 run

1. Does Suraj run the load against the deployed Render service or against a local backend?
2. Exact ramp schedule and how long each phase lasts.
3. Is Ishani's observer account excluded from the simulated user pool?
4. Where should the final observation log live in the repo for the team handoff?

## 10) Final handoff

- Backend-caused issues: send to Suraj immediately.
- UI-caused issues: document for D34 UI polish.
- P0 issues: escalate immediately and treat as release-blocking at Gate 4.
- Final D32 summary should be shared the same day as the run.
