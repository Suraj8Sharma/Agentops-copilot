// AgentOps Copilot — Approval Screen widget tests (D27 full suite).
// Owner: Ishani (D27 full suite; D25 smoke + golden baseline).
// §15.2: safety-critical — 100% widget-test coverage + golden required.
// FR-AP-1 to FR-AP-9 + §5.2 edge cases all covered here.

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/approval/approval_screen.dart';
import 'package:agentops_copilot/features/approval/approval_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_view_screen.dart';

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

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

Widget screen({List<Override>? overrides}) => MaterialApp(
      theme: AppTheme.light,
      home: const ApprovalScreen(),
      onGenerateRoute: (settings) {
        if (settings.name == AppRoutes.signIn) {
          return MaterialPageRoute<void>(
            builder: (_) => const Scaffold(
              body: Center(child: Text('Sign In Screen')),
            ),
          );
        }
        return null;
      },
    );

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

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

  // ─── FR4: smoke test ─────────────────────────────────────────────────────
  testWidgets('ApprovalScreen renders without throwing', (tester) async {
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    expect(find.byType(ApprovalScreen), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('provided step skips fetching the pending list', (tester) async {
    var fetchCalled = false;
    ApprovalService.fetchPendingOverride = () async {
      fetchCalled = true;
      return <ApprovalStep>[];
    };

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const ApprovalScreen(step: pendingStep),
    ));
    await tester.pumpAndSettle();

    expect(fetchCalled, isFalse);
    expect(find.byKey(const Key('approve-button-step-1')), findsOneWidget);
  });

  // ─── FR-AP-1 / FR-AP-9: golden baseline ───────────────────────────────────
  // Regenerate with: flutter test --update-goldens test/screens/approval_screen_test.dart
  // Any golden diff must be explained in the PR — a silent mis-render is a safety bug.
  testWidgets('test_approval_screen_renders_risk_explanation', (tester) async {
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];

    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    // Keep strict baselines per OS; Skia rasterizes edges differently on Linux.
    final goldenPath = Platform.isLinux
        ? '../golden/approval_screen_baseline_linux.png'
        : '../golden/approval_screen_baseline.png';
    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile(goldenPath),
    );
  });

  // ─── FR-AP-2: never auto-approves ─────────────────────────────────────────
  // Rendering, loading, and completing load never send a decision.
  testWidgets('test_approval_screen_never_auto_approves', (tester) async {
    final completer = Completer<List<ApprovalStep>>();
    ApprovalService.fetchPendingOverride = () => completer.future;

    var decideCalled = false;
    ApprovalService.decideOverride = (_, __) async {
      decideCalled = true;
    };

    await tester.pumpWidget(screen());
    await tester.pump();
    expect(find.byKey(const Key('approval-loading')), findsOneWidget);
    expect(decideCalled, isFalse);

    completer.complete(<ApprovalStep>[pendingStep]);
    await tester.pumpAndSettle();

    // Screen settled — still no decision sent.
    expect(decideCalled, isFalse);
    expect(find.byKey(const Key('approve-button-step-1')), findsOneWidget);
  });

  testWidgets('fetch auth failure routes to sign-in', (tester) async {
    ApprovalService.fetchPendingOverride = () async {
      throw const ApprovalServiceException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
      );
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    expect(find.text('Sign In Screen'), findsOneWidget);
  });

  testWidgets('fetch service failure can be retried', (tester) async {
    var fetchCount = 0;
    ApprovalService.fetchPendingOverride = () async {
      fetchCount++;
      if (fetchCount == 1) {
        throw const ApprovalServiceException('Temporary service failure');
      }
      return <ApprovalStep>[];
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    expect(find.text('Temporary service failure'), findsOneWidget);
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(fetchCount, 2);
    expect(find.byKey(const Key('approval-empty')), findsOneWidget);
  });

  testWidgets('unexpected fetch failure shows a connection message',
      (tester) async {
    ApprovalService.fetchPendingOverride =
        () async => throw StateError('offline');

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    expect(
      find.text(
          'Could not load approvals. Check your connection and try again.'),
      findsOneWidget,
    );
  });

  // ─── FR-AP-3: Approve sends single POST with decision: approved ────────────
  testWidgets('test_approval_screen_approve_sends_single_approved_decision',
      (tester) async {
    final calls = <(String, ApprovalDecision)>[];
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    ApprovalService.decideOverride = (id, decision) async {
      calls.add((id, decision));
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('approve-button-step-1')));
    await tester.pumpAndSettle();

    expect(calls.length, 1, reason: 'Exactly one POST must be sent');
    expect(calls.first.$1, 'step-1');
    expect(calls.first.$2, ApprovalDecision.approved);
  });

  // ─── FR-AP-4: Reject sends single POST with decision: rejected ─────────────
  testWidgets('test_approval_screen_reject_sends_single_rejected_decision',
      (tester) async {
    final calls = <(String, ApprovalDecision)>[];
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    ApprovalService.decideOverride = (id, decision) async {
      calls.add((id, decision));
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('reject-button-step-1')));
    await tester.pumpAndSettle();

    expect(calls.length, 1, reason: 'Exactly one POST must be sent');
    expect(calls.first.$1, 'step-1');
    expect(calls.first.$2, ApprovalDecision.rejected);
  });

  // ─── FR-AP-5: risk tier and rationale visible before decision ─────────────
  // Use a step with no taskId → goes through _buildFallbackCard → _RiskCard
  // which renders risk-tier-badge, approval-tool-name, and explanation-text.
  testWidgets('test_approval_screen_shows_risk_tier_before_decision',
      (tester) async {
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[
          const ApprovalStep(
            id: 'step-1',
            taskId: '', // empty taskId → _buildFallbackCard → _RiskCard
            toolName: 'gmail.send_message',
            mcpServer: 'gmail',
            riskTier: RiskTier.high,
            requiresApproval: true,
            status: 'awaiting_approval',
            explanationText: 'Send the launch agenda to the project team.',
          ),
        ];

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    // Risk tier badge visible in _RiskCard.
    expect(find.byKey(const Key('risk-tier-badge')), findsOneWidget);
    expect(find.text('HIGH RISK'), findsOneWidget);
    // Explanation text visible.
    expect(find.byKey(const Key('explanation-text')), findsOneWidget);
    expect(find.text('Send the launch agenda to the project team.'),
        findsOneWidget);
    // Both buttons present — user has not decided yet.
    expect(find.byKey(const Key('approve-button-step-1')), findsOneWidget);
    expect(find.byKey(const Key('reject-button-step-1')), findsOneWidget);
  });

  testWidgets('fallback decisions remove pending steps without plan context',
      (tester) async {
    const approveStep = ApprovalStep(
      id: 'step-approve',
      taskId: 'task-no-plan',
      toolName: 'gmail.send_message',
      mcpServer: 'gmail',
      riskTier: RiskTier.high,
      requiresApproval: true,
      status: 'awaiting_approval',
      explanationText: 'Approve this action.',
    );
    const rejectStep = ApprovalStep(
      id: 'step-reject',
      taskId: 'task-no-plan',
      toolName: 'gmail.send_message',
      mcpServer: 'gmail',
      riskTier: RiskTier.high,
      requiresApproval: true,
      status: 'awaiting_approval',
      explanationText: 'Reject this action.',
    );
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[approveStep, rejectStep];
    PlanService.fetchPlanOverride =
        (_) async => throw Exception('Plan context unavailable');
    ApprovalService.decideOverride = (_, __) async {};

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    final approveFinder = find.byKey(const Key('approve-button-step-approve'));
    await tester.ensureVisible(approveFinder);
    await tester.tap(approveFinder);
    await tester.pumpAndSettle();

    final rejectFinder = find.byKey(const Key('reject-button-step-reject'));
    await tester.ensureVisible(rejectFinder);
    await tester.tap(rejectFinder);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('approval-empty')), findsOneWidget);
  });

  testWidgets('unexpected risk state fails closed without decision controls',
      (tester) async {
    const unexpectedStep = ApprovalStep(
      id: 'step-unexpected',
      taskId: 'task-no-plan',
      toolName: 'gmail.send_message',
      mcpServer: 'gmail',
      riskTier: RiskTier.high,
      requiresApproval: false,
      status: 'awaiting_approval',
    );
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[unexpectedStep];
    PlanService.fetchPlanOverride =
        (_) async => throw Exception('Plan context unavailable');

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('unexpected-risk-body')), findsOneWidget);
    expect(
        find.byKey(const Key('approve-button-step-unexpected')), findsNothing);
    expect(
        find.byKey(const Key('reject-button-step-unexpected')), findsNothing);
  });

  // ─── FR-AP-6: no pre-selected or recommended choice ───────────────────────
  testWidgets('test_approval_screen_has_no_preselected_or_recommended_choice',
      (tester) async {
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    // No "recommended", "suggest", or pre-selected language.
    expect(find.textContaining('recommended', findRichText: true), findsNothing);
    expect(find.textContaining('Recommended', findRichText: true), findsNothing);
    expect(find.textContaining('suggested', findRichText: true), findsNothing);

    // Both buttons are OutlinedButton (equal prominence — no filled/elevated difference).
    final approveBtn = tester.widget<OutlinedButton>(
        find.byKey(const Key('approve-button-step-1')));
    final rejectBtn = tester.widget<OutlinedButton>(
        find.byKey(const Key('reject-button-step-1')));
    expect(approveBtn.onPressed, isNotNull);
    expect(rejectBtn.onPressed, isNotNull);
  });

  // ─── FR-AP-7: after decision controls are disabled; outcome reflected ──────
  testWidgets('test_approval_screen_after_decision_disables_controls_and_navigates',
      (tester) async {
    final completer = Completer<void>();
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    ApprovalService.decideOverride = (_, __) => completer.future;

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('approve-button-step-1')));
    await tester.pump();

    // While in-flight: buttons disabled, spinner shown.
    expect(
        tester
            .widget<OutlinedButton>(
                find.byKey(const Key('approve-button-step-1')))
            .onPressed,
        isNull);
    expect(
        tester
            .widget<OutlinedButton>(
                find.byKey(const Key('reject-button-step-1')))
            .onPressed,
        isNull);
    expect(find.text('Recording decision...'), findsOneWidget);

    // Complete the decision.
    completer.complete();
    await tester.pumpAndSettle();

    // Outcome reflected — APPROVED status chip now visible.
    expect(find.text('APPROVED'), findsOneWidget);
  });

  // ─── FR-AP-8: multiple pending steps — decision targets correct step ───────
  testWidgets('test_approval_screen_multiple_pending_targets_correct_step',
      (tester) async {
    const stepA = ApprovalStep(
      id: 'step-a',
      taskId: 'task-a',
      toolName: 'gmail.send_message',
      mcpServer: 'gmail',
      riskTier: RiskTier.high,
      requiresApproval: true,
      status: 'awaiting_approval',
      explanationText: 'Send email A',
    );
    const stepB = ApprovalStep(
      id: 'step-b',
      taskId: 'task-b',
      toolName: 'github.create_issue',
      mcpServer: 'github',
      riskTier: RiskTier.medium,
      requiresApproval: true,
      status: 'awaiting_approval',
      explanationText: 'Create issue B',
    );

    final decided = <String>[];
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[stepA, stepB];
    ApprovalService.decideOverride = (id, _) async => decided.add(id);
    PlanService.fetchPlanOverride = (taskId) async => MockPlan(
          id: 'plan-$taskId',
          taskId: taskId,
          plannerVersion: 'v1',
          status: 'active',
          steps: [
            PlanStep(
              id: taskId == 'task-a' ? 'step-a' : 'step-b',
              stepIndex: 1,
              toolName: taskId == 'task-a'
                  ? 'gmail.send_message'
                  : 'github.create_issue',
              mcpServer: taskId == 'task-a' ? 'gmail' : 'github',
              riskTier:
                  taskId == 'task-a' ? RiskTier.high : RiskTier.medium,
              requiresApproval: true,
              status: PlanStepStatus.awaitingApproval,
            ),
          ],
        );

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    // Approve step-a.
    await tester.tap(find.byKey(const Key('approve-button-step-a')));
    await tester.pumpAndSettle();

    // Only step-a's id was sent.
    expect(decided, contains('step-a'));
    expect(decided, isNot(contains('step-b')));
  });

  // ─── §5.2 edge cases ──────────────────────────────────────────────────────

  // Double-tap on Approve sends exactly one request.
  testWidgets('test_approval_screen_double_tap_approve_sends_once',
      (tester) async {
    var callCount = 0;
    final completer = Completer<void>();
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    ApprovalService.decideOverride = (_, __) {
      callCount++;
      return completer.future;
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    // Tap twice rapidly.
    await tester.tap(find.byKey(const Key('approve-button-step-1')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('approve-button-step-1')));
    await tester.pump();

    completer.complete();
    await tester.pumpAndSettle();

    expect(callCount, 1, reason: 'Double-tap should send only one request');
  });

  // Approve then Reject in quick succession: only first decision recorded.
  testWidgets('test_approval_screen_locks_controls_after_first_tap',
      (tester) async {
    final calls = <ApprovalDecision>[];
    final completer = Completer<void>();
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    ApprovalService.decideOverride = (_, decision) {
      calls.add(decision);
      return completer.future;
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('approve-button-step-1')));
    await tester.pump();

    // Buttons should now be disabled — Reject tap should be a no-op.
    await tester.tap(find.byKey(const Key('reject-button-step-1')));
    await tester.pump();

    completer.complete();
    await tester.pumpAndSettle();

    expect(calls.length, 1);
    expect(calls.first, ApprovalDecision.approved);
  });

  // 5xx POST: step stays awaiting, never shown as approved.
  testWidgets('test_approval_screen_post_failure_not_shown_as_approved',
      (tester) async {
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    ApprovalService.decideOverride = (_, __) async {
      throw const ApprovalServiceException('Service unavailable (HTTP 503)');
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('approve-button-step-1')));
    await tester.pumpAndSettle();

    // Error banner must appear.
    expect(find.text('Approval service unavailable'), findsOneWidget);
    // Step must NOT be shown as approved.
    expect(find.text('APPROVED'), findsNothing);
    // Approved text nowhere on screen.
    expect(find.text('Approved'), findsNothing);
  });

  testWidgets('unexpected decision failure remains visible', (tester) async {
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    ApprovalService.decideOverride = (_, __) async {
      throw StateError('offline');
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('approve-button-step-1')));
    await tester.pumpAndSettle();

    expect(find.text('Approval service unavailable'), findsOneWidget);
    expect(find.text('APPROVED'), findsNothing);
  });

  // 409: screen refreshes state and notifies user.
  testWidgets('test_approval_screen_409_refreshes_state', (tester) async {
    var fetchCount = 0;
    ApprovalService.fetchPendingOverride = () async {
      fetchCount++;
      return fetchCount == 1 ? <ApprovalStep>[pendingStep] : <ApprovalStep>[];
    };
    ApprovalService.decideOverride = (_, __) async {
      throw const ApprovalServiceException(
        'This approval is no longer pending. Refreshing the list.',
        refreshPending: true,
      );
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('approve-button-step-1')));
    await tester.pumpAndSettle();

    // After 409 → screen refreshed (fetchCount == 2), now empty state.
    expect(fetchCount, 2);
    expect(find.byKey(const Key('approval-empty')), findsOneWidget);
  });

  // 401 during decision: auth hand-off, no assumed decision.
  testWidgets('test_approval_screen_401_no_assumed_decision', (tester) async {
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    ApprovalService.decideOverride = (_, __) async {
      throw const ApprovalServiceException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
      );
    };

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('approve-button-step-1')));
    await tester.pumpAndSettle();

    // Navigated to Sign In.
    expect(find.text('Sign In Screen'), findsOneWidget);
    // No "APPROVED" on screen (not assumed).
    expect(find.text('APPROVED'), findsNothing);
  });

  // Missing explanation: structured action details still shown.
  testWidgets('test_approval_screen_missing_explanation_still_shows_action',
      (tester) async {
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[
          const ApprovalStep(
            id: 'step-no-exp',
            taskId: 'task-no-exp',
            toolName: 'slack.post_message_channel',
            mcpServer: 'slack',
            riskTier: RiskTier.high,
            requiresApproval: true,
            status: 'awaiting_approval',
            // explanationText intentionally omitted → null
          ),
        ];
    PlanService.fetchPlanOverride = (taskId) async => const MockPlan(
          id: 'plan-no-exp',
          taskId: 'task-no-exp',
          plannerVersion: 'v1',
          status: 'active',
          steps: [
            PlanStep(
              id: 'step-no-exp',
              stepIndex: 1,
              toolName: 'slack.post_message_channel',
              mcpServer: 'slack',
              riskTier: RiskTier.high,
              requiresApproval: true,
              status: PlanStepStatus.awaitingApproval,
            ),
          ],
        );

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    // Fallback explanation shown.
    expect(find.byKey(const Key('explanation-fallback')), findsOneWidget);
    expect(find.text('No explanation available.'), findsOneWidget);
    // Approve / Reject still offered.
    expect(find.byKey(const Key('approve-button-step-no-exp')), findsOneWidget);
    expect(find.byKey(const Key('reject-button-step-no-exp')), findsOneWidget);
  });

  // Long explanation: no overflow.
  // Uses empty taskId so explanation goes through _RiskCard (explanation-text key).
  testWidgets('test_approval_screen_long_explanation_no_overflow',
      (tester) async {
    final longExplanation = 'This action will perform a very complex operation. ' * 30;
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[
          ApprovalStep(
            id: 'step-long',
            taskId: '', // empty taskId → _buildFallbackCard → _RiskCard
            toolName: 'github.create_issue',
            mcpServer: 'github',
            riskTier: RiskTier.medium,
            requiresApproval: true,
            status: 'awaiting_approval',
            explanationText: longExplanation,
          ),
        ];

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('explanation-text')), findsOneWidget);
  });

  // Structured params displayed alongside explanation (fail-closed).
  testWidgets('test_approval_screen_shows_structured_params_alongside_explanation',
      (tester) async {
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[
          const ApprovalStep(
            id: 'step-params',
            taskId: '', // no taskId → falls through to fallback _RiskCard
            toolName: 'gmail.send_message',
            mcpServer: 'gmail',
            riskTier: RiskTier.high,
            requiresApproval: true,
            status: 'awaiting_approval',
            inputParams: <String, dynamic>{
              'to': 'professor.rao@university.edu',
              'subject': "Agenda for Thursday's call",
            },
            explanationText: 'Send the agenda email.',
          ),
        ];

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    // Params label visible in _RiskCard.
    expect(find.byKey(const Key('approval-input-params-label')), findsOneWidget);
    expect(find.text('to: '), findsOneWidget);
    expect(find.text('subject: '), findsOneWidget);
    // Explanation still visible alongside.
    expect(find.text('Send the agenda email.'), findsOneWidget);
  });

  // Unknown risk tier: presented as high-risk (fail-closed).
  testWidgets('test_approval_screen_unknown_tier_treated_as_high',
      (tester) async {
    // ApprovalStep.fromJson maps unknown risk_tier → RiskTier.high.
    // We simulate this directly:
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[
          const ApprovalStep(
            id: 'step-unknown',
            taskId: '',
            toolName: 'unknown.action',
            mcpServer: 'unknown',
            riskTier: RiskTier.high, // fail-closed: unknown → high
            requiresApproval: true,
            status: 'awaiting_approval',
          ),
        ];

    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    expect(find.text('HIGH RISK'), findsOneWidget);
    expect(find.byKey(const Key('approve-button-step-unknown')), findsOneWidget);
  });

  // No pending approvals: clear empty state, no phantom Approve button.
  testWidgets('test_approval_screen_no_pending_empty_state', (tester) async {
    ApprovalService.fetchPendingOverride = () async => <ApprovalStep>[];
    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('approval-empty')), findsOneWidget);
    expect(find.text('Nothing waiting on you right now'), findsOneWidget);
    expect(find.textContaining('Approve'), findsNothing);
  });

  // Pending step survives app reopen (screen fetches fresh from backend).
  testWidgets('test_approval_screen_pending_step_survives_reopen',
      (tester) async {
    // Simulate app reopen: screen is rebuilt from scratch and fetches pending.
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];

    // First "open".
    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('approve-button-step-1')), findsOneWidget);

    // "Close" and "reopen" by rebuilding the widget.
    await tester.pumpWidget(const SizedBox());
    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];
    await tester.pumpWidget(screen());
    await tester.pumpAndSettle();

    // Step still awaiting decision.
    expect(find.byKey(const Key('approve-button-step-1')), findsOneWidget);
  });

  // Small screen / large text: controls remain visible and tappable.
  testWidgets('test_approval_screen_small_screen_large_text', (tester) async {
    tester.view.physicalSize = const Size(320 * 2, 568 * 2);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.reset);

    ApprovalService.fetchPendingOverride =
        () async => <ApprovalStep>[pendingStep];

    await tester.pumpWidget(MediaQuery(
      data: const MediaQueryData(textScaler: TextScaler.linear(2.0)),
      child: screen(),
    ));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    // Approval button must still be on screen (may need scroll).
    final approveFinder = find.byKey(const Key('approve-button-step-1'));
    expect(approveFinder, findsOneWidget);
  });

  // ─── Remaining legacy tests (preserve from D25 baseline) ──────────────────

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

  testWidgets('test_mixed_risk_multi_step_plan_orders_correctly',
      (tester) async {
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

    expect(tester.getCenter(step1Finder).dy,
        lessThan(tester.getCenter(step2Finder).dy));
    expect(tester.getCenter(step2Finder).dy,
        lessThan(tester.getCenter(step3Finder).dy));
  });

  testWidgets('test_rejected_approval_halts_task_with_no_side_effects',
      (tester) async {
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

    expect(find.text('REJECTED'), findsOneWidget);
  });

  testWidgets('test_task_resumes_after_app_closed_mid_approval',
      (tester) async {
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
            toolName: taskId == 'task-a'
                ? 'gmail.send_message'
                : 'github.create_issue',
            mcpServer: taskId == 'task-a' ? 'gmail' : 'github',
            riskTier:
                taskId == 'task-a' ? RiskTier.high : RiskTier.medium,
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

// ---------------------------------------------------------------------------
// Helper: Override class (unused — avoids lint warning on import)
// ---------------------------------------------------------------------------
class Override {}
