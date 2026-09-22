import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/approval/approval_screen.dart';
import 'package:agentops_copilot/features/approval/approval_service.dart';
import 'package:agentops_copilot/features/home/home_screen.dart';
import 'package:agentops_copilot/features/home/task_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_view_screen.dart';

void main() {
  tearDown(() {
    TaskService.fetchTasksOverride = null;
    TaskService.createTaskOverride = null;
    ApprovalService.fetchPendingOverride = null;
    ApprovalService.decideOverride = null;
    PlanService.fetchPlanOverride = null;
  });

  test('follows the Composer → Home → Plan → Approval contract', () async {
    final task = AppTask(
      id: 'task-1',
      inputType: 'text',
      rawInput: 'Send the weekly update',
      status: TaskStatus.awaitingApproval,
      createdAt: DateTime(2026, 9, 12),
    );
    final plan = MockPlan(
      id: 'plan-1',
      taskId: task.id,
      plannerVersion: 'planner-v1',
      status: 'active',
      steps: <PlanStep>[
        const PlanStep(
          id: 'step-low',
          stepIndex: 0,
          toolName: 'calendar.list_events',
          mcpServer: 'calendar',
          riskTier: RiskTier.low,
          requiresApproval: false,
          status: PlanStepStatus.done,
        ),
        const PlanStep(
          id: 'step-high',
          stepIndex: 1,
          toolName: 'gmail.send_message',
          mcpServer: 'gmail',
          riskTier: RiskTier.high,
          requiresApproval: true,
          status: PlanStepStatus.awaitingApproval,
        ),
      ],
    );
    const approval = ApprovalStep(
      id: 'step-high',
      taskId: 'task-1',
      toolName: 'gmail.send_message',
      mcpServer: 'gmail',
      riskTier: RiskTier.high,
      requiresApproval: true,
      status: 'awaiting_approval',
      explanationText: 'Send the weekly update to the team.',
    );

    TaskService.createTaskOverride = (_) async => task;
    TaskService.fetchTasksOverride = () async => <AppTask>[task];
    PlanService.fetchPlanOverride = (_) async => plan;
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[approval];
    var recordedDecision = false;
    ApprovalService.decideOverride = (_, decision) async {
      expect(decision, ApprovalDecision.approved);
      recordedDecision = true;
    };

    final created = await TaskService.createTextTask(task.rawInput);
    final homeTasks = await TaskService.fetchTasks();
    final loadedPlan = await PlanService.fetchPlan(created.id);
    final pending = await ApprovalService.fetchPending();
    await ApprovalService.decide(pending.single.id, ApprovalDecision.approved);

    expect(created.status, TaskStatus.awaitingApproval);
    expect(homeTasks.single.id, task.id);
    expect(loadedPlan.steps.map((step) => step.stepIndex), <int>[0, 1]);
    expect(pending.single.explanationText, approval.explanationText);
    expect(recordedDecision, isTrue);
  });
}
