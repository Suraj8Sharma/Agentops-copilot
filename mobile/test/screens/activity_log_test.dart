import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/activity_log/activity_log_models.dart';
import 'package:agentops_copilot/features/activity_log/activity_log_screen.dart';
import 'package:agentops_copilot/features/activity_log/activity_log_service.dart';

final ActivityLogEntry newest = ActivityLogEntry(
  id: '1042',
  eventType: LogEventType.approvalDecided,
  title: 'gmail.send_message approved',
  description: 'Approval decision: approved.',
  timestamp: DateTime(2026, 9, 24, 10),
  agentName: 'risk_gate',
  decision: 'approved',
);

final ActivityLogEntry middle = ActivityLogEntry(
  id: '1041',
  eventType: LogEventType.toolCalled,
  title: 'calendar.create_event called',
  description: 'Created the calendar event.',
  timestamp: DateTime(2026, 9, 23, 10),
  agentName: 'mcp_calendar',
  integration: 'calendar',
);

final ActivityLogEntry oldest = ActivityLogEntry(
  id: '1040',
  eventType: LogEventType.error,
  title: 'Activity error',
  description: 'The provider timed out.',
  timestamp: DateTime(2026, 9, 22, 10),
  agentName: 'mcp_gmail',
);

Widget buildScreen({DateTime? from, DateTime? to}) => MaterialApp(
      theme: AppTheme.light,
      home: ActivityLogScreen(initialFrom: from, initialTo: to),
    );

