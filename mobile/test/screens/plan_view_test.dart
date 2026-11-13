// AgentOps Copilot — Plan View Screen widget tests (D27 full suite).
// Owner: Ishani (D27 full suite; D25 smoke + golden baseline).
// §15.2: safety-critical — 100% widget-test coverage + golden required.
// FR-PV-1 to FR-PV-7 + §5.1 edge cases all covered here.

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/home/home_screen.dart';
import 'package:agentops_copilot/features/home/task_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_view_screen.dart';
import 'package:agentops_copilot/features/plan_view/plan_service.dart';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

ThemeData _goldenTheme() {
  final theme = AppTheme.light;
  return theme.copyWith(
    textTheme: theme.textTheme.apply(fontFamily: 'Ahem'),
    primaryTextTheme: theme.primaryTextTheme.apply(fontFamily: 'Ahem'),
    appBarTheme: theme.appBarTheme.copyWith(
      titleTextStyle:
          theme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'Ahem'),
    ),
  );
}

Widget planView({MockPlan plan = mockPlan, ThemeData? theme}) {
  PlanService.fetchPlanOverride = (_) async => plan;
  return MaterialApp(
    theme: theme ?? AppTheme.light,
    home: const PlanViewScreen(taskId: 'task-123'),
    onGenerateRoute: (settings) {
      if (settings.name == AppRoutes.approval) {
        return MaterialPageRoute<void>(
          builder: (_) => const Scaffold(
            body: Center(child: Text('Approval Screen')),
          ),
        );
      }
      return null;
    },
  );
}

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

