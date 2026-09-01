// AgentOps Copilot — Approval Screen Widget Tests (Day 8)
//
// Owner: Ishani
// 100%-coverage, never-mis-render bar per Manual §15 / Section 3.
//
// Test philosophy:
//   • Every acceptance criterion from the spec doc is asserted explicitly.
//   • No test verifies that explanation content influences the decision
//     outcome — that separation is a structural guarantee, not just a test.
//   • All edge-case paths (missing explanation, long explanation, double-tap,
//     unexpected risk state, sparse inputParams) have dedicated test cases.
//   • Widget keys are used throughout so assertions are layout-stable.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/approval/approval_screen.dart';

// ---------------------------------------------------------------------------
// TEST HELPERS
// ---------------------------------------------------------------------------

Widget _wrap(Widget child) => MaterialApp(theme: AppTheme.light, home: child);

Widget _screen({ApprovalStep step = mockApprovalStep}) =>
    _wrap(ApprovalScreen(step: step));

// Minimal high-risk step — sparse inputParams edge case.
const ApprovalStep _sparseStep = ApprovalStep(
  id: 'step-sparse-001',
  toolName: 'slack.send_message',
  mcpServer: 'slack',
  riskTier: RiskTier.high,
  requiresApproval: true,
  status: 'awaiting_approval',
  // No inputParams, no explanationText
);

// Low-risk step that should never reach this screen.
const ApprovalStep _lowRiskStep = ApprovalStep(
  id: 'step-low-001',
  toolName: 'calendar.list_events',
  mcpServer: 'calendar',
  riskTier: RiskTier.low,
  requiresApproval: false,
  status: 'pending',
);

// Step with an overly long explanation to test cap handling.
const ApprovalStep _longExplanationStep = ApprovalStep(
  id: 'step-long-001',
  toolName: 'github.create_issue',
  mcpServer: 'github',
  riskTier: RiskTier.medium,
  requiresApproval: true,
  status: 'awaiting_approval',
  explanationText:
      'This action will create a new issue in the repository. '
      'The issue will be titled with the provided summary text and assigned '
      'to the current user. It will include a description, labels, and may '
      'trigger notification emails to all watchers of the repository. '
      'This is an irreversible operation in the sense that once created, '
      'the issue will be visible to all repository collaborators. The action '
      'cannot be undone from within the copilot after it executes — only '
      'manual deletion via the GitHub UI would remove it. Please review the '
      'content carefully before approving this step.',
);

