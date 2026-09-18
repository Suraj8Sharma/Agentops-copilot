# Day 18 Week 3 core-loop review

## Reviewed scope

The review covered the four Ishani-owned core-loop screens:

- Home/Dashboard uses `GET /tasks` and renders live task statuses.
- Task Composer uses `POST /tasks` for text submission and preserves auth refresh behavior.
- Plan View uses `GET /tasks/{id}/plan`, renders the active plan in `step_index` order, and now shares the authenticated token provider.
- Approval Screen uses `GET /approvals/pending` and `POST /approvals/{step_id}`, never auto-approves, and keeps explanation text advisory-only.

## Verification and carry-over

The mobile suite includes service-contract and widget coverage for loading, empty, error, refresh, mixed-risk ordering, decision locking, and the end-to-end task-to-approval sequence. Direct Dart analysis and backend syntax compilation pass locally. The local Flutter runner and backend pytest collection are environment-blocked here (Flutter hangs without output; this checkout lacks the CI-installed `langgraph` dependency), so CI remains the authoritative full-suite gate. OAuth Connections wiring is the named Day 21 carry-over; Trust Dashboard and notification-banner work remain outside this review.
