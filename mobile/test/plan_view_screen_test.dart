import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/home/home_screen.dart';
import 'package:agentops_copilot/features/home/task_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_view_screen.dart';
import 'package:agentops_copilot/features/plan_view/plan_service.dart';

void main() {
  Widget planView({MockPlan plan = mockPlan}) {
    PlanService.fetchPlanOverride = (_) async => plan;
    return MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    );
  }

  testWidgets('renders ordered steps with tool, integration, risk, and status',
      (tester) async {
    await tester.pumpWidget(planView());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('plan-summary')), findsOneWidget);
    expect(find.byKey(const Key('plan-step-plan-step-calendar')), findsOneWidget);
    expect(find.byKey(const Key('plan-step-plan-step-gmail')), findsOneWidget);
    expect(find.byKey(const Key('plan-step-plan-step-draft')), findsOneWidget);
    expect(find.text('calendar.list_events'), findsOneWidget);
    expect(find.text('Integration: calendar'), findsOneWidget);
    expect(find.text('LOW RISK'), findsOneWidget);
    expect(find.text('AWAITING APPROVAL'), findsOneWidget);
    expect(find.text('This step gates the steps that follow.'), findsOneWidget);
  });

  testWidgets('shows an empty state for a plan without steps', (tester) async {
    await tester.pumpWidget(planView(
      plan: const MockPlan(
        id: 'empty-plan',
        taskId: 'empty-task',
        plannerVersion: 'planner-v1-mock',
        status: 'active',
        steps: <PlanStep>[],
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('empty-plan-state')), findsOneWidget);
    expect(find.text('No steps planned yet'), findsOneWidget);
  });

  testWidgets('renders every supported risk tier and step status',
      (tester) async {
    final steps = <PlanStep>[
      for (var index = 0; index < PlanStepStatus.values.length; index++)
        PlanStep(
          id: 'status-step-$index',
          stepIndex: index + 1,
          toolName: 'tool.action_$index',
          mcpServer: 'calendar',
          riskTier: RiskTier.values[index % RiskTier.values.length],
          requiresApproval: index.isEven,
          status: PlanStepStatus.values[index],
        ),
    ];
    await tester.pumpWidget(planView(
      plan: MockPlan(
        id: 'status-plan',
        taskId: 'status-task',
        plannerVersion: 'planner-v1-mock',
        status: 'active',
        steps: steps,
      ),
    ));
    await tester.pumpAndSettle();

    // Verify each status and risk tier are rendered
    for (var step in steps) {
      expect(find.text(step.riskTier.label), findsWidgets);
      expect(find.text(step.status.label), findsWidgets);
    }
  });

  testWidgets('long plans scroll without overflow and failed steps are clear',
      (tester) async {
    final steps = List<PlanStep>.generate(
      12,
      (index) => PlanStep(
        id: 'long-step-$index',
        stepIndex: index + 1,
        toolName: 'github.create_issue_with_a_very_long_tool_name_$index',
        mcpServer: 'github',
        riskTier: RiskTier.high,
        requiresApproval: true,
        status: index == 5 ? PlanStepStatus.failed : PlanStepStatus.pending,
      ),
    );
    await tester.pumpWidget(planView(
      plan: MockPlan(
        id: 'long-plan',
        taskId: 'long-task',
        plannerVersion: 'planner-v1-mock',
        status: 'active',
        steps: steps,
      ),
    ));
    await tester.pumpAndSettle();

    // Scroll down to find the failed step
    for (int i = 0; i < 5; i++) {
      await tester.drag(find.byType(SingleChildScrollView), const Offset(0, -300));
      await tester.pumpAndSettle();
    }
    
    expect(find.text('FAILED'), findsOneWidget);
    expect(find.text('Later steps may not run until this is resolved.'),
        findsOneWidget);
    
    // Continue scrolling to ensure no layout breakage
    await tester.drag(find.byType(SingleChildScrollView), const Offset(0, -1200));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });


  testWidgets('shows loading state initially', (tester) async {
    final completer = Completer<MockPlan>();
    PlanService.fetchPlanOverride = (_) => completer.future;

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    ));

    expect(find.text('Waking up backend...'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('shows error state when fetching fails', (tester) async {
    PlanService.fetchPlanOverride = (_) async => throw Exception('Network error');

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Failed to load plan'), findsOneWidget);
    expect(find.text('Exception: Network error'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('shows waiting state when plan is not found', (tester) async {
    PlanService.fetchPlanOverride = (_) async => throw const PlanNotFoundException('Plan not ready yet');

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('empty-plan-state')), findsOneWidget);
    expect(find.text('No steps planned yet'), findsOneWidget);
  });

  testWidgets('home task tiles route to the plan view', (tester) async {
    final mockAppTask = AppTask(
      id: 'task-planning',
      inputType: 'text',
      rawInput: 'Prepare a weekly team update from my calendar',
      status: TaskStatus.planning,
      createdAt: DateTime(2026, 8, 27, 8, 45),
    );
    TaskService.fetchTasksOverride = () async => [mockAppTask];
    PlanService.fetchPlanOverride = (_) async => mockPlan;

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const HomeScreen(),
      onGenerateRoute: (settings) {
        if (settings.name == AppRoutes.planView) {
          final taskId = settings.arguments as String?;
          return MaterialPageRoute<void>(
            builder: (_) => PlanViewScreen(taskId: taskId ?? ''),
          );
        }
        return null;
      },
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('task-planning')));
    await tester.pumpAndSettle();
    expect(find.byType(PlanViewScreen), findsOneWidget);
    
    TaskService.fetchTasksOverride = null;
  });
}
