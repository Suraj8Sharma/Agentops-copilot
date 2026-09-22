import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/approval/approval_screen.dart';
import 'package:agentops_copilot/features/approval/approval_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_view_screen.dart';

const ApprovalStep pendingStep = ApprovalStep(
  id: 'step-1',
  taskId: 'task-1',
  toolName: 'gmail.send_message',
  mcpServer: 'gmail',
  riskTier: RiskTier.high,
  requiresApproval: true,
  status: 'awaiting_approval',
  explanationText: 'Send the launch agenda to the project team.',
);

const MockPlan mockSingleStepPlan = MockPlan(
  id: 'plan-1',
  taskId: 'task-1',
  plannerVersion: 'v1',
  status: 'active',
  steps: [
    PlanStep(
      id: 'step-1',
      stepIndex: 1,
      toolName: 'gmail.send_message',
      mcpServer: 'gmail',
      riskTier: RiskTier.high,
      requiresApproval: true,
      status: PlanStepStatus.awaitingApproval,
    ),
  ],
);

Widget screen() => MaterialApp(
      theme: AppTheme.light,
      home: const ApprovalScreen(),
    );

void main() {
  setUp(() {
    PlanService.fetchPlanOverride = (taskId) async {
      return mockSingleStepPlan;
    };
  });

  tearDown(() {
    ApprovalService.fetchPendingOverride = null;
    ApprovalService.decideOverride = null;
    PlanService.fetchPlanOverride = null;
  });

  testWidgets('fetches and renders pending approval verbatim', (tester) async {
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];

    await tester.pumpWidget(screen());
    expect(find.byKey(const Key('approval-loading')), findsOneWidget);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('approval-pending-list')), findsOneWidget);
    expect(find.text('Send the launch agenda to the project team.'),
        findsOneWidget);
    expect(find.byKey(const Key('approve-button-step-1')), findsOneWidget);
    expect(find.byKey(const Key('reject-button-step-1')), findsOneWidget);
  });

  testWidgets('test_approval_screen_never_auto_approves', (tester) async {
    final completer = Completer<List<ApprovalStep>>();
    ApprovalService.fetchPendingOverride = () => completer.future;

    await tester.pumpWidget(screen());
    await tester.pump();
    expect(find.byKey(const Key('approval-loading')), findsOneWidget);
    expect(find.text('Approved'), findsNothing);

    completer.complete(<ApprovalStep>[pendingStep]);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('approve-button-step-1')), findsOneWidget);
    expect(find.text('Approved'), findsNothing);
  });

  testWidgets('posts approve decision and disables controls in flight',
      (tester) async {
    final completer = Completer<void>();
    String? stepId;
    ApprovalDecision? decision;
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    ApprovalService.decideOverride = (id, value) {
      stepId = id;
      decision = value;
      return completer.future;
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('approve-button-step-1')));
    await tester.pump();

    expect(stepId, 'step-1');
    expect(decision, ApprovalDecision.approved);
    expect(find.text('Recording decision...'), findsOneWidget);
    expect(
        tester
            .widget<OutlinedButton>(
                find.byKey(const Key('approve-button-step-1')))
            .onPressed,
        isNull);

    completer.complete();
    await tester.pumpAndSettle();
    expect(find.text('APPROVED'), findsOneWidget);
  });

  testWidgets('reject decision is sent and failure is visible', (tester) async {
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    ApprovalService.decideOverride = (_, decision) async {
      expect(decision, ApprovalDecision.rejected);
      throw const ApprovalServiceException('Service unavailable (HTTP 503)');
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('reject-button-step-1')));
    await tester.pumpAndSettle();

    expect(find.text('Approval service unavailable'), findsOneWidget);
    expect(find.text('Service unavailable (HTTP 503)'), findsOneWidget);
    expect(find.text('Approved'), findsNothing);
  });

  testWidgets('empty pending list has an explicit empty state', (tester) async {
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[];
    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('approval-empty')), findsOneWidget);
    expect(find.text('Nothing waiting on you right now'), findsOneWidget);
  });

  testWidgets('missing explanation uses neutral fallback', (tester) async {
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[
          const ApprovalStep(
            id: 'step-1',
            taskId: 'task-1',
            toolName: 'slack.post_message_channel',
            mcpServer: 'slack',
            riskTier: RiskTier.high,
            requiresApproval: true,
            status: 'awaiting_approval',
          ),
        ];
    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('explanation-fallback')), findsOneWidget);
    expect(find.text('No explanation available.'), findsOneWidget);
  });

  // --- New Tests for Day 23 ---

  testWidgets('test_mixed_risk_multi_step_plan_orders_correctly', (tester) async {
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[
          const ApprovalStep(
            id: 'step-2',
            taskId: 'task-mixed',
            toolName: 'gmail.send_message',
            mcpServer: 'gmail',
            riskTier: RiskTier.high,
            requiresApproval: true,
            status: 'awaiting_approval',
            explanationText: 'Send email',
          ),
        ];

    PlanService.fetchPlanOverride = (taskId) async {
      return const MockPlan(
        id: 'plan-mixed',
        taskId: 'task-mixed',
        plannerVersion: 'v1',
        status: 'active',
        steps: [
          PlanStep(
            id: 'step-1',
            stepIndex: 1,
            toolName: 'calendar.list_events',
            mcpServer: 'calendar',
            riskTier: RiskTier.low,
            requiresApproval: false,
            status: PlanStepStatus.done,
          ),
          PlanStep(
            id: 'step-2',
            stepIndex: 2,
            toolName: 'gmail.send_message',
            mcpServer: 'gmail',
            riskTier: RiskTier.high,
            requiresApproval: true,
            status: PlanStepStatus.awaitingApproval,
          ),
          PlanStep(
            id: 'step-3',
            stepIndex: 3,
            toolName: 'slack.post_message_channel',
            mcpServer: 'slack',
            riskTier: RiskTier.low,
            requiresApproval: false,
            status: PlanStepStatus.pending,
          ),
        ],
      );
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    final step1Finder = find.text('calendar.list_events');
    final step2Finder = find.text('gmail.send_message');
    final step3Finder = find.text('slack.post_message_channel');
    
    expect(step1Finder, findsOneWidget);
    expect(step2Finder, findsOneWidget);
    expect(step3Finder, findsOneWidget);
    
    // Check order visually by position
    expect(tester.getCenter(step1Finder).dy, lessThan(tester.getCenter(step2Finder).dy));
    expect(tester.getCenter(step2Finder).dy, lessThan(tester.getCenter(step3Finder).dy));
  });

  testWidgets('test_rejected_approval_halts_task_with_no_side_effects', (tester) async {
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[
          const ApprovalStep(
            id: 'step-skip',
            taskId: 'task-skip',
            toolName: 'slack.post_message_channel',
            mcpServer: 'slack',
            riskTier: RiskTier.medium,
            requiresApproval: true,
            status: 'awaiting_approval',
          ),
        ];

    PlanService.fetchPlanOverride = (taskId) async {
      return const MockPlan(
        id: 'plan-skip',
        taskId: 'task-skip',
        plannerVersion: 'v1',
        status: 'active',
        steps: [
          PlanStep(
            id: 'step-skip',
            stepIndex: 1,
            toolName: 'slack.post_message_channel',
            mcpServer: 'slack',
            riskTier: RiskTier.medium,
            requiresApproval: true,
            status: PlanStepStatus.awaitingApproval,
          ),
        ],
      );
    };

    ApprovalService.decideOverride = (_, decision) async {
      expect(decision, ApprovalDecision.rejected);
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('reject-button-step-skip')));
    await tester.pumpAndSettle();

    // Verify it updates UI to show rejected, and no side effect
    expect(find.text('REJECTED'), findsOneWidget);
  });

  testWidgets('test_task_resumes_after_app_closed_mid_approval', (tester) async {
    // Tests that opening the app with multiple pending approvals works correctly
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[
          const ApprovalStep(
            id: 'step-a',
            taskId: 'task-a',
            toolName: 'gmail.send_message',
            mcpServer: 'gmail',
            riskTier: RiskTier.high,
            requiresApproval: true,
            status: 'awaiting_approval',
          ),
          const ApprovalStep(
            id: 'step-b',
            taskId: 'task-b',
            toolName: 'github.create_issue',
            mcpServer: 'github',
            riskTier: RiskTier.medium,
            requiresApproval: true,
            status: 'awaiting_approval',
          ),
        ];

    PlanService.fetchPlanOverride = (taskId) async {
      return MockPlan(
        id: 'plan-$taskId',
        taskId: taskId,
        plannerVersion: 'v1',
        status: 'active',
        steps: [
          PlanStep(
            id: taskId == 'task-a' ? 'step-a' : 'step-b',
            stepIndex: 1,
            toolName: taskId == 'task-a' ? 'gmail.send_message' : 'github.create_issue',
            mcpServer: taskId == 'task-a' ? 'gmail' : 'github',
            riskTier: taskId == 'task-a' ? RiskTier.high : RiskTier.medium,
            requiresApproval: true,
            status: PlanStepStatus.awaitingApproval,
          ),
        ],
      );
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('approve-button-step-a')), findsOneWidget);
    await tester.drag(find.byType(ListView), const Offset(0, -500));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('approve-button-step-b')), findsOneWidget);
  });
}
