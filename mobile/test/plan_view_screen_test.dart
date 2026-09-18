import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/home/home_screen.dart';
import 'package:agentops_copilot/features/home/task_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_view_screen.dart';

void main() {
  Widget planView({MockPlan plan = mockPlan}) => MaterialApp(
        theme: AppTheme.light,
        home: PlanViewScreen(plan: plan),
      );

  testWidgets('renders ordered steps with tool, integration, risk, and status',
      (tester) async {
    await tester.pumpWidget(planView());

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

  testWidgets('home task tiles route to the plan view', (tester) async {
    final mockAppTask = AppTask(
      id: 'task-planning',
      inputType: 'text',
      rawInput: 'Prepare a weekly team update from my calendar',
      status: TaskStatus.planning,
      createdAt: DateTime(2026, 8, 27, 8, 45),
    );
    TaskService.fetchTasksOverride = () async => [mockAppTask];

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const HomeScreen(),
      onGenerateRoute: (settings) {
        if (settings.name == AppRoutes.planView) {
          return MaterialPageRoute<void>(
            builder: (_) => const PlanViewScreen(),
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
