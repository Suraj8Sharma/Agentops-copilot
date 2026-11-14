// AgentOps Copilot — Settings Screen widget tests.
// Owner: Sanskriti (D25 folder ready; D26+ full suite).
// FR4: smoke test proves harness.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/settings/settings_screen.dart';

Widget _screen() => MaterialApp(
      theme: AppTheme.light,
      home: const SettingsScreen(),
    );

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  // FR4 — smoke test: proves the harness works end-to-end.
  testWidgets('SettingsScreen renders without throwing', (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    expect(find.byType(SettingsScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('SettingsScreen displays the screen title', (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    // The ScreenStub renders the title in the AppBar.
    expect(find.text('Settings / Profile'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
