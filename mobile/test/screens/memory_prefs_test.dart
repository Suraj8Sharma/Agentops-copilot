// AgentOps Copilot — Memory / Preferences Screen widget tests.
// Owner: Sanskriti (D25 folder ready; D26+ full suite).
// FR4: smoke test proves harness.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/memory_prefs/memory_prefs_screen.dart';

Widget _screen() => MaterialApp(
      theme: AppTheme.light,
      home: const MemoryPrefsScreen(),
    );

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  // FR4 — smoke test: proves the harness works end-to-end.
  testWidgets('MemoryPrefsScreen renders without throwing', (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    expect(find.byType(MemoryPrefsScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('MemoryPrefsScreen displays the screen title', (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    // The ScreenStub renders the title in the AppBar.
    expect(find.text('Memory / Preferences'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
