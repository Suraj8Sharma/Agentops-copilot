Spec: Wire OAuth Connections to Real OAuth Endpoints

Owner: Ishani · Day: D21, Wed 16 Sep · Week 4 (14–19 Sep)

Derived from the AgentOps Implementation Manual (§3 Team Structure, §5.1–5.2 Auth & OAuth Scopes, §6 Page Inventory, §7 Data Model — oauth_connections, §10 API Reference, §14 Day Plan D9–D22, §15.2/§15.4 Testing, §16.3 Definition of Done, §18 A3, §19 Risk Register). Points not stated verbatim are marked [interpreted].

1. Problem Statement

The OAuth Connections screen was built against mock data back on D9, showing four provider cards (Calendar, Gmail, GitHub, Slack). Suraj's OAuth layer — consent redirect, callback/token-exchange, encrypted storage, refresh — has been live since D12, when the auth + OAuth layer froze for Week 2 (Gate 1). For four days that layer has sat unconsumed by the screen it exists to power.

D21 is where that gap closes: wire the OAuth Connections screen to the real endpoints so a user can actually connect, see the status of, and disconnect each provider. This is deliberately scoped to the happy path — connect, see status, disconnect. §14 shows the next day, D22, is dedicated separately to "OAuth Connections — edge cases: revoke, re-auth, scope-mismatch states," which means D21's job is to get the baseline flow working correctly, not to exhaustively handle every failure mode in one sitting.

This screen carries real weight beyond its own page: A3 requires OAuth token refresh to succeed automatically in ≥95% of expiry-simulation runs, with failures surfacing a clear re-auth prompt rather than a silent failure — and this screen is the user-facing surface where that prompt has to land. It also gates Gate 2 (19 Sep), which explicitly lists "OAuth Connections wired to real data" as Ishani's line item.

Explicitly not in scope for D21: the OAuth backend itself (Suraj, D7–D12, already frozen); revoke/re-auth/scope-mismatch edge-case handling (Ishani, D22); the OAuth/JWT automated test suite (Suraj, D27); Week-4 PR merge (D24, separate task).

2. Functional Requirements
FR1 — Render real connection state per provider. For each of the four providers (google_calendar, gmail, github, slack), the screen shows the real oauth_connections row for the current user, or a "not connected" state if none exists.
FR2 — Connect flow. Tapping "connect" on a provider starts the real consent redirect via GET /oauth/{provider}/connect.
FR3 — Callback completes the connection. After consent, GET /oauth/{provider}/callback exchanges the code and stores the encrypted token pair; the screen reflects the new active status once complete.
FR4 — Disconnect flow. Tapping "disconnect" calls DELETE /oauth/{provider} and the screen reflects the provider returning to a disconnected state.
FR5 — Status reflects the status enum. The screen must render active, expired, revoked, and scope_mismatch distinctly — even if full edge-case handling for the latter three is D22's job, the screen must not misrepresent a non-active status as active on D21. [interpreted — D21 vs D22 split is inferred from the day-plan sequencing]
FR6 — Per-provider independence. Connecting or disconnecting one provider must not affect another — mirrors the manual's design intent that revoking Gmail doesn't revoke Calendar, since each is provider-scoped.
FR7 — Correct connect-state per provider on the widget test level. Must satisfy test_oauth_connections_shows_correct_connect_state_per_provider (§15.2).
FR8 — Wired, not mocked. No fallback to the D9 mock data once wiring is complete — this is the same "mock → real" transition pattern as Ishani's D13–D16 core-loop screens.
3. API Contract

All routes sit behind the JWT-verification dependency (§5.1).

Method	Path	Auth	Purpose
GET	/oauth/{provider}/connect	JWT	Start the OAuth consent redirect for a provider
GET	/oauth/{provider}/callback	JWT	Exchange the authorization code, store encrypted tokens
DELETE	/oauth/{provider}	JWT	Disconnect / revoke a provider connection

{provider} values: google_calendar, gmail, github, slack (matches the oauth_connections.provider CHECK constraint).

oauth_connections row the screen renders (§7):

Column	Type / Constraint	Notes
provider	text, CHECK IN (google_calendar,gmail,github,slack)	
access_token	text, ENCRYPTED	Never logged in plaintext — never surfaced to the client either
refresh_token	text, ENCRYPTED, nullable	GitHub classic tokens may not rotate
scopes	text[]	Granted OAuth scopes, audited against risk_rules
expires_at	timestamptz	
status	text, default active	active | expired | revoked | scope_mismatch
connected_at	timestamptz, default now()	

