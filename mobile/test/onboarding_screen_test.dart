import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/onboarding/onboarding_screen.dart';

void main() {
  Future<void> pumpOnboarding(WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const OnboardingScreen(),
    ));
    await tester.pump(const Duration(milliseconds: 800));
  }

  testWidgets('shows splash then the first onboarding slide', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const OnboardingScreen(),
    ));
    expect(find.text('AgentOps Copilot'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 800));
    expect(find.text('Your work, with a copilot'), findsOneWidget);
    expect(find.text('Next'), findsOneWidget);
    expect(find.text('Skip'), findsOneWidget);
  });

  testWidgets('next advances through slides', (tester) async {
    await pumpOnboarding(tester);
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.text('You stay in control'), findsOneWidget);
    await tester.tap(find.text('Next'));
    await tester.pumpAndSettle();
    expect(find.text('Connect your tools next'), findsOneWidget);
    expect(find.text('Get Started'), findsOneWidget);
  });

  testWidgets('skip uses the routed handoff', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const OnboardingScreen(),
      onGenerateRoute: (settings) => MaterialPageRoute<void>(
        settings: settings,
        builder: (_) => const Placeholder(key: Key('home-page')),
      ),
    ));
    await tester.pump(const Duration(milliseconds: 800));
    await tester.tap(find.text('Skip'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('home-page')), findsOneWidget);
  });

  testWidgets('does not overflow on a compact device', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await pumpOnboarding(tester);
    expect(tester.takeException(), isNull);
  });
}
