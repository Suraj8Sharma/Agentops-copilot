import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/home/task_service.dart';
import 'package:agentops_copilot/features/trust_dashboard/trust_dashboard_screen.dart';
import 'package:agentops_copilot/features/trust_dashboard/trust_dashboard_service.dart';

void main() {
  setUp(() {
    TaskService.accessTokenProvider = () async => 'fake-token';
    TaskService.httpClientOverride = MockClient((request) async {
      if (request.method == 'GET' &&
          request.url.path.endsWith('/dashboard/metrics')) {
        return http.Response(
          jsonEncode({
            'generated_at': '2026-09-26T09:00:00Z',
            'latency': [
              {'label': 'Mon', 'value': 1.4},
              {'label': 'Tue', 'value': 2.0},
              {'label': 'Wed', 'value': 2.6},
            ],
            'cost': [
              {'label': 'Mon', 'value': 0.12},
              {'label': 'Tue', 'value': 0.08},
              {'label': 'Wed', 'value': 0.15},
            ],
            'accuracy': [
              {'label': 'Mon', 'value': 92.0},
              {'label': 'Tue', 'value': 95.0},
              {'label': 'Wed', 'value': 97.0},
            ],
            'summary': {
              'p95_latency': 2.6,
              'total_cost': 0.35,
              'avg_accuracy': 94.7,
              'fallback_events_count': 1,
            },
            'fallback_events': 1,
          }),
          200,
        );
      }
      return http.Response('Not Found', 404);
    });
  });

  tearDown(() {
    TaskService.accessTokenProvider = null;
    TaskService.httpClientOverride = null;
    TrustDashboardService.fetchMetricsOverride = null;
  });

  testWidgets('renders all dashboard panels with real data', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const TrustDashboardScreen(),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('trust-dashboard-screen')), findsOneWidget);
    expect(find.text('Latency'), findsOneWidget);
    expect(find.text('Cost'), findsOneWidget);
    expect(find.text('Accuracy'), findsOneWidget);
    expect(find.byKey(const Key('Latency-metric-chart')), findsOneWidget);
    expect(find.byKey(const Key('Cost-metric-chart')), findsOneWidget);
    expect(find.byKey(const Key('Accuracy-metric-chart')), findsOneWidget);
    expect(find.text('Fallback event'), findsOneWidget);
    expect(find.textContaining('Updated'), findsOneWidget);
  });

  testWidgets('accuracy panel shows the correct live values', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const TrustDashboardScreen(),
    ));
    await tester.pumpAndSettle();

    expect(find.text('95%'), findsOneWidget);
    expect(find.text('\$0.35'), findsOneWidget);
    expect(find.text('2.6s'), findsOneWidget);
  });

  testWidgets('empty metric series shows no-data state instead of zeroes', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const TrustDashboardScreen(
        metrics: TrustDashboardMetrics(
          latency: [],
          cost: [],
          accuracy: [],
        ),
      ),
    ));

    expect(find.text('No data yet'), findsNWidgets(3));
    expect(find.text('0%'), findsNothing);
    expect(find.text('0.0s'), findsNothing);
    expect(find.text('\$0.00'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('loading and error states render without crashing', (tester) async {
    TaskService.httpClientOverride = MockClient((request) async {
      await Future<void>.delayed(const Duration(milliseconds: 150));
      return http.Response('Server error', 500);
    });

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const TrustDashboardScreen(),
    ));

    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pumpAndSettle();
    expect(find.textContaining('Could not load dashboard metrics'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('screen is reachable through the navigation shell', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      initialRoute: AppRoutes.trustDashboard,
      onGenerateRoute: AppRouter.generateRoute,
    ));

    expect(find.byType(TrustDashboardScreen), findsOneWidget);
  });
}
