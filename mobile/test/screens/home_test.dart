// AgentOps Copilot — Home / Dashboard Screen widget tests.
// Owner: Ishani (Frontend Design Lead & Trust Surfaces)
// Spec: Day 26 (A7, Gate 3, §15.2) — render & interaction coverage for Home.

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/home/home_screen.dart';
import 'package:agentops_copilot/features/home/task_service.dart';

final List<AppTask> mockAllStatusTasks = [
  AppTask(
    id: 'task-submitted',
    inputType: 'text',
    rawInput: 'Task in submitted status',
    status: TaskStatus.submitted,
    createdAt: DateTime(2026, 9, 22, 10, 0),
  ),
  AppTask(
    id: 'task-planning',
    inputType: 'text',
    rawInput: 'Task in planning status',
    status: TaskStatus.planning,
    createdAt: DateTime(2026, 9, 22, 9, 45),
  ),
  AppTask(
    id: 'task-awaiting-approval',
    inputType: 'text',
    rawInput: 'Task in awaiting approval status',
    status: TaskStatus.awaitingApproval,
    createdAt: DateTime(2026, 9, 22, 9, 30),
  ),
  AppTask(
    id: 'task-executing',
    inputType: 'voice',
    rawInput: '',
    transcriptionText: 'Task in executing status',
    status: TaskStatus.executing,
    createdAt: DateTime(2026, 9, 22, 9, 15),
  ),
  AppTask(
    id: 'task-completed',
    inputType: 'text',
    rawInput: 'Task in completed status',
    status: TaskStatus.completed,
    createdAt: DateTime(2026, 9, 22, 9, 0),
    completedAt: DateTime(2026, 9, 22, 9, 5),
  ),
  AppTask(
    id: 'task-failed',
    inputType: 'text',
    rawInput: 'Task in failed status',
    status: TaskStatus.failed,
    createdAt: DateTime(2026, 9, 22, 8, 45),
  ),
  AppTask(
    id: 'task-cancelled',
    inputType: 'text',
    rawInput: 'Task in cancelled status',
    status: TaskStatus.cancelled,
    createdAt: DateTime(2026, 9, 22, 8, 30),
  ),
];

