// AgentOps Copilot — Manual To-Do Fallback Screen widget tests.
// Owner: Shivangi (D25/26 full suite; D25 smoke by Ishani for harness setup).
// FR4: smoke test proves harness.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/manual_todo/manual_todo_screen.dart';

Widget _screen() => MaterialApp(
      theme: AppTheme.light,
      home: const ManualTodoScreen(),
    );

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  // FR4 — smoke test: proves the harness works end-to-end.
  testWidgets('ManualTodoScreen renders without throwing', (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    expect(find.byType(ManualTodoScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('ManualTodoScreen displays the screen title', (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    // The ScreenStub renders the title in the AppBar.
    expect(find.text('Manual To-Do Fallback'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