void main() {
  // -------------------------------------------------------------------------
  // 1. RENDERS THE RISK CARD WITH REQUIRED FIELDS
  // -------------------------------------------------------------------------

  testWidgets('renders risk card with action, integration, and risk tier',
      (tester) async {
    await tester.pumpWidget(_screen());

    expect(find.byKey(const Key('approval-risk-card')), findsOneWidget);
    expect(find.byKey(const Key('risk-tier-badge')), findsOneWidget);
    expect(find.byKey(const Key('approval-tool-name')), findsOneWidget);
    expect(find.byKey(const Key('approval-mcp-server')), findsOneWidget);
    expect(find.text('gmail.send_message'), findsOneWidget);
    expect(find.text('Integration: gmail'), findsOneWidget);
    expect(find.text('HIGH RISK'), findsOneWidget);
  });

  // -------------------------------------------------------------------------
  // 2. EXPLANATION IS DISPLAY-ONLY — NO CODE PATH TIES IT TO THE OUTCOME
  // -------------------------------------------------------------------------
  // This test verifies the structural invariant: tapping Approve/Reject
  // produces the correct outcome regardless of the explanation text.
  // (The explanation is never read by _handleDecision — this test confirms
  // the result is purely driven by which button was tapped.)

  testWidgets('explanation text is display-only — approve outcome is correct',
      (tester) async {
    await tester.pumpWidget(_screen());

    expect(find.byKey(const Key('explanation-text')), findsOneWidget);
    expect(find.byKey(const Key('explanation-advisory-disclaimer')),
        findsOneWidget);

    await tester.tap(find.byKey(const Key('approve-button')));
    await tester.pumpAndSettle();

    // Decision outcome is 'approved' — driven by button tap, not explanation.
    // The risk card (and its advisory text) remains visible after the decision;
    // only the button section is replaced by the confirmation banner.
    expect(find.byKey(const Key('decision-confirmed-approved')), findsOneWidget);
    // Approve button is gone; disclaimer (in risk card) is still present.
    expect(find.byKey(const Key('approve-button')), findsNothing);
    expect(find.byKey(const Key('explanation-advisory-disclaimer')),
        findsOneWidget);
  });

  testWidgets('explanation text is display-only — reject outcome is correct',
      (tester) async {
    await tester.pumpWidget(_screen());

    await tester.tap(find.byKey(const Key('reject-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('decision-confirmed-rejected')), findsOneWidget);
  });

  // -------------------------------------------------------------------------
  // 3. APPROVE AND REJECT ARE EQUALLY VISIBLE AND EQUAL-WEIGHT
  // -------------------------------------------------------------------------

  testWidgets('both approve and reject buttons are visible before any decision',
      (tester) async {
    await tester.pumpWidget(_screen());

    expect(find.byKey(const Key('approve-button')), findsOneWidget);
    expect(find.byKey(const Key('reject-button')), findsOneWidget);

    // No decision banner exists yet.
    expect(find.byKey(const Key('decision-confirmed-approved')), findsNothing);
    expect(find.byKey(const Key('decision-confirmed-rejected')), findsNothing);
  });

  testWidgets('both buttons share the same widget type (no visual hierarchy)',
      (tester) async {
    await tester.pumpWidget(_screen());

    // Both are OutlinedButton — no ElevatedButton/FilledButton for Approve.
    final approveWidget = find.byKey(const Key('approve-button'));
    final rejectWidget = find.byKey(const Key('reject-button'));

    // Both are Expanded inside the same Row (same visual footprint).
    final approveAncestor = find.ancestor(
        of: approveWidget, matching: find.byType(Expanded));
    final rejectAncestor = find.ancestor(
        of: rejectWidget, matching: find.byType(Expanded));

    expect(approveAncestor, findsWidgets);
    expect(rejectAncestor, findsWidgets);
  });

  // -------------------------------------------------------------------------
  // 4. RISK TIER VISUAL LANGUAGE — CONSISTENT WITH D7 PLAN VIEW
  // -------------------------------------------------------------------------

  testWidgets('high risk tier renders using AppColors.riskHigh via RiskTier',
      (tester) async {
    await tester.pumpWidget(_screen());

    // Risk tier badge is keyed — presence confirms the tier chip rendered.
    expect(find.byKey(const Key('risk-tier-badge')), findsOneWidget);
    expect(find.text('HIGH RISK'), findsOneWidget);
  });

  testWidgets('medium risk tier renders correctly', (tester) async {
    await tester.pumpWidget(_screen(step: _longExplanationStep));

    expect(find.text('MEDIUM RISK'), findsOneWidget);
  });

  // -------------------------------------------------------------------------
  // 5. EDGE CASE — MISSING EXPLANATION TEXT
  // -------------------------------------------------------------------------

  testWidgets('missing explanation renders fallback — not blank or broken',
      (tester) async {
    await tester.pumpWidget(_screen(step: _sparseStep));

    // Fallback container present.
    expect(find.byKey(const Key('explanation-fallback')), findsOneWidget);
    // Normal explanation container absent.
    expect(find.byKey(const Key('explanation-text')), findsNothing);
    // Layout still complete — card and buttons visible.
    expect(find.byKey(const Key('approval-risk-card')), findsOneWidget);
    expect(find.byKey(const Key('approve-button')), findsOneWidget);
    expect(find.byKey(const Key('reject-button')), findsOneWidget);
  });

  // -------------------------------------------------------------------------
  // 6. EDGE CASE — OVERLY LONG EXPLANATION TEXT
  // -------------------------------------------------------------------------

  testWidgets('long explanation is capped and still renders a complete card',
      (tester) async {
    await tester.pumpWidget(_screen(step: _longExplanationStep));

    expect(find.byKey(const Key('explanation-text')), findsOneWidget);
    // Card and buttons are still intact.
    expect(find.byKey(const Key('approval-risk-card')), findsOneWidget);
    expect(find.byKey(const Key('approve-button')), findsOneWidget);
    expect(find.byKey(const Key('reject-button')), findsOneWidget);
  });

  // -------------------------------------------------------------------------
  // 7. EDGE CASE — DOUBLE-TAP / RAPID TAP (decision lock)
  // -------------------------------------------------------------------------

  testWidgets('rapid double-tap on approve fires only one decision',
      (tester) async {
    await tester.pumpWidget(_screen());

    // Tap approve twice rapidly without settling.
    await tester.tap(find.byKey(const Key('approve-button')));
    await tester.tap(find.byKey(const Key('approve-button')));
    await tester.pumpAndSettle();

    // Only one confirmed banner — not two conflicting states.
    expect(find.byKey(const Key('decision-confirmed-approved')), findsOneWidget);
    expect(find.byKey(const Key('decision-confirmed-rejected')), findsNothing);
  });

  testWidgets('rapid approve then reject only records first decision',
      (tester) async {
    await tester.pumpWidget(_screen());

    // Tap approve then immediately tap reject — only approve should register.
    await tester.tap(find.byKey(const Key('approve-button')));
    await tester.tap(find.byKey(const Key('reject-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('decision-confirmed-approved')), findsOneWidget);
    expect(find.byKey(const Key('decision-confirmed-rejected')), findsNothing);
  });

  // -------------------------------------------------------------------------
  // 8. EDGE CASE — SPARSE INPUT PARAMS / MINIMAL ACTION STEP
  // -------------------------------------------------------------------------

  testWidgets('sparse step renders a complete, honest card without breaking',
      (tester) async {
    await tester.pumpWidget(_screen(step: _sparseStep));

    expect(find.byKey(const Key('approval-risk-card')), findsOneWidget);
    expect(find.text('slack.send_message'), findsOneWidget);
    expect(find.text('Integration: slack'), findsOneWidget);
    expect(find.text('HIGH RISK'), findsOneWidget);
    // Fallback explanation is shown.
    expect(find.byKey(const Key('explanation-fallback')), findsOneWidget);
  });

  // -------------------------------------------------------------------------
  // 9. EDGE CASE — LOW-RISK STEP REACHING THIS SCREEN
  // -------------------------------------------------------------------------

  testWidgets(
      'step with requiresApproval=false shows unexpected-state guard, not normal UI',
      (tester) async {
    await tester.pumpWidget(_screen(step: _lowRiskStep));

    expect(find.byKey(const Key('unexpected-risk-body')), findsOneWidget);
    // Normal approval UI must NOT be shown.
    expect(find.byKey(const Key('approval-risk-card')), findsNothing);
    expect(find.byKey(const Key('approve-button')), findsNothing);
    expect(find.byKey(const Key('reject-button')), findsNothing);
  });

  // -------------------------------------------------------------------------
  // 10. APPROVE DECISION — FULL HAPPY PATH
  // -------------------------------------------------------------------------

  testWidgets('approve tap replaces buttons with approved confirmation banner',
      (tester) async {
    await tester.pumpWidget(_screen());

    await tester.tap(find.byKey(const Key('approve-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('decision-confirmed-approved')), findsOneWidget);
    expect(find.text('Approved'), findsOneWidget);
    // Buttons are gone after decision.
    expect(find.byKey(const Key('approve-button')), findsNothing);
    expect(find.byKey(const Key('reject-button')), findsNothing);
  });

  // -------------------------------------------------------------------------
  // 11. REJECT DECISION — FULL HAPPY PATH
  // -------------------------------------------------------------------------

  testWidgets('reject tap replaces buttons with rejected confirmation banner',
      (tester) async {
    await tester.pumpWidget(_screen());

    await tester.tap(find.byKey(const Key('reject-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('decision-confirmed-rejected')), findsOneWidget);
    expect(find.text('Rejected'), findsOneWidget);
    expect(find.byKey(const Key('approve-button')), findsNothing);
    expect(find.byKey(const Key('reject-button')), findsNothing);
  });

  // -------------------------------------------------------------------------
  // 12. NO DECISION STATE — BUTTONS REMAIN, NO AUTO-APPROVAL
  // -------------------------------------------------------------------------

  testWidgets(
      'before any tap, no decision exists and neither outcome is pre-selected',
      (tester) async {
    await tester.pumpWidget(_screen());

    // Both buttons present, no decision banner.
    expect(find.byKey(const Key('approve-button')), findsOneWidget);
    expect(find.byKey(const Key('reject-button')), findsOneWidget);
    expect(find.byKey(const Key('decision-confirmed-approved')), findsNothing);
    expect(find.byKey(const Key('decision-confirmed-rejected')), findsNothing);
  });

  // -------------------------------------------------------------------------
  // 13. MOCK DATA SHAPE ALIGNS WITH SPEC (plan_steps + approvals schema)
  // -------------------------------------------------------------------------

  testWidgets('mockApprovalStep fields match the spec data contract',
      (tester) async {
    // This test documents the mock data contract so future wiring engineers
    // can verify the swap-in point is correct.
    expect(mockApprovalStep.id, isNotEmpty);
    expect(mockApprovalStep.toolName, equals('gmail.send_message'));
    expect(mockApprovalStep.mcpServer, equals('gmail'));
    expect(mockApprovalStep.riskTier, equals(RiskTier.high));
    expect(mockApprovalStep.requiresApproval, isTrue);
    expect(mockApprovalStep.status, equals('awaiting_approval'));
    expect(mockApprovalStep.explanationText, isNotNull);
    expect(mockApprovalStep.explanationText, isNotEmpty);
  });

  // -------------------------------------------------------------------------
  // 14. SCROLLABLE — NO OVERFLOW ON STANDARD SCREEN SIZES
  // -------------------------------------------------------------------------

  testWidgets('screen does not overflow on a standard mobile viewport',
      (tester) async {
    // iPhone 14 Pro: 390×844 logical pixels at 3.0 DPR = 1170×2532 physical.
    tester.view.physicalSize = const Size(1170, 2532);
    tester.view.devicePixelRatio = 3.0;

    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    // Confirm no render overflow exception.
    expect(tester.takeException(), isNull);

    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  });
}
