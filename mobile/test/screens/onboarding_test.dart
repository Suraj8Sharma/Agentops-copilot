// AgentOps Copilot — Onboarding / Splash Screen widget tests.
// Owner: Ishani (Frontend Design Lead & Trust Surfaces)
// Spec: Day 26 (A7, Gate 3, §15.2) — render & interaction coverage for Onboarding.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/onboarding/onboarding_screen.dart';

void main() {
  tearDown(() {
    OnboardingService.completeOnboardingOverride = null;
    OnboardingScreen.requestPermissionsOverride = null;
  });

  Widget onboardingApp({bool onboardingCompleted = false}) {
    return MaterialApp(
      theme: AppTheme.light,
      initialRoute: AppRoutes.onboarding,
      routes: {
        AppRoutes.onboarding: (_) => OnboardingScreen(
              onboardingCompleted: onboardingCompleted,
            ),
        AppRoutes.signIn: (_) => const Scaffold(
              body: Center(child: Text('Sign In Screen')),
            ),
      },
    );
  }

  // FR-ON-1: Renders intro content without errors using design tokens.
  testWidgets('test_onboarding_renders_intro', (tester) async {
    await tester.pumpWidget(onboardingApp());

    // Initially shows splash view with design token styling
    expect(find.text('AgentOps Copilot'), findsOneWidget);
    expect(find.byKey(const Key('app-logo-splash')), findsOneWidget);

    // Advance past splash transition
    await tester.pump(const Duration(milliseconds: 800));
    await tester.pumpAndSettle();

    // Intro content rendered using theme tokens
    expect(find.text('Your work, with a copilot'), findsOneWidget);
    expect(
      find.text('AgentOps plans and runs tasks across the tools you already use.'),
      findsOneWidget,
    );
    expect(find.text('Next'), findsOneWidget);
    expect(find.text('Skip'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  // FR-ON-2: Permission priming content is shown (mic & notifications) before system prompt.
  testWidgets('test_onboarding_shows_permission_priming', (tester) async {
    await tester.pumpWidget(onboardingApp());
    await tester.pump(const Duration(milliseconds: 800));
    await tester.pumpAndSettle();

    // Navigate to slide 2
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.text('You stay in control'), findsOneWidget);

    // Navigate to slide 3
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.text('Connect your tools next'), findsOneWidget);
    expect(find.text('Get Started'), findsOneWidget);

    // Tapping Get Started opens permission priming
    await tester.tap(find.text('Get Started'));
    await tester.pumpAndSettle();

    // Priming content includes microphone and notifications
    expect(find.text('Permissions'), findsOneWidget);
    expect(find.textContaining('microphone', findRichText: true), findsOneWidget);
    expect(find.textContaining('notifications', findRichText: true), findsOneWidget);
    expect(find.byKey(const Key('allow-permissions')), findsOneWidget);
    expect(find.byKey(const Key('deny-permissions')), findsOneWidget);
  });

  // FR-ON-3: Primary action advances through flow and navigates to next route via router.dart.
  testWidgets('test_onboarding_continue_navigates_forward', (tester) async {
    await tester.pumpWidget(onboardingApp());
    await tester.pump(const Duration(milliseconds: 800));
    await tester.pumpAndSettle();

    // Advance to end
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Get Started'));
    await tester.pumpAndSettle();

    // Accept priming
    await tester.tap(find.byKey(const Key('allow-permissions')));
    await tester.pumpAndSettle();

    // Reached sign in screen
    expect(find.text('Sign In Screen'), findsOneWidget);
  });

  // FR-ON-4: Completing onboarding requests profiles.onboarding_completed = true.
  testWidgets('test_onboarding_completion_marks_profile_complete', (tester) async {
    var markedCompleted = false;
    OnboardingService.completeOnboardingOverride = () async {
      markedCompleted = true;
    };

    await tester.pumpWidget(onboardingApp());
    await tester.pump(const Duration(milliseconds: 800));
    await tester.pumpAndSettle();

    // Tapping skip also completes onboarding
    await tester.tap(find.text('Skip'));
    await tester.pumpAndSettle();

    expect(markedCompleted, isTrue);
    expect(find.text('Sign In Screen'), findsOneWidget);
  });

  // Edge Case §5.1: User denies permission after priming -> flow continues, does not block.
  testWidgets('test_onboarding_continues_when_permission_denied', (tester) async {
    var markedCompleted = false;
    OnboardingService.completeOnboardingOverride = () async {
      markedCompleted = true;
    };

    await tester.pumpWidget(onboardingApp());
    await tester.pump(const Duration(milliseconds: 800));
    await tester.pumpAndSettle();

    // Advance to permission priming
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Get Started'));
    await tester.pumpAndSettle();

    // User chooses 'Not now' (denies permission)
    await tester.tap(find.byKey(const Key('deny-permissions')));
    await tester.pumpAndSettle();

    // Flow still completed successfully and navigated to next route
    expect(markedCompleted, isTrue);
    expect(find.text('Sign In Screen'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  // Edge Case §5.1: Onboarding re-entered after completion -> screen is skipped.
  testWidgets('test_onboarding_skipped_when_already_completed', (tester) async {
    await tester.pumpWidget(onboardingApp(onboardingCompleted: true));
    await tester.pumpAndSettle();

    // Immediately redirects to Sign In without showing onboarding slides
    expect(find.text('Sign In Screen'), findsOneWidget);
    expect(find.text('Your work, with a copilot'), findsNothing);
  });

  // Edge Case §5.1: Small screen or large text scale -> no overflow, action reachable.
  testWidgets('test_onboarding_no_overflow_on_small_screen_and_large_text', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(textScaler: TextScaler.linear(1.5)),
        child: onboardingApp(),
      ),
    );
    await tester.pump(const Duration(milliseconds: 800));
    await tester.pumpAndSettle();

    // Verify slide 1 is readable and Next is reachable
    expect(find.text('Your work, with a copilot'), findsOneWidget);
    expect(tester.getRect(find.text('Next')).bottom, lessThanOrEqualTo(568.0));
    expect(tester.takeException(), isNull);

    // Advance to slide 2
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.text('You stay in control'), findsOneWidget);
    expect(tester.takeException(), isNull);

    // Advance to slide 3
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.text('Connect your tools next'), findsOneWidget);
    expect(find.text('Get Started'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
