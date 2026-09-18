import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/approval/approval_screen.dart';
import 'package:agentops_copilot/features/approval/approval_service.dart';

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

Widget screen() => MaterialApp(
      theme: AppTheme.light,
      home: const ApprovalScreen(),
    );

void main() {
  tearDown(() {
    ApprovalService.fetchPendingOverride = null;
    ApprovalService.decideOverride = null;
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

  testWidgets('never auto-approves while pending', (tester) async {
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
    expect(find.text('Nothing waiting on you right now'), findsOneWidget);
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
            id: 'step-empty',
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
}
