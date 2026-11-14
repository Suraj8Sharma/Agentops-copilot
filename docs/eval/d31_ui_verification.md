# D31 UI Verification Handoff

- **Owner:** Ishani
- **Supporting backend owner:** Suraj
- **Planned day:** D31 (2026-09-28, per the Day 31 spec)
- **Verification status:** Pending — no run results or evidence were supplied for this handoff.

## Purpose and scope

Record the UI-side checks for Suraj's approval-gate bypass and agent-loop end-to-end tests. The UI must not show a blocked high-risk action as approved, executing, or done, and must not imply that an unconfirmed action succeeded.

Screens in scope: Home, Task Composer, Plan View, Approval Screen, Activity Log, and Notifications when following an approval notification. This is a verification handoff, not a record of completed test runs. No gate logic or backend behavior was changed here.

## Expected end-to-end behavior

| Scenario | Expected behavior | Result | Evidence |
| --- | --- | --- | --- |
| Text task completes full loop | Plan View shows the low-risk calendar step and high-risk email step in order. The email waits for explicit approval; after approval, both steps and the task show their confirmed completed state. Activity Log records the steps. | Pending | Not provided |
| Low-risk action | The action completes without showing an Approval Screen or creating a pending approval. | Pending | Not provided |
| High-risk action waits | The step and task remain awaiting approval until a decision; the email/event does not appear in the mock or sandbox beforehand. | Pending | Not provided |
| Rejected approval | The step remains rejected, the task is not shown as completed, dependent steps do not run, and there is no mock/sandbox side effect. | Pending | Not provided |
| Mixed-risk plan | Low-risk steps run when ready; only the high-risk step pauses, and the UI presents the order and statuses accurately. | Pending | Not provided |
| App closed during approval | After reopening, the pending approval is still visible and the task resumes from its saved state after a decision. | Pending | Not provided |
| Voice task (Jigyasu-supported) | Confirm that the voice task appears accurately in Home, Plan View, and Approval Screen. | Pending | Not provided |

## Approval-gate bypass observations

| Scenario | Expected UI/system behavior | Result | Evidence |
| --- | --- | --- | --- |
| Double-tap or replay a decision | Exactly one decision/action occurs; controls lock after the first decision. | Pending | Not provided |
| Reopen an already decided step | The current state is shown and no actionable Approve control is offered. | Pending | Not provided |
| Approve after rejection, cancellation, or halt | The decision is refused; terminal state remains and nothing executes. | Pending | Not provided |
| Replay a step from another user | Access is refused, another user's data is not rendered, and nothing executes. | Pending | Not provided |
| Missing/unknown risk tier or action type | The action fails closed and remains approval-gated. | Pending | Not provided |
| Malformed or tampered plan | The UI does not crash or mark a step approved; it surfaces an error state. | Pending | Not provided |
| Leave, background, or navigate away | No decision is sent; the step remains pending. | Pending | Not provided |
| Tap stale approval notification | The current state is opened instead of a stale approval prompt. | Pending | Not provided |
| Token expires during approval | Refresh/re-authentication is handled without assuming a decision was recorded. | Pending | Not provided |
| Network drops after Approve | Outcome is treated as unknown; state is re-fetched and no success is shown until confirmed. | Pending | Not provided |

## Audit trail checks

| Check | Expected evidence | Result | Evidence |
| --- | --- | --- | --- |
| Approved high-risk step | `approval_requested` and `approval_decided (approved)` precede the high-risk `tool_called` event. | Pending | Not provided |
| Rejected step | `approval_requested` and `approval_decided (rejected)` are present; no `tool_called` event exists for that step. | Pending | Not provided |
| Blocked bypass attempt | No `tool_called` event exists for the blocked high-risk step. | Pending | Not provided |

## Run details and evidence to add

- Actual run date/time: not provided
- Build/version and target environment: not provided
- Test user/account: not provided
- Backend test runs and results: not provided
- Screenshots or screen recordings: not provided
- Mock/sandbox call log: not provided
- Findings, severity, and issue links: not provided

For each run, record the scenario ID, result, and timestamp, and attach Plan View, Approval Screen, and Activity Log evidence as applicable, together with the mock/sandbox call log. A missing result or artifact is not a pass.