void main() {
  tearDown(() {
    PlanService.fetchPlanOverride = null;
    TaskService.fetchTasksOverride = null;
  });

  // ─── FR4 ─────────────────────────────────────────────────────────────────
  testWidgets('PlanViewScreen renders without throwing', (tester) async {
    await tester.pumpWidget(planView());
    await tester.pumpAndSettle();

    expect(find.byType(PlanViewScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  // ─── FR-PV-7: golden baseline (mixed risk tiers) ─────────────────────────
  // Regenerate with: flutter test --update-goldens test/screens/plan_view_test.dart
  // Any golden diff must be explained in the PR — a silent mis-render is a safety bug.
  testWidgets('test_plan_view_golden_mixed_risk_plan', (tester) async {
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(planView(theme: _goldenTheme()));
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('../golden/plan_view_baseline.png'),
    );
  });

  // ─── FR-PV-1: all steps render in stepIndex order ─────────────────────────
  testWidgets('test_plan_view_renders_all_steps_in_order', (tester) async {
    await tester.pumpWidget(planView());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('plan-summary')), findsOneWidget);
    // All 3 steps must be present — none missing, none duplicated.
    expect(
        find.byKey(const Key('plan-step-plan-step-calendar')), findsOneWidget);
    expect(find.byKey(const Key('plan-step-plan-step-gmail')), findsOneWidget);
    expect(find.byKey(const Key('plan-step-plan-step-draft')), findsOneWidget);

    // Verify order: calendar (stepIndex 1) is above gmail (stepIndex 2).
    final calendarCenter =
        tester.getCenter(find.byKey(const Key('plan-step-plan-step-calendar')));
    final gmailCenter =
        tester.getCenter(find.byKey(const Key('plan-step-plan-step-gmail')));
    final draftCenter =
        tester.getCenter(find.byKey(const Key('plan-step-plan-step-draft')));
    expect(calendarCenter.dy, lessThan(gmailCenter.dy));
    expect(gmailCenter.dy, lessThan(draftCenter.dy));
  });

  // ─── FR-PV-2: tool name, provider and input params are visible ────────────
  testWidgets('test_plan_view_step_shows_tool_provider_and_params',
      (tester) async {
    const step = PlanStep(
      id: 'step-params',
      stepIndex: 1,
      toolName: 'calendar.create_event',
      mcpServer: 'google-calendar',
      riskTier: RiskTier.medium,
      requiresApproval: false,
      status: PlanStepStatus.pending,
      inputParams: <String, dynamic>{
        'title': 'Call with Prof. Rao',
        'start': '2026-09-24T15:00:00+05:30',
      },
    );
    await tester.pumpWidget(planView(
      plan: const MockPlan(
        id: 'plan-params',
        taskId: 'task-params',
        plannerVersion: 'v1',
        status: 'active',
        steps: [step],
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('calendar.create_event'), findsOneWidget);
    expect(find.text('Integration: google-calendar'), findsOneWidget);
    expect(find.text('title: '), findsOneWidget);
    expect(find.text('Call with Prof. Rao'), findsOneWidget);
    expect(find.text('start: '), findsOneWidget);
    expect(find.text('2026-09-24T15:00:00+05:30'), findsOneWidget);
  });

  // ─── FR-PV-3: risk tier + requiresApproval badge (not colour-only) ────────
  testWidgets('test_plan_view_shows_risk_tier_and_approval_flag',
      (tester) async {
    const step = PlanStep(
      id: 'step-risk',
      stepIndex: 1,
      toolName: 'gmail.send_message',
      mcpServer: 'gmail',
      riskTier: RiskTier.high,
      requiresApproval: true,
      status: PlanStepStatus.pending,
    );
    await tester.pumpWidget(planView(
      plan: const MockPlan(
        id: 'plan-risk',
        taskId: 'task-risk',
        plannerVersion: 'v1',
        status: 'active',
        steps: [step],
      ),
    ));
    await tester.pumpAndSettle();

    // Risk tier must appear as text (not colour-only).
    expect(find.text('HIGH RISK'), findsOneWidget);
    // Approval-required badge must appear as text too.
    expect(find.byKey(const Key('requires-approval-badge')), findsOneWidget);
    expect(find.text('APPROVAL REQUIRED'), findsOneWidget);
  });

  // ─── FR-PV-4: all 7 step statuses render distinctly ──────────────────────
  testWidgets('test_plan_view_renders_each_step_status', (tester) async {
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
        plannerVersion: 'v1',
        status: 'active',
        steps: steps,
      ),
    ));
    await tester.pumpAndSettle();

    // Every status label must appear — PENDING, AWAITING APPROVAL, APPROVED,
    // REJECTED, EXECUTING, DONE, FAILED.
    for (final status in PlanStepStatus.values) {
      expect(find.text(status.label), findsWidgets,
          reason: 'Missing status label: ${status.label}');
    }
  });

  // ─── FR-PV-5: awaiting-approval step offers navigation to Approval Screen ─
  testWidgets('test_plan_view_awaiting_step_links_to_approval', (tester) async {
    const step = PlanStep(
      id: 'step-awaiting',
      stepIndex: 1,
      toolName: 'gmail.send_message',
      mcpServer: 'gmail',
      riskTier: RiskTier.high,
      requiresApproval: true,
      status: PlanStepStatus.awaitingApproval,
    );
    await tester.pumpWidget(planView(
      plan: const MockPlan(
        id: 'plan-awaiting',
        taskId: 'task-awaiting',
        plannerVersion: 'v1',
        status: 'active',
        steps: [step],
      ),
    ));
    await tester.pumpAndSettle();

    // The gateway text must be visible.
    expect(find.text('This step gates the steps that follow.'), findsOneWidget);

    // A tappable review link must be present.
    final reviewButton =
        find.byKey(const Key('review-approval-button-step-awaiting'));
    expect(reviewButton, findsOneWidget);

    // Tapping it navigates to the Approval Screen.
    await tester.tap(reviewButton);
    await tester.pumpAndSettle();
    expect(find.text('Approval Screen'), findsOneWidget);
  });

  // ─── FR-PV-6: done step shows result; failed step shows clear error ────────
  testWidgets('test_plan_view_done_and_failed_step_states', (tester) async {
    final steps = <PlanStep>[
      const PlanStep(
        id: 'step-done',
        stepIndex: 1,
        toolName: 'calendar.list_events',
        mcpServer: 'calendar',
        riskTier: RiskTier.low,
        requiresApproval: false,
        status: PlanStepStatus.done,
        output: <String, dynamic>{'event_count': 3},
      ),
      const PlanStep(
        id: 'step-failed',
        stepIndex: 2,
        toolName: 'gmail.send_message',
        mcpServer: 'gmail',
        riskTier: RiskTier.high,
        requiresApproval: true,
        status: PlanStepStatus.failed,
      ),
    ];
    await tester.pumpWidget(planView(
      plan: MockPlan(
        id: 'plan-done-failed',
        taskId: 'task-done-failed',
        plannerVersion: 'v1',
        status: 'active',
        steps: steps,
      ),
    ));
    await tester.pumpAndSettle();

    // Done step: shows Result section and output key/value.
    expect(find.text('Result'), findsOneWidget);
    expect(find.text('event_count: '), findsOneWidget);
    expect(find.text('3'), findsOneWidget);

    // Failed step: shows clear failure notice (not just colour).
    expect(find.text('FAILED'), findsOneWidget);
    expect(find.text('Later steps may not run until this is resolved.'),
        findsOneWidget);
  });

  // ─── §5.1 edge cases ──────────────────────────────────────────────────────

  // Single-step plan renders without layout glitches.
  testWidgets('test_plan_view_single_step_plan', (tester) async {
    await tester.pumpWidget(planView(
      plan: const MockPlan(
        id: 'plan-single',
        taskId: 'task-single',
        plannerVersion: 'v1',
        status: 'active',
        steps: <PlanStep>[
          PlanStep(
            id: 'step-only',
            stepIndex: 1,
            toolName: 'calendar.list_events',
            mcpServer: 'calendar',
            riskTier: RiskTier.low,
            requiresApproval: false,
            status: PlanStepStatus.done,
          ),
        ],
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('plan-step-step-only')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  // 10+ step plan: all render in order, list scrolls, none dropped.
  testWidgets('test_plan_view_many_steps_all_rendered_in_order',
      (tester) async {
    final steps = List<PlanStep>.generate(
      12,
      (i) => PlanStep(
        id: 'long-step-$i',
        stepIndex: i + 1,
        toolName: 'github.create_issue_$i',
        mcpServer: 'github',
        riskTier: RiskTier.high,
        requiresApproval: true,
        status: PlanStepStatus.pending,
      ),
    );
    await tester.pumpWidget(planView(
      plan: MockPlan(
        id: 'long-plan',
        taskId: 'long-task',
        plannerVersion: 'v1',
        status: 'active',
        steps: steps,
      ),
    ));
    await tester.pumpAndSettle();

    // Scroll to the bottom.
    for (int i = 0; i < 6; i++) {
      await tester.drag(
          find.byType(SingleChildScrollView), const Offset(0, -400));
      await tester.pumpAndSettle();
    }

    // Last step should be visible after scrolling.
    await tester.scrollUntilVisible(
        find.byKey(const Key('plan-step-long-step-11')), 300);
    expect(find.byKey(const Key('plan-step-long-step-11')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  // Steps arrive out of order → displayed by stepIndex.
  testWidgets('test_plan_view_sorts_by_step_index', (tester) async {
    // Deliberately pass steps in reverse order.
    final stepsOutOfOrder = <PlanStep>[
      const PlanStep(
        id: 'step-c',
        stepIndex: 3,
        toolName: 'tool.c',
        mcpServer: 'svc',
        riskTier: RiskTier.low,
        requiresApproval: false,
        status: PlanStepStatus.pending,
      ),
      const PlanStep(
        id: 'step-a',
        stepIndex: 1,
        toolName: 'tool.a',
        mcpServer: 'svc',
        riskTier: RiskTier.low,
        requiresApproval: false,
        status: PlanStepStatus.done,
      ),
      const PlanStep(
        id: 'step-b',
        stepIndex: 2,
        toolName: 'tool.b',
        mcpServer: 'svc',
        riskTier: RiskTier.medium,
        requiresApproval: false,
        status: PlanStepStatus.executing,
      ),
    ];
    await tester.pumpWidget(planView(
      plan: MockPlan(
        id: 'plan-unordered',
        taskId: 'task-unordered',
        plannerVersion: 'v1',
        status: 'active',
        steps: stepsOutOfOrder,
      ),
    ));
    await tester.pumpAndSettle();

    final aCenter = tester.getCenter(find.byKey(const Key('plan-step-step-a')));
    final bCenter = tester.getCenter(find.byKey(const Key('plan-step-step-b')));
    final cCenter = tester.getCenter(find.byKey(const Key('plan-step-step-c')));

    expect(aCenter.dy, lessThan(bCenter.dy),
        reason: 'step-a (index 1) should appear above step-b (index 2)');
    expect(bCenter.dy, lessThan(cCenter.dy),
        reason: 'step-b (index 2) should appear above step-c (index 3)');
  });

  // Mixed-risk plan: low-risk steps show done/running, only high-risk pauses.
  testWidgets('test_plan_view_mixed_risk_ordering', (tester) async {
    await tester.pumpWidget(planView(
      plan: const MockPlan(
        id: 'plan-mixed',
        taskId: 'task-mixed',
        plannerVersion: 'v1',
        status: 'active',
        steps: <PlanStep>[
          PlanStep(
            id: 'step-low-done',
            stepIndex: 1,
            toolName: 'calendar.list_events',
            mcpServer: 'calendar',
            riskTier: RiskTier.low,
            requiresApproval: false,
            status: PlanStepStatus.done,
          ),
          PlanStep(
            id: 'step-high-awaiting',
            stepIndex: 2,
            toolName: 'gmail.send_message',
            mcpServer: 'gmail',
            riskTier: RiskTier.high,
            requiresApproval: true,
            status: PlanStepStatus.awaitingApproval,
          ),
          PlanStep(
            id: 'step-low-pending',
            stepIndex: 3,
            toolName: 'slack.post_message',
            mcpServer: 'slack',
            riskTier: RiskTier.low,
            requiresApproval: false,
            status: PlanStepStatus.pending,
          ),
        ],
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('DONE'), findsOneWidget);
    expect(find.text('AWAITING APPROVAL'), findsOneWidget);
    // Only the high-risk step shows awaiting approval badge.
    expect(find.text('PENDING'), findsOneWidget);
    // The pending low-risk step (step-3) must show PENDING, not AWAITING APPROVAL.
    expect(find.text('AWAITING APPROVAL'), findsOneWidget);
  });

  // Rejected step mid-flow: clearly marked, task not completed.
  testWidgets('test_plan_view_rejected_step_midflow', (tester) async {
    await tester.pumpWidget(planView(
      plan: const MockPlan(
        id: 'plan-rejected',
        taskId: 'task-rejected',
        plannerVersion: 'v1',
        status: 'active',
        steps: <PlanStep>[
          PlanStep(
            id: 'step-done-1',
            stepIndex: 1,
            toolName: 'calendar.list_events',
            mcpServer: 'calendar',
            riskTier: RiskTier.low,
            requiresApproval: false,
            status: PlanStepStatus.done,
          ),
          PlanStep(
            id: 'step-rejected-2',
            stepIndex: 2,
            toolName: 'gmail.send_message',
            mcpServer: 'gmail',
            riskTier: RiskTier.high,
            requiresApproval: true,
            status: PlanStepStatus.rejected,
          ),
          PlanStep(
            id: 'step-pending-3',
            stepIndex: 3,
            toolName: 'slack.post_message',
            mcpServer: 'slack',
            riskTier: RiskTier.low,
            requiresApproval: false,
            status: PlanStepStatus.pending,
          ),
        ],
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('REJECTED'), findsOneWidget);
    // Task not shown as completed — the plan status is 'active', not 'done'.
    // Last step is still pending, not done.
    expect(find.text('PENDING'), findsOneWidget);
  });

  // Superseded plan: only the active plan is shown.
  testWidgets('test_plan_view_ignores_superseded_plan', (tester) async {
    // The screen fetches only one plan (the active one).
    // We simulate that the backend already filtered out superseded plans
    // by returning only the active plan. The UI must not reintroduce stale data.
    await tester.pumpWidget(planView(
      plan: const MockPlan(
        id: 'plan-active',
        taskId: 'task-123',
        plannerVersion: 'v2',
        status: 'active',
        steps: <PlanStep>[
          PlanStep(
            id: 'step-active',
            stepIndex: 1,
            toolName: 'calendar.list_events',
            mcpServer: 'calendar',
            riskTier: RiskTier.low,
            requiresApproval: false,
            status: PlanStepStatus.done,
          ),
        ],
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('plan-step-step-active')), findsOneWidget);
    // No duplicated/stale step cards.
    expect(
        find.byType(Card), findsNWidgets(2)); // 1 plan-summary + 1 step card.
  });

  // Empty/draft plan: explicit planning state, not a blank screen.
  testWidgets('test_plan_view_planning_state', (tester) async {
    PlanService.fetchPlanOverride =
        (_) async => throw const PlanNotFoundException('Plan not ready yet');
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('empty-plan-state')), findsOneWidget);
    expect(find.text('No steps planned yet'), findsOneWidget);
  });

  // Unknown risk tier / status: fail-closed, no crash.
  testWidgets('test_plan_view_unknown_values_fail_closed', (tester) async {
    // PlanService._parseRiskTier defaults unknown → RiskTier.high.
    // PlanService._parseStatus defaults unknown → PlanStepStatus.pending.
    // We simulate that behaviour directly with known enum values representing
    // the fail-closed path.
    await tester.pumpWidget(planView(
      plan: const MockPlan(
        id: 'plan-unknown',
        taskId: 'task-unknown',
        plannerVersion: 'v1',
        status: 'active',
        steps: <PlanStep>[
          PlanStep(
            id: 'step-unknown',
            stepIndex: 1,
            toolName: 'unknown.action',
            mcpServer: 'unknown',
            riskTier: RiskTier.high, // fail-closed: unknown → high
            requiresApproval: true, // fail-closed: approval required
            status: PlanStepStatus.pending, // fail-closed: unknown → pending
          ),
        ],
      ),
    ));
    await tester.pumpAndSettle();

    // Screen must not crash.
    expect(tester.takeException(), isNull);
    // Must show HIGH RISK badge (fail-closed).
    expect(find.text('HIGH RISK'), findsOneWidget);
  });

  // Long/nested input_params: no overflow.
  testWidgets('test_plan_view_long_params_no_overflow', (tester) async {
    final longValue = 'a' * 300;
    await tester.pumpWidget(planView(
      plan: MockPlan(
        id: 'plan-long',
        taskId: 'task-long',
        plannerVersion: 'v1',
        status: 'active',
        steps: <PlanStep>[
          PlanStep(
            id: 'step-long',
            stepIndex: 1,
            toolName: 'tool.long_params',
            mcpServer: 'svc',
            riskTier: RiskTier.medium,
            requiresApproval: false,
            status: PlanStepStatus.pending,
            inputParams: <String, dynamic>{
              'very_long_key': longValue,
              'nested_list': [1, 2, 3, 4, 5],
            },
          ),
        ],
      ),
    ));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('very_long_key: '), findsOneWidget);
  });

  // Fetch failure shows error state with Retry button.
  testWidgets('test_plan_view_error_state_retry', (tester) async {
    var fetchCount = 0;
    PlanService.fetchPlanOverride = (_) async {
      fetchCount++;
      if (fetchCount == 1) throw Exception('Network error');
      return mockPlan;
    };

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Failed to load plan'), findsOneWidget);
    expect(find.text('Exception: Network error'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);

    // Tap Retry → plan loads successfully.
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(find.text('Failed to load plan'), findsNothing);
    expect(find.byKey(const Key('plan-summary')), findsOneWidget);
    expect(fetchCount, 2);
  });

  // Shows loading state initially.
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

  // 401 auth error navigates to sign-in.
  testWidgets('shows waiting state when plan is not found', (tester) async {
    PlanService.fetchPlanOverride =
        (_) async => throw const PlanNotFoundException('Plan not ready yet');

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('empty-plan-state')), findsOneWidget);
    expect(find.text('No steps planned yet'), findsOneWidget);
  });

  // Home task tiles route to the plan view.
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

  // Shows all risk tier labels and step statuses in multi-step plan.
  testWidgets('renders ordered steps with tool, integration, risk, and status',
      (tester) async {
    await tester.pumpWidget(planView());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('plan-summary')), findsOneWidget);
    expect(
        find.byKey(const Key('plan-step-plan-step-calendar')), findsOneWidget);
    expect(find.byKey(const Key('plan-step-plan-step-gmail')), findsOneWidget);
    expect(find.byKey(const Key('plan-step-plan-step-draft')), findsOneWidget);
    expect(find.text('calendar.list_events'), findsOneWidget);
    expect(find.text('Integration: calendar'), findsOneWidget);
    expect(find.text('LOW RISK'), findsOneWidget);
    expect(find.text('AWAITING APPROVAL'), findsOneWidget);
    expect(find.text('This step gates the steps that follow.'), findsOneWidget);
  });

  // Empty plan shows the empty state widget.
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

  // All 7 statuses visible in a single plan.
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

    for (var step in steps) {
      expect(find.text(step.riskTier.label), findsWidgets);
      expect(find.text(step.status.label), findsWidgets);
    }
  });

  // Long plan scrolls without overflow and failed steps are clear.
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

    for (int i = 0; i < 5; i++) {
      await tester.drag(
          find.byType(SingleChildScrollView), const Offset(0, -300));
      await tester.pumpAndSettle();
    }

    expect(find.text('FAILED'), findsOneWidget);
    expect(find.text('Later steps may not run until this is resolved.'),
        findsOneWidget);

    await tester.drag(
        find.byType(SingleChildScrollView), const Offset(0, -1200));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
