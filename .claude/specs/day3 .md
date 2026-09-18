AGENTOPS COPILOT
Day 3 Feature Specification — Onboarding / Splash Screen
Owner: Ishani — Frontend Design Lead & Trust Surfaces
Day / Date: D3 · Wednesday, 26 August 2026
Screen: Onboarding / Splash (mobile/lib/features/onboarding/onboarding_screen.dart)
Depends on: D1 — design tokens & Flutter theme (theme.dart); D2 — navigation shell & routing skeleton (router.dart)
Status: Mock UI — no backend wiring on D3

1. Problem Statement
AgentOps Copilot asks a first-time user to trust an agent that will act on their behalf across Calendar, Gmail, GitHub and Slack. That trust has to start being built before the user ever signs up or connects a provider — on the very first screen they see. Per the manual's Goal G2 ("a user can always see what the agent is about to do and why, before it happens"), the onboarding experience is the earliest point where that legibility has to be established: it introduces what the app does, previews that the agent will ask permission before risky actions, and primes the user for the OAuth-connection and approval flows that come later in the build (D7–D11).
On D3 the backend does not exist beyond a FastAPI health-check (Suraj, D3) and a bare Supabase schema (D2) — there is no auth, no session, and no live profiles row to read or write. The onboarding/splash screen must therefore be built and demoable entirely as static, mocked UI: correct in layout, tokens, and navigation, with no dependency on any endpoint. Its job on D3 is to exist, look right, and hand off cleanly into the (also-mocked) Home/Dashboard shell — not to persist anything real.
2. Functional Requirements
2.1 Splash state
•On cold app launch, show a branded splash state (logo/wordmark placeholder, background per theme.dart palette) for a short, fixed duration — no network call, no auth check, since neither exists yet.
•Splash transitions automatically to the Onboarding intro; it is not a tappable/interactive screen.
2.2 Onboarding intro
•A short, swipeable multi-slide sequence (suggested: 3 slides) introducing: (1) what AgentOps Copilot does — plans and runs tasks across your tools; (2) how it stays safe — nothing risky runs without your approval; (3) what's next — connect your tools and get started.
•Each slide carries a short headline + supporting line, using theme.dart type scale and spacing tokens — no hardcoded colours or sizes.
•Slide position indicator (dots) and Skip / Next controls; last slide's primary CTA reads "Get Started" (or similar) instead of "Next".
•"Permission priming": the copy sets expectation that the app will later ask to connect Calendar/Gmail/GitHub/Slack and will always ask before a risky action — this is messaging only on D3, not a live OS permission dialog or OAuth call (those land D7 onward).
2.3 Navigation handoff
•Skip or completing the last slide routes into the app's post-onboarding shell via router.dart (D2 routing skeleton) — target route can point at the Home/Dashboard stub or Sign Up stub, whichever exists as a routed page on D3; do not hardcode a screen that bypasses the router.
•No back-navigation into the splash state once onboarding has been left.
2.4 State (design-only on D3)
•Design the widget so that a future 'has onboarding already been completed' check (backed by profiles.onboarding_completed, added in the D2 schema) can gate whether this flow shows again on relaunch. On D3, wire this as a static/mock condition (e.g. a local constant or in-memory flag) — do not call Supabase or any endpoint.
3. API Contract
Per the App Page Inventory (Section 6 of the manual), Onboarding/Splash is classified Backend dependency: None (static). D3 ships with zero live API calls. The table below documents the only related contract point in the schema, for forward-reference — it is not called from this screen on D3.
Field	Table	Type	Relevance to this screen
onboarding_completed	profiles	boolean, DEFAULT false	Intended, future gate for whether onboarding is shown again on relaunch. No read/write from this screen until auth + profiles endpoints exist (post-D4).

No request/response contract applies to D3. When wiring lands (after Suraj's auth/profile endpoints), the expected shape is a simple PATCH-style update setting onboarding_completed = true on flow exit — to be specified in that day's own contract, not this one.
4. Constraints
•Complexity is rated Low in the page inventory — the screen must not import backend clients, HTTP packages, or Supabase calls.
•Must consume design tokens exclusively from mobile/lib/core/theme.dart (D1); no ad-hoc colours, font sizes, or spacing values.
•Must be reachable only through mobile/lib/core/router.dart (D2) — no direct Navigator.push bypassing the routing skeleton, since later days extend this same router.
•No dependency on Jigyasu's Sign Up/Sign In screens, Suraj's auth endpoints, or any OAuth provider — all of that lands D4 and later.
•Must be widget-testable per Section 15.2 of the manual (render + basic-interaction coverage; contributes to the 80% overall floor). It is not one of the two safety-critical screens (Approval Screen, Plan View) held to the 100%/golden-file bar.
•Build window for this task is a single day (D3) inside a 41-day schedule — scope stays limited to splash + onboarding slides; do not scope-creep into Home/Dashboard (D4) or Sign Up (D3, owned by Jigyasu).
5. Edge Cases & Error Handling
Case	Expected handling
User skips on slide 1	Same handoff as completing the last slide — route into the app shell via router.dart; skip must not require confirmation.
Relaunch after already completing onboarding (future state)	On D3 there is no real persistence, so this cannot be triggered live; the widget should still be structured so a true onboarding_completed flag can short-circuit straight to the app shell without code changes, once wired.
Slow asset/image load on splash	Splash duration should not block on image decode; use a placeholder/solid background from theme.dart so the screen never renders blank or throws if an asset is missing.
Small/large screen sizes	Slide layout must remain legible without overflow errors on both compact phone widths and larger devices/tablets — no fixed pixel offsets.
Copy implies a live permission prompt	Explicitly avoid wording that claims a Calendar/Gmail/GitHub/Slack connection has been made or a permission has been granted — priming copy must read as forward-looking ("you'll be asked before..."), since no OAuth exists until D7.
Router target screen not yet built	If the D3 target route (Home/Dashboard or Sign Up stub) isn't fully implemented yet, the onboarding flow must still navigate to whatever stub exists per D2 rather than crash or dead-end.
Rapid repeated taps on Next/Skip	Debounce or guard navigation so multiple taps don't push the route stack more than once.
6. Acceptance Criteria
•Splash renders on cold launch using only theme.dart tokens, then auto-transitions to the onboarding slide sequence without a network call.
•All onboarding slides render with correct copy, ordering, and slide-position indicator; Skip and Next/Get Started controls are present and functional.
•Permission-priming copy is present and reads as forward-looking, not as a live permission/connection grant.
•Skip and slide-completion both route into the app shell exclusively through router.dart; no direct/bypassing navigation calls exist in the diff.
•No HTTP, Supabase, or auth-related import appears in onboarding_screen.dart — the screen is verifiably static/mock per the Section 6 page-inventory classification.
•A basic widget test (onboarding_screen_test.dart or equivalent) exists covering render and the skip/next interaction, contributing to the 80% overall widget-test coverage floor (Section 15.2).
•Screen degrades gracefully on both small and large device widths with no overflow/render errors.
•Code and design are ready to hand off into D4 (Home/Dashboard UI) without rework of the router or theme integration.

Source: AgentOps Copilot — Technical Implementation Manual v2.0 (Sections 3, 6, 7, 14, 15, 18).