void main() {
  tearDown(() {
    ActivityLogService.fetchOverride = null;
    ActivityLogService.fetchPageOverride = null;
  });

  testWidgets('ActivityLogScreen renders without throwing', (tester) async {
    ActivityLogService.fetchPageOverride = (
            {limit = 50,
            cursor,
            eventTypes = const {},
            from,
            to,
            query}) async =>
        ActivityLogPage(items: [newest, middle, oldest]);
    await tester.pumpWidget(buildScreen());
    await tester.pumpAndSettle();
    expect(find.byType(ActivityLogScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('test_activity_log_renders_entries', (tester) async {
    ActivityLogService.fetchPageOverride = (
            {limit = 50,
            cursor,
            eventTypes = const {},
            from,
            to,
            query}) async =>
        ActivityLogPage(items: [newest, middle, oldest]);
    await tester.pumpWidget(buildScreen());
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('log-entry-1042')), findsOneWidget);
    expect(find.byKey(const Key('log-entry-1041')), findsOneWidget);
    expect(find.byKey(const Key('log-entry-1040')), findsOneWidget);
    expect(tester.getCenter(find.byKey(const Key('log-entry-1042'))).dy,
        lessThan(tester.getCenter(find.byKey(const Key('log-entry-1041'))).dy));
    expect(find.text('Approval decision: approved.'), findsOneWidget);
  });

  testWidgets('test_activity_log_filters_by_date_and_type', (tester) async {
    final calls = <({Set<LogEventType> types, DateTime? from, DateTime? to})>[];
    ActivityLogService.fetchPageOverride =
        ({limit = 50, cursor, eventTypes = const {}, from, to, query}) async {
      calls.add((types: eventTypes, from: from, to: to));
      final filtered =
          <ActivityLogEntry>[newest, middle, oldest].where((entry) {
        final dateMatch = (from == null || !entry.timestamp.isBefore(from)) &&
            (to == null || !entry.timestamp.isAfter(to));
        return dateMatch &&
            (eventTypes.isEmpty || eventTypes.contains(entry.eventType));
      }).toList();
      return ActivityLogPage(items: filtered);
    };

    await tester.pumpWidget(buildScreen(
      from: DateTime(2026, 9, 23),
      to: DateTime(2026, 9, 24, 23, 59, 59),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('log-entry-1042')), findsOneWidget);
    expect(find.byKey(const Key('log-entry-1041')), findsOneWidget);
    expect(find.byKey(const Key('log-entry-1040')), findsNothing);

    await tester.tap(find.byKey(const Key('activity-filter-Tool called')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('log-entry-1041')), findsOneWidget);
    expect(find.byKey(const Key('log-entry-1042')), findsNothing);
    expect(calls.last.types, contains(LogEventType.toolCalled));
    expect(calls.last.from, DateTime(2026, 9, 23));

    await tester.tap(find.byKey(const Key('activity-filter-Tool called')));
    await tester.tap(find.byKey(const Key('activity-clear-filters')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('log-entry-1040')), findsOneWidget);
  });

  testWidgets('test_activity_log_search_filters_entries', (tester) async {
    ActivityLogService.fetchPageOverride = (
            {limit = 50,
            cursor,
            eventTypes = const {},
            from,
            to,
            query}) async =>
        ActivityLogPage(
          items: (query ?? '').toLowerCase().contains('calendar')
              ? [middle]
              : [newest, middle, oldest],
        );
    await tester.pumpWidget(buildScreen());
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const Key('activity-search')), 'calendar');
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('log-entry-1041')), findsOneWidget);
    expect(find.byKey(const Key('log-entry-1042')), findsNothing);

    await tester.tap(find.byKey(const Key('activity-clear-search')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('log-entry-1041')), findsOneWidget);
    expect(find.byKey(const Key('log-entry-1042')), findsOneWidget);
  });

  testWidgets('test_activity_log_renders_each_event_type', (tester) async {
    final entries = <ActivityLogEntry>[
      for (var i = 0; i < LogEventType.values.length; i++)
        ActivityLogEntry(
          id: 'type-$i',
          eventType: LogEventType.values[i],
          title: LogEventType.values[i].label,
          description: 'event',
          timestamp: DateTime(2026, 9, 24, i),
        ),
    ];
    ActivityLogService.fetchPageOverride = (
            {limit = 50,
            cursor,
            eventTypes = const {},
            from,
            to,
            query}) async =>
        ActivityLogPage(items: entries);
    await tester.pumpWidget(buildScreen());
    await tester.pumpAndSettle();
    for (final type in LogEventType.values) {
      expect(find.text(type.label), findsWidgets);
    }
  });

  testWidgets('test_activity_log_pagination_appends_next_page', (tester) async {
    final cursors = <String?>[];
    ActivityLogService.fetchPageOverride =
        ({limit = 50, cursor, eventTypes = const {}, from, to, query}) async {
      cursors.add(cursor);
      return cursor == null
          ? ActivityLogPage(items: [newest], nextCursor: 'next')
          : ActivityLogPage(items: [middle], nextCursor: null);
    };
    await tester.pumpWidget(buildScreen());
    await tester.pumpAndSettle();
    await tester.drag(
        find.byKey(const Key('activity-log-list')), const Offset(0, -1000));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('log-entry-1042')), findsOneWidget);
    expect(find.byKey(const Key('log-entry-1041')), findsOneWidget);
    expect(cursors, contains('next'));
  });

  testWidgets('test_activity_log_shows_loading_state', (tester) async {
    final completer = Completer<ActivityLogPage>();
    ActivityLogService.fetchPageOverride = (
            {limit = 50, cursor, eventTypes = const {}, from, to, query}) =>
        completer.future;
    await tester.pumpWidget(buildScreen());
    expect(find.byKey(const Key('activity-loading')), findsOneWidget);
    completer.complete(ActivityLogPage(items: [newest]));
    await tester.pumpAndSettle();
  });

  testWidgets('test_activity_log_empty_states', (tester) async {
    ActivityLogService.fetchPageOverride = (
            {limit = 50,
            cursor,
            eventTypes = const {},
            from,
            to,
            query}) async =>
        const ActivityLogPage(items: []);
    await tester.pumpWidget(buildScreen());
    await tester.pumpAndSettle();
    expect(find.text('No activity yet'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await tester.pumpAndSettle();
    await tester.pumpWidget(
        buildScreen(from: DateTime(2026, 9, 24), to: DateTime(2026, 9, 24)));
    await tester.pumpAndSettle();
    expect(find.text('No results for these filters'), findsOneWidget);
  });

  testWidgets('test_activity_log_first_load_error_not_shown_as_empty',
      (tester) async {
    ActivityLogService.fetchPageOverride = (
            {limit = 50,
            cursor,
            eventTypes = const {},
            from,
            to,
            query}) async =>
        throw const ActivityLogException('backend unavailable',
            retryable: true);
    await tester.pumpWidget(buildScreen());
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('activity-error')), findsOneWidget);
    expect(find.text('No activity yet'), findsNothing);
  });

  testWidgets('test_activity_log_read_only_has_no_write_action',
      (tester) async {
    ActivityLogService.fetchPageOverride = (
            {limit = 50,
            cursor,
            eventTypes = const {},
            from,
            to,
            query}) async =>
        ActivityLogPage(items: [newest]);
    await tester.pumpWidget(buildScreen());
    await tester.pumpAndSettle();
    expect(find.textContaining('Delete'), findsNothing);
    expect(find.textContaining('Edit'), findsNothing);
    expect(find.byType(FloatingActionButton), findsNothing);
  });
}
