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

## Widget Testing (Day 26)

Widget tests covering the entry points of the core trust loop (`OnboardingScreen`, `HomeScreen`, and `TaskComposerScreen`) live under `test/screens/`:
- `test/screens/onboarding_test.dart`: verifies splash rendering, intro sequence, permission priming (microphone and notifications), forward routing, profile completion marking, and small-screen resilience.
- `test/screens/home_test.dart`: verifies task list rendering across all seven task statuses, empty state with CTA, loading state on cold start, quick-entry routing, task tap navigation, and error state retry.
- `test/screens/task_composer_test.dart`: verifies text submission, submit locking, voice mode handoff and transcription submission, 401 silent refresh/sign-in handoff, 429 rate limit messaging, input preservation on errors, and draft discard confirmation.

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
```

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
