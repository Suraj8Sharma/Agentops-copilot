import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/task_composer/task_composer_screen.dart';

void main() {
  Widget composer() => MaterialApp(
        theme: AppTheme.light,
        home: const TaskComposerScreen(),
      );

  testWidgets('renders text mode and reserves voice mode affordance',
      (tester) async {
    await tester.pumpWidget(composer());

    expect(find.byKey(const Key('task-input')), findsOneWidget);
    expect(find.text('Submit task'), findsOneWidget);
    expect(find.text('Voice mode coming soon'), findsOneWidget);
    expect(
        tester
            .widget<OutlinedButton>(
              find.byKey(const Key('voice-mode-placeholder')),
            )
            .onPressed,
        isNull);
  });

  testWidgets('blocks an empty submission', (tester) async {
    await tester.pumpWidget(composer());

    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pump();

    expect(find.text('Tell your copilot what to do first.'), findsOneWidget);
    expect(find.text('Submitting...'), findsNothing);
  });

  testWidgets('shows submitting then submitted mock state', (tester) async {
    await tester.pumpWidget(composer());
    await tester.enterText(
      find.byKey(const Key('task-input')),
      'Prepare a summary of my unread emails',
    );
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pump();

    expect(find.text('Submitting...'), findsOneWidget);
    expect(find.text('Submitting your task'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Task submitted'), findsOneWidget);
    expect(
      find.byKey(const Key('submitted-task-text')),
      findsOneWidget,
    );
  });
}
