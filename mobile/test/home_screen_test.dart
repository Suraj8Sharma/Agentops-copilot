import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/home/home_screen.dart';

void main() {
  Widget home({List<MockTask>? tasks}) => MaterialApp(
        theme: AppTheme.light,
        home: HomeScreen(tasks: tasks ?? mockTasks),
      );

  testWidgets('renders every task status in the mock list', (tester) async {
    await tester.pumpWidget(home());
    final taskList = find.byKey(const Key('home-task-list'));
    expect(taskList, findsOneWidget);

    for (final status in TaskStatus.values) {
      await tester.scrollUntilVisible(
        find.text(status.label),
        300,
        scrollable: taskList,
      );
      expect(find.text(status.label), findsOneWidget);
    }
    await tester.scrollUntilVisible(
      find.text('Find the latest project brief and summarize it'),
      300,
      scrollable: taskList,
    );
    expect(find.text('Find the latest project brief and summarize it'),
        findsOneWidget);
  });

  testWidgets('create a task uses the task composer route', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: HomeScreen(),
      onGenerateRoute: (settings) => MaterialPageRoute<void>(
        settings: settings,
        builder: (_) => const Placeholder(key: Key('task-composer-page')),
      ),
    ));

    await tester.tap(find.text('Create a task'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('task-composer-page')), findsOneWidget);
  });

  testWidgets('renders an empty state without overflow', (tester) async {
    await tester.pumpWidget(home(tasks: const <MockTask>[]));

    expect(find.text('No tasks yet'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