RLS: user_id = auth.uid() for SELECT/UPDATE/DELETE; INSERT restricted to the OAuth callback service role — the client never inserts a connection row directly, only triggers the flow that causes the backend to.

What the screen must never receive: access_token / refresh_token values. The contract only exposes provider, scopes, expires_at, status, connected_at — never the encrypted credentials themselves.

4. Constraints
Backend has been frozen and stable since D12 (Gate 1) — this is wiring against a settled contract, not a moving one, unlike some of Ishani's earlier D13–D16 wiring which chased backend work landing the same week.
Provider independence is load-bearing (§5.2): tokens are provider-scoped; revoking Gmail must not revoke Calendar. The UI must reflect four independent connection states, not one combined auth state.
Encrypted tokens never reach the client. access_token/refresh_token are encrypted at rest (pgsodium/vault) and never logged in plaintext (§7, test_oauth_token_encrypted_at_rest) — the screen has no legitimate reason to ever see raw token values.
A3 is riding on this screen. ≥95% automatic refresh success, and any failure must surface a clear re-auth prompt — never a silent failure. The connect/disconnect wiring done D21 is the foundation D22's edge-case handling builds the re-auth prompt onto.
Provider-specific refresh quirks (§5.2) the screen's state model must be compatible with even if full handling is D22's: Google tokens refresh silently server-side; GitHub classic tokens don't expire on a schedule but can be revoked anytime from GitHub settings; Slack bot tokens don't expire under normal operation but an uninstalled app returns invalid_auth.
Testing-mode 7-day expiry (D9, §19 Risk Register): Google OAuth in testing mode has a 7-day token lifetime with an automated re-auth reminder already built — the screen's status display is what that reminder ultimately surfaces through.
Coverage expectations (§15.2): OAuth Connections isn't in the 100%-coverage tier (that's Approval Screen and Plan View only), but still needs render + basic-interaction coverage as part of the 80% overall floor.
Definition of Done (§16.3): reviewed PR, passing tests, clean linters, fail-closed/fail-open behaviour verified on this risk-adjacent path, same-day doc paragraph.
5. Edge Cases & Error Handling

Full edge-case ownership sits with D22 — these are the failure modes the D21 wiring must not actively break, even before D22 builds out dedicated handling.

Case	Expected Handling
No connection exists for a provider	Screen shows a clean "not connected" / "connect" state, not an error.
Connection exists with status = expired	Screen must show it as expired, not silently render it as active (FR5).
Connection exists with status = revoked	Screen must show it as revoked/disconnected, not stale-active.
Connection exists with status = scope_mismatch	Screen must render a distinct state, even if the full "disables feature gracefully" behavior (test_oauth_scope_mismatch_disables_feature_gracefully) is D22's build-out.
User cancels the consent flow mid-redirect	Screen returns to "not connected" rather than a stuck or ambiguous loading state. [interpreted]
Callback fails to exchange the code	Screen surfaces a clean error, consistent with the "typed error, not a retry loop" pattern used for GitHub 401s (§5.2).
Disconnect call fails (network, backend error)	Screen must not optimistically show "disconnected" before the backend confirms — avoids a state mismatch with oauth_connections. [interpreted]
Token expired mid-task elsewhere in the app	Reflected consistently here too — this screen is the canonical place a user checks/fixes provider connection state (A3).
Render cold start during connect/callback round-trip	Explicit loading state, not a spinner that reads as broken (§2.3), same principle applied to the OAuth redirect round-trip. [interpreted]
Reconnecting a provider that was previously revoked	Runs the same connect flow as a first-time connection; no special-cased "reconnect" path assumed unless the backend contract requires one. [interpreted]
6. Acceptance Criteria
AC1: All four providers (google_calendar, gmail, github, slack) render their real oauth_connections state — no mock data remains on this screen.
AC2: Connect flow works end-to-end for at least one provider in a live test: tap connect → consent redirect → callback → screen shows active.
AC3: Disconnect flow works end-to-end: tap disconnect → DELETE /oauth/{provider} → screen reflects disconnected state.
AC4: test_oauth_connections_shows_correct_connect_state_per_provider passes (§15.2).
AC5: Connecting or disconnecting one provider is verified to leave the other three providers' state unchanged.
AC6: The screen never displays or logs a raw access_token/refresh_token value.
AC7: All four status values (active, expired, revoked, scope_mismatch) render as visually distinct states, ready for D22 to build full edge-case behavior on top of.
AC8: Definition of Done met per §16.3: PR reviewed and merge-ready, tests passing, linters clean, same-day doc paragraph.
AC9: Feeds Gate 2 (19 Sep): OAuth Connections is one of the five screens confirmed "wired to real data."