AgentOps Copilot — Feature Spec
OAuth Connections Screen — Day 9
Owner: Ishani (Frontend Design Lead & Trust Surfaces)
Sprint day: D9 · Wed 2 Sep 2026
Scope for this day: Static/mock UI build only — 4 provider cards (Google Calendar, Gmail, GitHub, Slack). Wiring to real /oauth endpoints is D21; edge-case states (revoke, re-auth, scope-mismatch) are D22.
Source: AgentOps Implementation Manual — Sections 3, 5.2, 6, 7, 10, 14, 15, 18
1. Problem Statement
The app connects to four third-party providers — Google Calendar, Gmail, GitHub, and Slack — so the agent can act on the user's behalf (create events, send drafts, open issues, post messages). Each connection is a separate OAuth authorization-code grant with its own token pair, scopes, and expiry behavior (Section 5.2).
Today there is no screen where a user can see which providers are connected, connect a new one, or disconnect an existing one. Without it: (a) a user has no way to grant the access a task needs before submitting it, (b) there is no visible surface for the trust story the rest of the app depends on — every OAuth-backed action assumes the user consciously connected that provider, and (c) downstream screens (Trust Dashboard, Approval Screen) that reference provider state have nothing to point to.
Day 9 builds the screen shell and visual states against mock data only, so the layout, states, and per-provider card design are locked before Suraj's OAuth layer (live since D12, per D21) is wired in on D21. This keeps Ishani unblocked and gives the team a stable UI contract to build the backend integration against.
2. Functional Requirements
2.1 Core behavior (in scope for D9)
•Render one connection card per provider, in a fixed order: Google Calendar, Gmail, GitHub, Slack.
•Each card shows: provider icon/logo, provider display name, connection status (Connected / Not Connected), and a primary action button (Connect / Disconnect) that reflects that status.
•Each card in the "Connected" mock state additionally shows the granted scopes (human-readable, not raw scope strings) and a "connected since" or "last verified" timestamp.
•Tapping "Connect" on a Not-Connected card and tapping "Disconnect" on a Connected card both trigger local mock-state toggles only — no network call yet (that lands D21).
•Screen is reachable from wherever the app's navigation shell (router.dart) places it, consistent with the other core-trust-loop screens Ishani owns (Onboarding, Home, Task Composer, Agent Plan View, Approval Screen, Trust Dashboard).
•Screen uses the shared design system (theme.dart — colour, type, spacing tokens) rather than one-off styling, so it matches Approval Screen and Plan View visually.
2.2 Out of scope for D9 (explicitly deferred)
•Real OAuth consent redirect / callback wiring — D21, against GET /oauth/{provider}/connect and GET /oauth/{provider}/callback.
•Live disconnect against DELETE /oauth/{provider} — D21.
•Edge-case states: revoked, re-auth-required, scope-mismatch — D22.
•Token-refresh-triggered UI changes — depends on Suraj's D9 token-refresh job but is a backend concern; the screen only needs to be able to render a resulting status value later.
3. API Contract
These are the endpoints this screen is designed against. They are not called on D9 (mock data only) but the screen's data model and states must match this contract so D21 wiring is a swap, not a rebuild.
Method	Path	Auth	Purpose
GET	/oauth/{provider}/connect	JWT	Start the OAuth consent redirect for a provider
GET	/oauth/{provider}/callback	JWT	Exchange the authorization code, store encrypted tokens
DELETE	/oauth/{provider}	JWT	Disconnect / revoke a provider connection

Provider connection state is read from the oauth_connections table (one row per user+provider). The screen's mock data should mirror this shape:
Field	Type	Notes
provider	enum	'google_calendar' | 'gmail' | 'github' | 'slack'
status	enum	'active' | 'expired' | 'revoked' | 'scope_mismatch' (D9 mock only needs active / not-connected; the other three are D22)
scopes	string[]	Granted OAuth scopes — map to human-readable labels for display, never show raw scope strings
expires_at	timestamptz	Used for "connected since / last verified" display, not for logic on D9
connected_at	timestamptz	Used for "connected since" display

