// AgentOps Copilot — Daily / Weekly Digest Screen widget tests.
// Owner: Shivangi (D25/26 full suite; D25 smoke by Ishani for harness setup).
// FR4: smoke test proves harness.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/digest/digest_screen.dart';

Widget _screen() => MaterialApp(
      theme: AppTheme.light,
      home: const DigestScreen(),
    );

void main() {
  // FR4 — smoke test: proves the harness works end-to-end.
  testWidgets('DigestScreen renders without throwing', (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    expect(find.byType(DigestScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('DigestScreen displays the screen title', (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    // The ScreenStub renders the title in the AppBar.
    expect(find.text('Daily / Weekly Digest'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
