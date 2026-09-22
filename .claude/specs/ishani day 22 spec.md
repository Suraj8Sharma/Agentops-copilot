
Spec: OAuth Connections — Edge Cases: Revoke, Re-Auth, Scope-Mismatch States

Owner: Ishani · Day: D22, Thu 17 Sep · Week 4 (14–19 Sep)

Derived from the AgentOps Implementation Manual (§5.1–5.2 Auth & OAuth Scopes/Token Behaviour, §7 Data Model — oauth_connections, §14 Day Plan D9/D21/D22, §15.2/§15.4 Testing, §16.3 Definition of Done, §18 A3, §19 Risk Register). Points not stated verbatim are marked [interpreted].

1. Problem Statement

D21 wired the OAuth Connections screen to the real endpoints for the happy path — connect, view status, disconnect — across all four providers. That covers a user who connects cleanly and stays connected. It does not cover what actually happens to a token over time: Google's testing-mode tokens expire in 7 days, GitHub tokens can be revoked from GitHub's own settings at any moment with no warning, Slack tokens go invalid the instant someone uninstalls the workspace app, and a scope can simply stop matching what a feature needs.

D22 is where those failure modes get built out on the screen, not just tolerated by it. The manual is explicit that each provider fails differently — a Google token failure mid-task sets the task to failed with a re-auth reason; a Gmail send step (already approval-gated) surfaces a re-auth prompt instead of failing silently, while a draft step just degrades to "saved, not sent"; a revoked GitHub token comes back as a clean typed 401, not a retry loop; an uninstalled Slack app shows the provider as disconnected. None of that is generic error handling — it's four distinct, provider-specific behaviours the screen has to represent correctly.

This work also directly answers A3: OAuth token refresh must succeed automatically in ≥95% of expiry-simulation runs, and on the failure side, a clear re-auth prompt must appear — never a silent failure. D21 built the plumbing; D22 is what makes that acceptance criterion actually demonstrable on-screen. It also closes out the eval-relevant OAuth test suite (test_oauth_scope_mismatch_disables_feature_gracefully, test_oauth_revoked_access_returns_clean_error, test_oauth_7day_testing_mode_expiry_is_flagged) at the UI layer, ahead of Gate 2 the next day.

Explicitly not in scope for D22: the OAuth backend/token-refresh job itself (Suraj, D9, already live); the connect/disconnect happy-path wiring (Ishani, D21, already done); the automated OAuth/JWT pytest suite (Suraj, D27); notifications for oauth_expiring banner copy (Ishani, D20 — related but a separate surface).

2. Functional Requirements
FR1 — Revoked-token state renders correctly per provider. A connection with status = revoked (or a live 401/invalid_auth from the provider) shows as revoked/disconnected on the screen, using the provider-specific detection the manual describes (GitHub 401, Slack invalid_auth).
FR2 — Re-auth prompt on expiry/failure. When a token fails to refresh or has expired, the screen surfaces a clear, actionable re-auth prompt — never a silent failure (A3).
FR3 — Scope-mismatch state disables the affected feature gracefully. A connection with status = scope_mismatch must visibly and gracefully disable whatever feature depends on the missing scope, per test_oauth_scope_mismatch_disables_feature_gracefully — not crash, not silently no-op.
FR4 — Testing-mode 7-day expiry is flagged proactively. Building on D9's detection job, the screen must surface the flag before the Google testing-mode token actually expires, not just after (test_oauth_7day_testing_mode_expiry_is_flagged).
FR5 — Task-level failure reason is visible where relevant. When a mid-task token failure sets a task to failed, the re-auth reason attached to that failure must be surfaces-able from the OAuth Connections screen, not only buried in task detail. [interpreted]
FR6 — Gmail send vs. draft distinction respected. A failed Gmail send step (already approval-gated) surfaces a re-auth prompt; a failed draft step degrades gracefully to "saved, not sent" — these are different UX outcomes for the same underlying token failure and must not be collapsed into one generic error.
FR7 — Re-auth flow re-enters the existing connect path. Prompting a user to re-authenticate must route back through the same GET /oauth/{provider}/connect flow wired on D21, not a separate mechanism.
FR8 — Provider independence holds under failure too. One provider entering expired/revoked/scope_mismatch must not affect the displayed state of the other three.
3. API Contract

No new endpoints — D22 builds edge-case handling on top of the D21 contract, reading the same fields with sharper state logic.

Method	Path	Auth	Purpose (unchanged from D21)
GET	/oauth/{provider}/connect	JWT	Start consent redirect — also the re-auth entry point
GET	/oauth/{provider}/callback	JWT	Exchange code, store encrypted tokens
DELETE	/oauth/{provider}	JWT	Disconnect / revoke

State the screen must now interpret, not just display (oauth_connections, §7):

Field	Values relevant to D22
status	active | expired | revoked | scope_mismatch — all four now need distinct on-screen behaviour, not just distinct labels
scopes	text[] — compared against what the current feature set requires, to detect scope mismatch
expires_at	timestamptz — compared against now() to drive the 7-day testing-mode flag