void main() {
  tearDown(() {
    TaskService.fetchTasksOverride = null;
  });

  Widget homeApp() {
    return MaterialApp(
      theme: AppTheme.light,
      initialRoute: AppRoutes.home,
      onGenerateRoute: (settings) {
        if (settings.name == AppRoutes.home) {
          return MaterialPageRoute(builder: (_) => const HomeScreen());
        }
        return MaterialPageRoute(
          settings: settings,
          builder: (_) => Scaffold(
            body: Center(
              child: Text('Route: ${settings.name}, Args: ${settings.arguments}'),
            ),
          ),
        );
      },
    );
  }

  // FR-HM-1: Renders task list with every task status.
  testWidgets('test_home_renders_task_list_with_statuses', (tester) async {
    TaskService.fetchTasksOverride = () async => mockAllStatusTasks;

    await tester.pumpWidget(homeApp());
    await tester.pumpAndSettle();

    final taskList = find.byKey(const Key('home-task-list'));
    expect(taskList, findsOneWidget);

    for (final status in TaskStatus.values) {
      final statusLabelFinder = find.text(status.label);
      for (var attempt = 0; attempt < 10 && statusLabelFinder.evaluate().isEmpty; attempt++) {
        await tester.drag(taskList, const Offset(0, -250));
        await tester.pumpAndSettle();
      }
      expect(statusLabelFinder, findsOneWidget);
    }
  });

  // FR-HM-2: Empty state with obvious path to create a task.
  testWidgets('test_home_renders_empty_state_when_no_tasks', (tester) async {
    TaskService.fetchTasksOverride = () async => <AppTask>[];

    await tester.pumpWidget(homeApp());
    await tester.pumpAndSettle();

    expect(find.text('No tasks yet'), findsOneWidget);
    expect(
      find.text('Create a task and your copilot will keep you posted here.'),
      findsOneWidget,
    );
    // Path to create task is clearly visible (both header and empty-state CTA)
    expect(find.text('Create a task'), findsWidgets);
  });

  // FR-HM-3: Shows explicit loading state while request is in flight.
  testWidgets('test_home_shows_loading_state', (tester) async {
    final completer = Completer<List<AppTask>>();
    TaskService.fetchTasksOverride = () => completer.future;

    await tester.pumpWidget(homeApp());
    await tester.pump();

    // Verify explicit loading indicator and message
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Waking up backend...'), findsOneWidget);

    completer.complete(mockAllStatusTasks);
    await tester.pumpAndSettle();

    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.byKey(const Key('home-task-list')), findsOneWidget);
  });

  // FR-HM-4: Quick-entry control navigates to Task Composer.
  testWidgets('test_home_quick_entry_opens_composer', (tester) async {
    TaskService.fetchTasksOverride = () async => <AppTask>[];

    await tester.pumpWidget(homeApp());
    await tester.pumpAndSettle();

    // Tap quick-entry button
    await tester.tap(find.widgetWithText(ElevatedButton, 'Create a task').first);
    await tester.pumpAndSettle();

    expect(find.textContaining('Route: /task-composer'), findsOneWidget);
  });

  // FR-HM-5: Tapping a task navigates to task detail / plan route.
  testWidgets('test_home_task_tap_navigates_to_task', (tester) async {
    TaskService.fetchTasksOverride = () async => [
      AppTask(
        id: 'task-planning-1',
        inputType: 'text',
        rawInput: 'Draft announcement',
        status: TaskStatus.planning,
        createdAt: DateTime(2026, 9, 22),
      ),
      AppTask(
        id: 'task-approval-1',
        inputType: 'text',
        rawInput: 'Send sensitive email',
        status: TaskStatus.awaitingApproval,
        createdAt: DateTime(2026, 9, 22),
      ),
    ];

    await tester.pumpWidget(homeApp());
    await tester.pumpAndSettle();

    // Tapping planning task opens plan view with task id
    await tester.tap(find.text('Draft announcement'));
    await tester.pumpAndSettle();
    expect(find.text('Route: /plan-view, Args: task-planning-1'), findsOneWidget);

    // Return to home
    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    navigator.pop();
    await tester.pumpAndSettle();

    // Tapping awaiting approval task opens approval screen
    await tester.tap(find.text('Send sensitive email'));
    await tester.pumpAndSettle();
    expect(find.text('Route: /approval, Args: null'), findsOneWidget);
  });

  // FR-HM-6: Failed request shows error state with retry action, and retry refetches.
  testWidgets('test_home_error_state_retry_refetches', (tester) async {
    var callCount = 0;
    TaskService.fetchTasksOverride = () async {
      callCount++;
      if (callCount == 1) {
        throw Exception('Render cold start timeout');
      }
      return mockAllStatusTasks;
    };

    await tester.pumpWidget(homeApp());
    await tester.pumpAndSettle();

    expect(find.text('Failed to load tasks'), findsOneWidget);
    expect(find.textContaining('Render cold start timeout'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);

    // Tap retry
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(callCount, 2);
    expect(find.byKey(const Key('home-task-list')), findsOneWidget);
  });

  // Edge Case §5.2: Failed and awaiting_approval are visually distinct, never completed.
  testWidgets('test_home_distinguishes_failed_and_awaiting_approval', (tester) async {
    TaskService.fetchTasksOverride = () async => [
      AppTask(
        id: 'task-fail',
        inputType: 'text',
        rawInput: 'Failed action',
        status: TaskStatus.failed,
        createdAt: DateTime(2026, 9, 22),
      ),
      AppTask(
        id: 'task-appr',
        inputType: 'text',
        rawInput: 'Pending approval action',
        status: TaskStatus.awaitingApproval,
        createdAt: DateTime(2026, 9, 22),
      ),
    ];

    await tester.pumpWidget(homeApp());
    await tester.pumpAndSettle();

    expect(find.text('FAILED'), findsOneWidget);
    expect(find.text('AWAITING APPROVAL'), findsOneWidget);
    expect(find.text('COMPLETED'), findsNothing);
  });

  // Edge Case §5.2: Very long raw_input truncates cleanly with ellipsis and no overflow.
  testWidgets('test_home_truncates_long_task_text', (tester) async {
    final longText = 'A' * 2000;
    TaskService.fetchTasksOverride = () async => [
      AppTask(
        id: 'task-long',
        inputType: 'text',
        rawInput: longText,
        status: TaskStatus.submitted,
        createdAt: DateTime(2026, 9, 22),
      ),
    ];

    await tester.pumpWidget(homeApp());
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    final textWidget = tester.widget<Text>(find.text(longText));
    expect(textWidget.maxLines, 3);
    expect(textWidget.overflow, TextOverflow.ellipsis);
  });

  // Edge Case §5.2: Voice task with empty raw_input displays transcription text.
  testWidgets('test_home_shows_transcription_for_voice_task', (tester) async {
    const transcript = 'Send invoice reminder to client';
    TaskService.fetchTasksOverride = () async => [
      AppTask(
        id: 'task-voice',
        inputType: 'voice',
        rawInput: '',
        transcriptionText: transcript,
        status: TaskStatus.executing,
        createdAt: DateTime(2026, 9, 22),
      ),
    ];

    await tester.pumpWidget(homeApp());
    await tester.pumpAndSettle();

    expect(find.text(transcript), findsOneWidget);
  });

  // Edge Case §5.2: Large list (50+ tasks) scrolls and renders lazily.
  testWidgets('test_home_large_list_scrolls', (tester) async {
    final manyTasks = List.generate(
      60,
      (i) => AppTask(
        id: 'task-$i',
        inputType: 'text',
        rawInput: 'Bulk task #$i in queue',
        status: TaskStatus.submitted,
        createdAt: DateTime(2026, 9, 22, 10, i % 60),
      ),
    );
    TaskService.fetchTasksOverride = () async => manyTasks;

    await tester.pumpWidget(homeApp());
    await tester.pumpAndSettle();

    expect(find.text('Bulk task #0 in queue'), findsOneWidget);

    // Scroll until last item is visible
    await tester.scrollUntilVisible(
      find.text('Bulk task #59 in queue'),
      400,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();

    expect(find.text('Bulk task #0 in queue'), findsNothing);
    expect(find.text('Bulk task #59 in queue'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  // Edge Case §5.2: Unknown status value from backend renders neutral fallback, does not crash.
  testWidgets('test_home_unknown_status_does_not_crash', (tester) async {
    final taskMap = <String, dynamic>{
      'id': 'task-unknown',
      'input_type': 'text',
      'raw_input': 'Task with strange status',
      'status': 'non_existent_future_status',
      'created_at': '2026-09-22T10:00:00Z',
    };
    final parsedTask = AppTask.fromJson(taskMap);
    // Safe fallback to submitted, never completed or approved
    expect(parsedTask.status, TaskStatus.submitted);

    TaskService.fetchTasksOverride = () async => [parsedTask];

    await tester.pumpWidget(homeApp());
    await tester.pumpAndSettle();

    expect(find.text('Task with strange status'), findsOneWidget);
    expect(find.text('SUBMITTED'), findsOneWidget);
    expect(find.text('COMPLETED'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