3.1 Per-provider scopes (for the human-readable label mapping)
Provider	Scopes requested	Suggested display label
Google Calendar	calendar.events (read/write on events only)	"Can view and create calendar events"
Gmail	gmail.send, gmail.compose (+ read scope only if a read-type step is added later)	"Can draft and send email on your behalf"
GitHub	repo-scoped OAuth (issue/comment creation only)	"Can create issues and comments on your repos"
Slack	chat:write, channels:read (scoped to a single workspace install)	"Can post messages in one connected workspace"
4. Constraints
•Design tokens only — use theme.dart values for colour/type/spacing; no hard-coded styling, per Ishani's Section 3 ownership of the design system.
•Fixed provider order and exactly four cards for MVP — no dynamic provider list; adding a fifth provider is out of scope.
•No raw OAuth scope strings ever rendered directly to the user — always map through the display-label table above.
•No plaintext tokens touch the client at any point — access_token and refresh_token are encrypted server-side (pgsodium/vault) and this screen never receives or stores them; it only reads status/scopes/timestamps.
•Screen must be built against the shared navigation shell and design system already scaffolded by D2 (router.dart, theme.dart) — no parallel routing or styling system.
•Widget-test coverage floor of 80% applies to this screen (Acceptance A7); it is not one of the two 100%-coverage/golden-test screens (Approval Screen, Plan View), but still needs render + basic-interaction tests.
•Mock data must be structurally identical to the real oauth_connections row shape (Section 3 above) so D21 can wire real data with no UI-layer changes.
5. Edge Cases
Edge case	Expected D9 (mock) behavior	Where it's fully handled
Provider not yet connected	Card shows "Not Connected" state + Connect button	D9 (this spec)
Provider connected	Card shows "Connected" state, scopes, connected-since timestamp + Disconnect button	D9 (this spec)
Token expired mid-task (Google Calendar)	Task pauses, status set to failed with a re-auth reason	Backend D9 (Suraj's token-refresh job); screen reflects this once wired, D21/D22
Gmail send step blocked by expired token	Draft steps degrade to "saved, not sent"; send steps surface a re-auth prompt instead of silent failure	D22
GitHub token revoked by user externally	GitHub returns 401; MCP client surfaces a clean, typed error rather than retrying	D22
Slack app uninstalled from workspace	Slack returns invalid_auth; OAuth Connections screen shows the provider as disconnected	D22 — this is the literal spec for this screen's revoked state
Scope mismatch (granted scopes narrower than requested)	status = scope_mismatch on the row	D22
User taps Connect/Disconnect rapidly / double-tap	Local mock toggle only on D9 — button should still debounce or disable while "in flight" so the pattern is already correct before D21 adds a real request	D9 (defensive UI), verified for real on D21
6. Error Handling
D9 ships mock UI only, so there are no real network errors yet — but the screen should be built so real error handling (D21/D22) drops in without restructuring:
•Design the Connect/Disconnect action as an async-capable handler now (even though it resolves locally on D9), so D21 can swap the mock resolution for a real API call without changing the widget tree.
•Reserve a visible state for a failed connect/disconnect attempt (e.g. inline error text or a snackbar) even if unreachable on D9 — this becomes live when /oauth/{provider}/connect or DELETE /oauth/{provider} can actually fail.
•Per Section 5.2's provider table, each provider fails differently — Calendar/Gmail failures are refresh-token issues surfaced as a re-auth prompt, GitHub failures are a clean typed 401 error (not a retry loop), and Slack failures are an invalid_auth error that flips the card to disconnected. The screen's state model should be generic enough to represent all three outcomes (needs re-auth / typed error / disconnected) without special-casing each provider's UI.
•Never surface a raw backend error string or stack trace in a card — every failure state should resolve to one of the pre-defined card states (Not Connected / Connected / Needs Re-auth / Error), consistent with the "fail-closed, no silent failure" principle used across the app (Section 4, Section 5.2 Acceptance A3).
•No approval-gate or risk implications for this screen itself — connecting/disconnecting a provider is not a risk-rules-gated action — but downstream actions that use these tokens are, so this screen must never imply an action succeeded when only the connection step did.
7. Acceptance Criteria
#	Criterion
AC1	All 4 provider cards (Google Calendar, Gmail, GitHub, Slack) render in the fixed order, each showing provider name, icon, and current mock status.
AC2	A Not-Connected card shows a Connect button; tapping it flips the card to the Connected state (mock, no network call).
AC3	A Connected card shows Disconnect, human-readable granted scopes (from the label-mapping table, never raw scope strings), and a connected-since/last-verified timestamp; tapping Disconnect flips it back to Not Connected (mock).
AC4	All styling comes from theme.dart design tokens — no hard-coded colors, fonts, or spacing values in the screen file.
AC5	Mock data model matches the oauth_connections row shape (provider, status, scopes, expires_at, connected_at) so no data-shape changes are needed when D21 wires real endpoints.
AC6	oauth_connections_test.dart exists with at minimum test_oauth_connections_shows_correct_connect_state_per_provider passing, per Section 15.2.
AC7	Widget-test coverage for this screen is at or above the 80% floor (Acceptance A7).
AC8	Screen is reachable via the app's navigation shell (router.dart) alongside the other core-trust-loop screens.
AC9	No plaintext token values, and no raw OAuth scope strings, ever appear in rendered UI or test fixtures.

Key file: mobile/lib/features/oauth_connections/oauth_connections_screen.dart — Ishani
Related test file: mobile/test/.../oauth_connections_test.dart