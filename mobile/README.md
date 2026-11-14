# agentops_copilot

A new Flutter project.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Learn Flutter](https://docs.flutter.dev/get-started/learn-flutter)
- [Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Flutter learning resources](https://docs.flutter.dev/reference/learning-resources)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.

## Widget Testing (Day 26–30)

Widget tests covering the entry points of the core trust loop (`OnboardingScreen`, `HomeScreen`, and `TaskComposerScreen`) live under `test/screens/`:
- `test/screens/onboarding_test.dart`: verifies splash rendering, intro sequence, permission priming (microphone and notifications), forward routing, profile completion marking, and small-screen resilience.
- `test/screens/home_test.dart`: verifies task list rendering across all seven task statuses, empty state with CTA, loading state on cold start, quick-entry routing, task tap navigation, and error state retry.
- `test/screens/task_composer_test.dart`: verifies text submission, submit locking, voice mode handoff and transcription submission, 401 silent refresh/sign-in handoff, 429 rate limit messaging, input preservation on errors, and draft discard confirmation.
- `test/screens/plan_view_test.dart` and `test/screens/approval_screen_test.dart`: safety-critical plan ordering, risk/status presentation, approval decisions, fail-closed states, error handling, and deterministic golden screens.
- `test/screens/activity_log_test.dart`: audit-log rendering, newest-first ordering, fixed date/type filters, search, pagination, loading/error/empty states, and read-only behaviour.
- `test/trust_dashboard_test.dart`: live dashboard metrics, honest empty states, loading/errors, retry, and navigation.
- `test/screens/oauth_connections_test.dart`: provider connect state, backend actions, expiry and scope-mismatch states, and navigation.

### Running the tests
Run the full mobile test suite:
```bash
flutter test
```
Or run individual screen suites:
```bash
flutter test test/screens/onboarding_test.dart
flutter test test/screens/home_test.dart
flutter test test/screens/task_composer_test.dart
flutter test test/screens/plan_view_test.dart
flutter test test/screens/approval_screen_test.dart
flutter test test/screens/activity_log_test.dart
flutter test test/trust_dashboard_test.dart
flutter test test/screens/oauth_connections_test.dart
```

The two Day 27 golden tests use a fixed 1080×1920 surface at 3× pixel ratio. Review any image diff before updating a baseline. To intentionally regenerate both baselines, run `flutter test --update-goldens test/screens/plan_view_test.dart test/screens/approval_screen_test.dart`; commit the resulting files under `test/golden/` with the reviewed change.

Activity Log tests use service overrides, a fixed 2026 fixture clock, and the `/activity-log` response contract. Extend `ActivityLogService.fetchPageOverride` for new filters or pages; do not restore network fallbacks because a backend error must remain visible as an error state rather than looking like an empty or mock log.

The Trust Dashboard reads aggregate latency, cost, accuracy, and fallback metrics from `GET /dashboard/metrics` through `TrustDashboardService`; it must not query service-role tables directly. Its widget tests stub the HTTP endpoint and cover the live-data, loading, error, and no-data states.

### Extending screen tests
To add coverage or test new behavior:
1. Always isolate tests from real network calls using the static service overrides:
   - `TaskService.fetchTasksOverride`
   - `TaskService.createTaskOverride`
   - `TaskService.createVoiceTaskOverride`
   - `OnboardingService.completeOnboardingOverride`
2. Follow the test naming convention `test_<screen>_<behaviour>`.
3. Wrap widgets with `MaterialApp` using `theme: AppTheme.light` so theme design tokens are asserted.
4. Avoid flaky timers by using fake async and `tester.pumpAndSettle()` with bounded timeouts.
