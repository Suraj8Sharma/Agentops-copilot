import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/task_composer/task_composer_screen.dart';
import 'package:agentops_copilot/features/home/home_screen.dart';
import 'package:agentops_copilot/features/home/task_service.dart';

AppTask submittedTask(String input) => AppTask(
      id: 'task-1',
      inputType: 'text',
      rawInput: input,
      status: TaskStatus.submitted,
      createdAt: DateTime(2026, 9, 8),
    );

void main() {
  tearDown(() {
    TaskService.createTaskOverride = null;
    TaskService.accessTokenProvider = null;
    TaskService.refreshAccessTokenProvider = null;
  });

  Widget composer() => MaterialApp(
        theme: AppTheme.light,
        home: const TaskComposerScreen(),
      );

  testWidgets('renders text mode and reserves voice mode affordance',
      (tester) async {
    await tester.pumpWidget(composer());

    expect(find.byKey(const Key('task-input')), findsOneWidget);
    expect(find.text('Submit task'), findsOneWidget);
    expect(find.byKey(const Key('voice-mode-button')), findsOneWidget);
    expect(find.text('Voice mode (Speak task)'), findsOneWidget);
  });

  testWidgets('blocks an empty submission', (tester) async {
    await tester.pumpWidget(composer());

    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pump();

    expect(find.text('Tell your copilot what to do first.'), findsOneWidget);
    expect(find.text('Submitting...'), findsNothing);
  });

  testWidgets('shows submitting then submitted state', (tester) async {
    final completer = Completer<AppTask>();
    TaskService.createTaskOverride = (_) => completer.future;
    await tester.pumpWidget(composer());
    await tester.enterText(
      find.byKey(const Key('task-input')),
      'Prepare a summary of my unread emails',
    );
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pump();

    expect(find.text('Submitting...'), findsOneWidget);
    expect(find.text('Submitting your task'), findsOneWidget);

    completer.complete(
      submittedTask('Prepare a summary of my unread emails'),
    );
    await tester.pumpAndSettle();
    expect(find.text('Task submitted'), findsOneWidget);
    expect(
      find.byKey(const Key('submitted-task-text')),
      findsOneWidget,
    );
  });

  testWidgets('preserves exact input and surfaces a retryable error', (tester) async {
    TaskService.createTaskOverride = (_) async {
      throw const TaskServiceException('Server unavailable (HTTP 503)');
    };
    await tester.pumpWidget(composer());
    const input = '  Prepare the launch summary  ';
    await tester.enterText(find.byKey(const Key('task-input')), input);
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pumpAndSettle();

    expect(find.text('Task could not be submitted'), findsOneWidget);
    expect(find.text('Server unavailable (HTTP 503)'), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byKey(const Key('task-input'))).controller!.text,
      input,
    );
  });

  testWidgets('locks submit while the request is in flight', (tester) async {
    final completer = Completer<AppTask>();
    var calls = 0;
    TaskService.createTaskOverride = (_) {
      calls++;
      return completer.future;
    };
    await tester.pumpWidget(composer());
    await tester.enterText(find.byKey(const Key('task-input')), 'Do one thing');
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pump();

    expect(calls, 1);
    expect(find.text('Submitting...'), findsOneWidget);
    completer.complete(submittedTask('Do one thing'));
    await tester.pumpAndSettle();
  });
}
