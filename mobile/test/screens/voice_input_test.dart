// AgentOps Copilot — Voice Input Screen widget tests.
// Owner: Jigyasu (D26 full suite; D25 smoke only — harness readiness).
// FR4: smoke test proves harness. FR8: async state + listening-state patterns verified.
//
// NOTE for Jigyasu (D26):
//   VoiceInputScreen is currently a ScreenStub placeholder.
//   When you build it, remove the ScreenStub import and update these tests.
//   The async/tap patterns you'll need are verified in FR8 notes below.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/voice_input/voice_input_screen.dart';

Widget _screen() => MaterialApp(
      theme: AppTheme.light,
      home: const VoiceInputScreen(),
    );

void main() {
  // FR4 — smoke test: proves the harness works end-to-end.
  testWidgets('VoiceInputScreen renders without throwing', (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(VoiceInputScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  // FR8 — pattern verification: async state transitions (pumpAndSettle).
  // This shows Jigyasu the pattern for simulating listening→transcript state changes.
  // Replace these with real assertions once VoiceInputScreen is built.
  testWidgets('FR8 pattern: pumpAndSettle handles async state correctly',
      (tester) async {
    // This is a pattern test, not a real feature test.
    // It verifies the test framework can handle async widget state changes,
    // which voice_input tests will need (listening → transcribing → done states).
    var stateValue = 'idle';
    late StateSetter setter;

    await tester.pumpWidget(
      MaterialApp(
        home: StatefulBuilder(
          builder: (context, setState) {
            setter = setState;
            return Scaffold(
              body: Center(
                key: const Key('voice-state-display'),
                child: Text(stateValue),
              ),
            );
          },
        ),
      ),
    );

    expect(find.text('idle'), findsOneWidget);

    // Simulate transition: idle → listening
    setter(() => stateValue = 'listening');
    await tester.pump();
    expect(find.text('listening'), findsOneWidget);

    // Simulate transition: listening → final-transcript
    setter(() => stateValue = 'final-transcript');
    await tester.pump();
    expect(find.text('final-transcript'), findsOneWidget);

    // pumpAndSettle ensures all animations complete
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
