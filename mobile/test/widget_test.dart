// AgentOps Copilot — smoke test.
//
// Replaces Flutter's default counter-app test (which referenced the
// placeholder home: Scaffold from before Day 2's routing skeleton).
// This just confirms the app boots, applies AppTheme, and lands on
// the initial route without throwing. Full per-screen widget/golden
// test suites are scheduled separately (Manual §15.2, starting D25).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/main.dart';
import 'package:agentops_copilot/core/theme.dart';

void main() {
  testWidgets('App boots and renders the initial route', (tester) async {
    await tester.pumpWidget(const AgentOpsApp());
    await tester.pumpAndSettle();

    // Lands on the Onboarding stub (AppRoutes.onboarding is the
    // initialRoute set in main.dart).
    expect(find.text('Onboarding / Splash'), findsOneWidget);
  });

  testWidgets('App uses AppTheme.light', (tester) async {
    await tester.pumpWidget(const AgentOpsApp());
    await tester.pumpAndSettle();

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.theme, AppTheme.light);
  });
}