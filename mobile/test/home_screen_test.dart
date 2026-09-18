import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/home/home_screen.dart';
import 'package:agentops_copilot/features/home/task_service.dart';

final List<AppTask> mockTasks = <AppTask>[
  AppTask(
    id: 'task-submitted',
    inputType: 'text',
    rawInput: 'Find the latest project brief and summarize it',
    status: TaskStatus.submitted,
    createdAt: DateTime(2026, 8, 27, 9, 0),
  ),
  AppTask(
    id: 'task-planning',
    inputType: 'text',
    rawInput: 'Prepare a weekly team update from my calendar',
    status: TaskStatus.planning,
    createdAt: DateTime(2026, 8, 27, 8, 45),
  ),
  AppTask(
    id: 'task-awaiting-approval',
    inputType: 'text',
    rawInput: 'Send the revised launch plan to the team',
    status: TaskStatus.awaitingApproval,
    createdAt: DateTime(2026, 8, 27, 8, 30),
  ),
  AppTask(
    id: 'task-executing',
    inputType: 'voice',
    rawInput: '',
    transcriptionText: 'Create an issue for the onboarding bug',
    status: TaskStatus.executing,
    createdAt: DateTime(2026, 8, 27, 8, 15),
  ),
  AppTask(
    id: 'task-completed',
    inputType: 'text',
    rawInput: 'Add the design review to my calendar',
    status: TaskStatus.completed,
    createdAt: DateTime(2026, 8, 26, 16, 0),
    completedAt: DateTime(2026, 8, 26, 16, 2),
  ),
  AppTask(
    id: 'task-failed',
    inputType: 'text',
    rawInput: 'Find an available room for tomorrow',
    status: TaskStatus.failed,
    createdAt: DateTime(2026, 8, 26, 15, 30),
  ),
  AppTask(
    id: 'task-cancelled',
    inputType: 'text',
    rawInput: 'Draft a reply to the vendor email',
    status: TaskStatus.cancelled,
    createdAt: DateTime(2026, 8, 26, 14, 0),
  ),
];

void main() {
  setUp(() {
    TaskService.fetchTasksOverride = () async => mockTasks;
  });
  
  tearDown(() {
    TaskService.fetchTasksOverride = null;
  });

  Widget home() => MaterialApp(
        theme: AppTheme.light,
        home: const HomeScreen(),
      );

  testWidgets('renders every task status in the mock list', (tester) async {
    await tester.pumpWidget(home());
    await tester.pumpAndSettle(); // Wait for fetchTasks to complete
    
    final taskList = find.byKey(const Key('home-task-list'));
    expect(taskList, findsOneWidget);

    Future<void> reveal(Finder finder, {bool reverse = false}) async {
      for (var attempt = 0;
          attempt < 12 && finder.evaluate().isEmpty;
          attempt++) {
        await tester.drag(
          taskList,
          Offset(0, reverse ? 400 : -300),
        );
        await tester.pumpAndSettle();
      }
      expect(finder, findsOneWidget);
    }

    for (final status in TaskStatus.values) {
      await reveal(find.text(status.label));
    }
    await reveal(
      find.text('Find the latest project brief and summarize it'),
      reverse: true,
    );
  });

  testWidgets('create a task uses the task composer route', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const HomeScreen(),
      onGenerateRoute: (settings) => MaterialPageRoute<void>(
        settings: settings,
        builder: (_) => const Placeholder(key: Key('task-composer-page')),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Create a task'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('task-composer-page')), findsOneWidget);
  });

  testWidgets('renders an empty state without overflow', (tester) async {
    TaskService.fetchTasksOverride = () async => <AppTask>[];
    await tester.pumpWidget(home());
    await tester.pumpAndSettle();

    expect(find.text('No tasks yet'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  
  testWidgets('renders loading state correctly', (tester) async {
    final completer = Completer<List<AppTask>>();
    TaskService.fetchTasksOverride = () => completer.future;
    
    await tester.pumpWidget(home());
    
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Waking up backend...'), findsOneWidget);
    
    completer.complete(mockTasks);
    await tester.pumpAndSettle();
    
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });
  
  testWidgets('renders error state correctly and can retry', (tester) async {
    var callCount = 0;
    TaskService.fetchTasksOverride = () async {
      callCount++;
      if (callCount == 1) {
        throw Exception('Server error 500');
      }
      return mockTasks;
    };
    
    await tester.pumpWidget(home());
    await tester.pumpAndSettle();
    
    expect(find.text('Failed to load tasks'), findsOneWidget);
    expect(find.textContaining('Server error 500'), findsOneWidget);
    
    // Tap Retry
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    
    // Should now show tasks
    expect(find.byKey(const Key('home-task-list')), findsOneWidget);
  });
}
