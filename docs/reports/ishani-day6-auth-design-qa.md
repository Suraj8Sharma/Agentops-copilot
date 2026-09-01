# D6 Auth Screens Design QA

**Reviewer:** Ishani (Frontend Design Lead)  
**Date:** 29 August 2026  
**Scope:** Sign Up (D3), Sign In (D4), and Forgot Password / OTP (D5) only  
**Source of truth:** `mobile/lib/core/theme.dart` (D1 tokens and `AppTheme.light`)

## Review outcome

The three routes are structurally consistent because each screen delegates to the
same `ScreenStub` and is presented by the shared application theme. The review is
complete, but the auth set is not functionally ready for a product merge: all three
screens remain placeholders and the shared stub contains spacing literals instead of
D1 spacing tokens.

The Week-1 foundations (theme, router, and screen-shell wiring) are mergeable with
the follow-up items below visible in the PR. The auth UI work should be treated as a
tracked fast-follow, with the P0 item blocking any claim that the auth flow is ready
for user testing. No screen code was redesigned during this review.

## Evidence matrix

| Area | Expected from D1 / shared flow | Sign Up | Sign In | Forgot Password / OTP | Result |
|---|---|---|---|---|---|
| Theme | `AppTheme.light` and shared `AppColors` | Shared stub | Shared stub | Shared stub | Pass |
| Typography | Theme text styles, no screen-local scale | AppBar/title use theme | AppBar/title use theme | AppBar/title use theme | Pass for shell |
| Spacing | `AppSpacing` 4 px scale | `ScreenStub` uses 24/12/4 literals | Same | Same | P1 deviation |
| Inputs | Consistent themed `InputDecoration` | Missing | Missing | Missing | P0 deviation |
| Primary action | Consistent themed button treatment | Missing | Missing | Missing | P0 deviation |
| Validation/errors | Shared field/error presentation | Missing | Missing | Missing | P0 deviation |
| Loading | Shared submitting/loading treatment | Missing | Missing | Missing | P0 deviation |
| Navigation continuity | Auth routes remain named and routable | Pass | Pass | Pass | Pass |

## Follow-up findings

### AUTH-D6-001 — Auth screens are still placeholder shells

- **Severity:** P0 / merge-blocking for auth-flow readiness
- **Screens:** Sign Up, Sign In, Forgot Password / OTP
- **Element:** Entire screen body
- **Expected:** Each screen exposes its assigned form/action state while using the
  shared input, button, validation, error, and loading patterns.
- **Actual:** Each screen renders `ScreenStub(title, owner: 'Jigyasu')`; there are no
  fields, actions, validation states, error messages, or loading states to review.
- **Owner:** Jigyasu
- **Action:** Replace each stub on the owning implementation pass, then rerun the
  D6 QA matrix and add interaction tests for valid, invalid, error, and loading
  states. Keep API bindings out of this design-QA change.

### AUTH-D6-002 — Shared stub spacing bypasses D1 spacing tokens

- **Severity:** P1 / fast-follow
- **Screens:** All three through `mobile/lib/core/widgets/screen_stub.dart`
- **Element:** Body padding and vertical gaps
- **Expected:** Use `AppSpacing.screenPadding`, `AppSpacing.md`, and `AppSpacing.xs`
  (or another documented D1 token) for the shared shell.
- **Actual:** The shell uses literal `24`, `12`, and `4` values.
- **Owner:** Ishani with the shell owner
- **Action:** Update the shared shell or replace it during the auth implementation
  pass; do not patch the three auth screens independently.

### AUTH-D6-003 — Validation, error, and loading contracts are undocumented

- **Severity:** P1 / fast-follow
- **Screens:** All three
- **Element:** Cross-screen interaction states
- **Expected:** One documented pattern for field errors, form-level errors, disabled
  actions, and loading feedback, using `AppColors.error` and themed controls.
- **Actual:** D1 defines semantic error colour and themed controls, but no auth
  state contract exists because the screens are placeholders.
- **Owner:** Ishani + Jigyasu
- **Action:** Agree the pattern before the next auth implementation review and add
  it to the auth widget tests.

## Week-1 merge note

QA input is ready for the Saturday PR conversation. Merge of the Week-1 foundation
is acceptable only with `AUTH-D6-001` through `AUTH-D6-003` linked in the PR and the
P0 status called out. This review made no ad-hoc visual changes to Jigyasu's files.

