import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/trust_dashboard/trust_dashboard_screen.dart';

void main() {
  testWidgets('renders latency, cost, and accuracy mock charts', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: TrustDashboardScreen(),
    ));

    expect(find.byKey(const Key('trust-dashboard-screen')), findsOneWidget);
    expect(find.text('Latency'), findsOneWidget);
    expect(find.text('Cost'), findsOneWidget);
    expect(find.text('Accuracy'), findsOneWidget);
    expect(find.byKey(const Key('Latency-metric-chart')), findsOneWidget);
    expect(find.byKey(const Key('Cost-metric-chart')), findsOneWidget);
    expect(find.byKey(const Key('Accuracy-metric-chart')), findsOneWidget);
    expect(find.text('Fallback event'), findsOneWidget);
    expect(find.textContaining('Mock data'), findsOneWidget);
  });

  testWidgets('empty metric series renders safely', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: TrustDashboardScreen(
        metrics: TrustDashboardMetrics(latency: [], cost: [], accuracy: []),
      ),
    ));

    expect(find.text('0.0s'), findsOneWidget);
    expect(find.text('\$0.00'), findsOneWidget);
    expect(find.text('0%'), findsOneWidget);
    expect(tester.takeException(), isNull);
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