Provider-specific failure signals the screen must translate (§5.2, not part of the oauth_connections schema itself but surfaced through it):

Provider	Failure signal	Screen behaviour
Google Calendar	Task fails mid-step with re-auth reason	Re-auth prompt; 7-day testing-mode flag shown ahead of expiry
Gmail	Send step fails post-approval / draft step fails	Send → re-auth prompt; Draft → "saved, not sent" (no prompt)
GitHub	401 from GitHub on a revoked token	Clean typed error, connection shown as revoked — no retry loop
Slack	invalid_auth on an uninstalled app	Provider shown as disconnected

Task-level linkage: a task that failed due to OAuth expiry carries a re-auth reason on its status = failed record — the screen should be able to point back to (or be pointed to from) that context. [interpreted — the manual states the task-side behaviour but not the screen-side linkage mechanism]

4. Constraints
Four providers, four different failure semantics. There is no single generic "token failed" state that covers Google, Gmail, GitHub, and Slack correctly — the manual is explicit that each behaves differently, and the UI must not paper over that with one shared error state.
Never silent. The single hard line running through this whole task: expiry or failure must always surface a clear re-auth prompt, per A3 — silent failure is the one outcome explicitly ruled out.
Authorization stays two-layered (§5.1). A valid, non-expired token is necessary but never sufficient for a high-risk action — risk_rules and the approval gate still govern what's allowed, independent of whether the OAuth layer is healthy.
Re-auth reuses the existing flow. No new OAuth mechanism is introduced for re-auth — it is the same consent redirect wired on D21.
7-day testing-mode window is real and short. Because the Google Cloud app is unverified during development, this isn't a rare edge case to deprioritize — it recurs roughly weekly and is called out separately in the risk register as something already mitigated by a same-day fresh consent pass before the D39 demo rehearsal.
Coverage expectations (§15.2): OAuth Connections sits in the 80%-overall floor, not the 100% tier — but the named OAuth test suite (§15.4) must pass regardless of tier.
Definition of Done (§16.3): reviewed PR, passing tests, clean linters, fail-closed behaviour verified (directly relevant here, since a mishandled re-auth path is exactly the kind of risk-adjacent gap DoD exists to catch), same-day doc paragraph.
One day out from Gate 2 (19 Sep). OAuth Connections wired-to-real-data is a named Gate 2 item; D22 is the last scheduled day to get its failure states right before that checkpoint.
5. Edge Cases & Error Handling
Case	Expected Handling
Google Calendar token expires mid-task	Task pauses at the failing step, status = failed, clear re-auth reason attached; screen surfaces the re-auth prompt.
Google testing-mode token approaching 7-day expiry	Flagged proactively, ahead of actual expiry, per D9's detector (test_oauth_7day_testing_mode_expiry_is_flagged).
Gmail send step fails on an expired token	Re-auth prompt shown (send is already approval-gated, so this is a real user-facing gap, not a background retry).
Gmail draft step fails on an expired token	Degrades gracefully to "saved, not sent" — explicitly not a re-auth prompt for this case.
GitHub token revoked by the user from GitHub's own settings	401 surfaces as a clean, typed error (test_oauth_revoked_access_returns_clean_error) — no retry loop.
Slack app uninstalled from the workspace	invalid_auth maps to the provider showing as disconnected on the OAuth Connections screen.
Scope no longer covers a feature the app needs	status = scope_mismatch; that specific feature disables gracefully rather than erroring or silently failing (test_oauth_scope_mismatch_disables_feature_gracefully).
User re-authenticates after a revoke/expiry	Re-enters the D21 connect flow; on success, status returns to active and any disabled feature re-enables. [interpreted]
Multiple providers fail simultaneously	Each renders and re-auths independently — no cross-provider coupling in either failure or recovery (FR8).
Re-auth prompt shown but user dismisses without acting	Prompt/flag persists rather than disappearing after one view — a dismissed warning about a broken connection shouldn't look resolved. [interpreted]
6. Acceptance Criteria
AC1: All four oauth_connections.status values render with correct, distinct, provider-appropriate on-screen behaviour — not just distinct labels.
AC2: test_oauth_revoked_access_returns_clean_error passes for GitHub.
AC3: test_oauth_scope_mismatch_disables_feature_gracefully passes.
AC4: test_oauth_7day_testing_mode_expiry_is_flagged passes, with the flag visibly surfaced ahead of actual expiry.
AC5: A simulated Gmail send-step failure shows a re-auth prompt; a simulated Gmail draft-step failure shows "saved, not sent" with no prompt — verified as two distinct outcomes.
AC6: No scenario in this spec results in a silent failure — every expiry/revoke/mismatch path ends in a visible, correct state or prompt (A3).
AC7: Re-authenticating from a failed state successfully restores active status via the existing D21 connect flow, with no separate re-auth mechanism introduced.
AC8: Provider independence holds under failure — one provider's failure state is verified not to alter the other three.
AC9: Definition of Done met per §16.3, and OAuth Connections stands as a fully wired, failure-aware Gate 2 item going into 19 Sep.