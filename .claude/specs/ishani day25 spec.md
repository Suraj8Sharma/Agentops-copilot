Ishani — Day 25 Work Specification
AgentOps Copilot · Week 5 · D25 (Mon 21 Sep 2026)

Owner	Ishani
Reviewer / merger	Suraj (sole PR merger)
D25 task (Manual §14)	Frontend test-suite setup (widget-test framework, golden-screen baseline)
Related manual sections	§15.2 Flutter Widget Testing · §11 folder structure · §16.3 Definition of Done · Acceptance A7 · Gate G2
Status	Draft for review
Scope in one line: stand up the widget-test framework and the golden-file baseline so that D26–D28 can write actual per-screen tests against a working harness, not spend those days debugging setup.

Not in D25 (later days, listed so scope doesn't creep): writing the Auth screens and Voice Input tests (D26, Jigyasu), Onboarding/Home/Composer tests (D26, Ishani), Plan View / Approval Screen tests (D27, Ishani), Activity Log tests (D28, Ishani), Manual To-Do / Digest tests (D25–26, Shivangi). D25 is infrastructure, not coverage.

1. Problem Statement
By D25 every core screen has been built (§14, Weeks 1–4) but the manual's own testing plan has a gap: §15.2 names seven test files and eleven named tests across five screen owners, and Acceptance A7 requires ≥80% widget-test coverage overall and 100% on the Approval Screen and Plan View — but no widget-test framework, golden-file baseline, or shared conventions exist yet. The test/screens/ folder in §11 is currently empty.

This matters on this specific day because D26, D27 and D28 are each fully booked with actual per-screen test-writing, split across Ishani, Jigyasu and Shivangi (§14). If those days start without a working flutter test setup, a golden-file mechanism, and agreed naming/location conventions, every owner re-solves the same setup problem in parallel on their own critical day, and the two screens with a zero-tolerance safety bar — Approval Screen and Plan View (§15.2: "a silent mis-render there is a safety bug, not a cosmetic one") — are exactly the ones due first, on D27.

D25 exists to remove that risk: one person builds the framework once, so three people can write tests against it starting D26 without reinventing conventions, and CI (ci.yml, §11) can gate on it from day one instead of being retrofitted later.

2. Functional Requirements
ID	Requirement
FR1	Set up the Flutter widget-test framework (flutter_test) so flutter test runs cleanly against the current app with zero pre-existing failures, from a clean checkout.
FR2	Establish the test folder layout matching test/screens/ (§11) with one subfolder or naming pattern per screen, ready to receive the seven files named in §15.2: approval_screen_test.dart, plan_view_test.dart, oauth_connections_test.dart, activity_log_test.dart, voice_input_test.dart, settings_test.dart / memory_prefs_test.dart, manual_todo_test.dart / digest_test.dart.
FR3	Add the golden-file testing mechanism (golden_toolkit or Flutter's built-in matchesGoldenFile) and generate an initial golden-screen baseline for the two screens that require it: Approval Screen and Plan View (§15.2). Placeholder/current UI state is acceptable as the baseline; owners regenerate it once real tests land on D27.
FR4	Write one smoke test per screen (render-only, "screen builds without throwing") across all seven files, so the scaffolding is proven working end to end before D26 owners add real assertions on top of it. This is not the full coverage requirement — it is proof the harness works.
FR5	Agree and document the coverage-measurement method (flutter test --coverage, lcov) and where the report is read, so A7's 80%/100% thresholds are measurable, not just aspirational.
FR6	Wire widget tests into ci.yml (§11: "lint + test + eval-smoke") so a PR touching a screen runs that screen's widget tests, and a golden-file mismatch on the Approval Screen or Plan View fails the build rather than merging silently.
FR7	Write a short conventions doc (naming, folder placement, how to add a golden test, how to update a golden baseline intentionally) so Jigyasu, Shivangi and Sanskriti can add their own screens' tests on D26+ without asking Ishani how.
FR8	Confirm the framework supports the specific patterns the named tests in §15.2 will need: async state (pumpAndSettle), simulated tap/approve-reject flows (plan_view_test.dart, approval_screen_test.dart), and simulated listening-state changes (voice_input_test.dart). Flag any gap to the relevant owner same day rather than let them discover it on their test-writing day.
3. API Contract
D25 ships no HTTP endpoints — it is client-side test tooling. The "contract" here is the set of interfaces and conventions the framework exposes to the four other people who write tests against it in the following days.

3.1 Test command contract
# Run all widget tests
flutter test

# Run one screen's tests
flutter test test/screens/approval_screen_test.dart

# Run with coverage (feeds FR5 / A7 measurement)
flutter test --coverage
genhtml coverage/lcov.info -o coverage/html   # or equivalent, documented in FR7
3.2 Folder and naming contract
mobile/
  test/
    screens/
      approval_screen_test.dart        # Ishani — D27, golden
      plan_view_test.dart              # Ishani — D27, golden
      oauth_connections_test.dart      # Ishani — D28 (Activity Log) / already D25-ready
      activity_log_test.dart           # Ishani — D28
      voice_input_test.dart            # Jigyasu — D26
      settings_test.dart               # Ishani — D26 (Onboarding/Home/Composer day) — confirm owner
      memory_prefs_test.dart
      manual_todo_test.dart            # Shivangi — D25/26
      digest_test.dart                 # Shivangi — D25/26
    golden/
      approval_screen_baseline.png     # generated D25, regenerated D27 if UI changed
      plan_view_baseline.png
One file name per screen is fixed by §15.2; the exact subfolder split above is Ishani's proposal — confirm before D26 so nobody's PR collides on file paths.

3.3 Golden-file update contract
# Regenerate a golden baseline after an intentional UI change
flutter test --update-goldens test/screens/approval_screen_test.dart
Any PR that updates a golden image must say why in the PR description — an unexplained golden-file diff on Approval Screen or Plan View is treated as a potential safety regression, not a routine update (ties to §15.2's "never mis-render" bar).

3.4 Smoke-test contract (what FR4 produces, for the other owners to build on)
testWidgets('ScreenName renders without throwing', (tester) async {
  await tester.pumpWidget(const MyApp());
  await tester.pumpAndSettle();
  expect(find.byType(ScreenNameWidget), findsOneWidget);
});
Each named test in §15.2 (e.g. test_approval_screen_renders_risk_explanation) is added on top of this scaffold on the owner's scheduled day — D25 does not write those.

3.5 CI contract
.github/workflows/ci.yml gains (or confirms) a step:

- run: flutter test --coverage
- run: flutter test --update-goldens=false   # fail on any golden mismatch
Per A9, CI blocks merge on any failing test — this step must be in place before D26 tests start landing, or that guarantee doesn't hold for the first tests written.

4. Constraints
Ownership and process (§16.3, A9)

All changes go through a reviewed PR to Suraj; zero direct pushes to main.
Linters must stay clean; CI changes in FR6 must not break the existing lint+test+eval-smoke pipeline for the other four tracks.
Scope discipline

D25 is setup only. Writing the actual assertions named in §15.2 belongs to D26 (Jigyasu: Auth + Voice Input; Ishani: Onboarding/Home/Composer), D27 (Ishani: Plan View + Approval Screen), and D28 (Ishani: Activity Log; Shivangi: Manual To-Do/Digest overlaps D25/26). Building real tests today risks the framework itself being under-tested and blocking three people at once if it's wrong.
Safety bar (§15.2)

Approval Screen and Plan View require 100% widget-test coverage and golden-file tests — non-negotiable, unlike the 80% floor elsewhere. The framework must support golden testing correctly for these two screens specifically before D27, since there is no slack day after it in the schedule.
Team dependency

Three other people (Jigyasu, Shivangi, and Ishani herself on D26–28) depend on this framework being correct and documented by end of D25. A framework that "mostly works" costs them debugging time on their own scheduled days, which the plan has no buffer for.
Environment

Flutter/Dart version and packages must match what's already pinned in pubspec.yaml for the rest of the app; introducing a new test-only dependency (e.g. golden_toolkit) needs a version check against the existing toolchain, not an assumption of "latest."
Not specified by the manual (assumptions to confirm)

Golden-file tolerance/diffing settings (pixel-perfect vs. a small tolerance for anti-aliasing) — not stated; propose a tolerance and confirm with Suraj since CI runs on a different renderer/OS than local dev.
Exact coverage tool (lcov + genhtml vs. IDE-integrated) — not stated; pick one and document it (FR5/FR7).
Whether settings_test.dart/memory_prefs_test.dart and manual_todo_test.dart/digest_test.dart are Ishani's or Shivangi's to write is ambiguous from the D25–26 cells alone (§14) even though §15.2 says "each owner testing their own screens" and those screens belong to Shivangi (§11). Confirm folder ownership only — not authorship — is Ishani's job today.
5. Edge Cases and Error Handling
5.1 Framework setup
Scenario	Handling
flutter test fails on a clean checkout for reasons unrelated to the new setup (pre-existing broken widget, stale generated code)	Fix or flag immediately — a framework that inherits red tests is worse than no framework, since nobody can tell a new failure from an old one.
Golden-file package version conflicts with pinned Flutter/Dart SDK version	Pin a compatible version explicitly in pubspec.yaml's dev dependencies; do not silently downgrade the app's own dependencies to fit.
Golden images render differently in CI vs. local machine (font rendering, DPI)	Generate and store goldens from the same environment CI uses (or document the required flag, e.g. --update-goldens run inside the CI container), otherwise D27's golden tests will flake for everyone.
Coverage tool reports differently for generated code (e.g. .g.dart files)	Exclude generated files from the coverage calculation so A7's 80%/100% numbers reflect hand-written screen code.
5.2 Handoff to other owners (D26–28)
Scenario	Handling
An owner's screen doesn't build cleanly inside the smoke test (missing test-mode mocks for network/auth state)	Document the minimum fake/mock setup needed per screen (e.g. a fake JWT, a mock Supabase client) in the conventions doc (FR7), so D26 owners aren't blocked discovering this live.
Two owners' PRs on D26 touch overlapping test-folder files	Folder/naming contract (§3.2) is agreed and shared before D26 starts, to avoid merge collisions on the same day three people are writing tests in parallel.
A named test in §15.2 needs a framework feature not yet verified (e.g. simulating a rejected approval mid-flow, simulating a listening→final-transcript state change)	Verify the pattern works with a throwaway example during setup (FR8); if it doesn't work cleanly, flag it to the owner (Jigyasu for voice, Ishani herself for Plan View) same day, not on their test-writing day.
Owner needs to update a golden baseline after a legitimate UI change later in the project	Documented, deliberate process (§3.3) — not an ad hoc --update-goldens with no PR explanation, since an unexplained diff on the safety-critical screens is exactly the failure mode §15.2 exists to catch.
5.3 CI integration
Scenario	Handling
New widget-test CI step significantly increases pipeline runtime	Flag to Suraj (owns CI/CD, §14 D1); consider running only changed-screen tests on PR and the full suite on merge to main, if runtime becomes a blocker.
CI step added today breaks the existing lint + test + eval-smoke pipeline for other tracks (backend tests, eval pipeline)	Add the step additively and verify the full pipeline still passes for a representative backend-only PR before end of day.
No widget tests exist yet (true today, before D26) so the new CI gate has nothing to check	Fine — FR4's smoke tests are what CI checks today; this proves the wiring, not the coverage. Coverage enforcement (A7's numeric thresholds) becomes meaningful once D26–28 land.
6. Acceptance Criteria
D25 is done when every item below is true.

ID	Criterion	How it's checked
AC1	flutter test runs successfully from a clean checkout with zero failures.	Run locally + in CI
AC2	All seven test files named in §15.2 exist under mobile/test/screens/ (or the agreed subfolder layout) with at least a passing smoke test each.	File listing + flutter test output
AC3	A golden-file baseline exists and passes for both Approval Screen and Plan View.	flutter test golden comparison green
AC4	flutter test --coverage produces a readable report, and the method for checking it against the 80%/100% thresholds (A7) is documented.	Report generated, doc reviewed
AC5	ci.yml runs the widget-test step (including the golden check) on PRs touching screen code, without breaking the existing lint/test/eval-smoke pipeline.	CI run on a test PR
AC6	A short conventions doc exists covering: file/folder placement, how to add a test, how to add/update a golden test, and any mock/fake setup a screen needs.	Doc present, linked from PR
AC7	Any framework gap found against the named tests in §15.2 (async state, simulated tap flows, listening-state changes) has been flagged to the relevant D26/D27 owner the same day.	Message/comment exists
AC8	Work is merged to main through a reviewed PR (Suraj), with linters clean — no direct pushes (§16.3, A9).	PR merged
AC9	One paragraph of same-day docs exists per §16.3 (can live in the conventions doc or PR description).	Present
Open Questions and Assumptions
Subfolder layout inside test/screens/ (§3.2) is Ishani's proposal — the manual only fixes file names, not a folder split. Confirm before D26 so no PR path collisions.
Golden-file tolerance settings are not specified in the manual — propose a value and confirm, since CI and local rendering can differ.
Ownership of settings_test.dart/memory_prefs_test.dart and manual_todo_test.dart/digest_test.dart authorship is ambiguous between Ishani and Shivangi from §14's D25/D26 rows read alone; §15.2 and §11 suggest each owner tests their own screens, so Shivangi likely authors these — Ishani's D25 job is making sure the folder/harness is ready for whoever does.
Coverage tool choice (lcov/genhtml vs. another option) is not specified — pick one, document it.
CI runtime impact of adding widget tests today is unmeasured — flag to Suraj if it materially slows the pipeline.