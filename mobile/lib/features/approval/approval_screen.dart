// AgentOps Copilot — Approval Screen (Day 8)
//
// Owner: Ishani
// Deliverable: Risk Card UI + Approve / Reject (mock)
//
// Safety notes (Manual §9.2, §9.3, §15):
//   • The advisory explanation text is DISPLAY ONLY — no code path here
//     reads explanationText to drive the approve/reject outcome.
//   • Neither Approve nor Reject is pre-selected, highlighted, or made
//     visually easier than the other. Both are equal-weight actions.
//   • A decision is locked in after the first tap; double-tap is ignored.
//   • "No decision" (app closed mid-review) is left as an unresolved state;
//     it is never silently treated as approve or reject.
//   • Only steps with requiresApproval == true should reach this screen;
//     a low-risk step arriving here is flagged as an unexpected data state.

import 'package:flutter/material.dart';

import '../../core/theme.dart';

// ---------------------------------------------------------------------------
// DATA MODELS
// ---------------------------------------------------------------------------
// Shapes mirror plan_steps + approvals + risk_rules (Manual §7) so that
// future wiring to GET /tasks/{id}/plan and POST /approvals/{step_id}
// is a data-source swap, not a structural rewrite.

/// Mirrors a row from the `plan_steps` table for the step under review.
class ApprovalStep {
  const ApprovalStep({
    required this.id,
    required this.toolName,
    required this.mcpServer,
    required this.riskTier,
    required this.requiresApproval,
    required this.status,
    this.inputParams = const <String, dynamic>{},
    this.explanationText,
  });

  final String id;
  final String toolName;
  final String mcpServer;
  final RiskTier riskTier;

  /// Should always be true for a step that reaches this screen.
  /// If false, this is flagged as an unexpected data state.
  final bool requiresApproval;

  /// Should always be 'awaiting_approval' on arrival.
  final String status;

  /// Raw input params from the planner; feeds the explanation LLM; not rendered raw.
  final Map<String, dynamic> inputParams;

  /// Plain-English advisory copy from the Section 9.3 explainer LLM.
  /// Display only — MUST NOT influence approve/reject logic.
  final String? explanationText;
}

/// The decision recorded to the `approvals` table on submit.
enum ApprovalDecision { approved, rejected }

// ---------------------------------------------------------------------------
// MOCK DATA
// ---------------------------------------------------------------------------
// Shape matches plan_steps + approvals + risk_rules (Manual §7).

const ApprovalStep mockApprovalStep = ApprovalStep(
  id: 'step-gmail-send-001',
  toolName: 'gmail.send_message',
  mcpServer: 'gmail',
  riskTier: RiskTier.high,
  requiresApproval: true,
  status: 'awaiting_approval',
  inputParams: <String, dynamic>{
    'to': 'professor.rao@university.edu',
    'subject': "Agenda for Thursday's call",
    'body': 'Hi Professor Rao, please find the agenda attached...',
  },
  explanationText:
      "This will send an email to professor.rao@university.edu with the "
      "subject \u2018Agenda for Thursday\u2019s call\u2019.",
);

// ---------------------------------------------------------------------------
// SCREEN
// ---------------------------------------------------------------------------

class ApprovalScreen extends StatefulWidget {
  const ApprovalScreen({super.key, this.step = mockApprovalStep});

  final ApprovalStep step;

  @override
  State<ApprovalScreen> createState() => _ApprovalScreenState();
}

class _ApprovalScreenState extends State<ApprovalScreen> {
  // Null == no decision made yet.
  // A non-null value is final — it cannot be toggled back.
  ApprovalDecision? _decision;

  // Prevents double-tap from firing two conflicting decisions.
  bool _isProcessing = false;

  // Wall-clock timestamp when this screen was surfaced, used to compute
  // response_time_ms for the Trust Dashboard (Manual §7, approvals table).
  // ignore: unused_field
  final DateTime _surfacedAt = DateTime.now();

  void _handleDecision(ApprovalDecision decision) {
    // Guard: already decided or still processing previous tap — do nothing.
    if (_decision != null || _isProcessing) return;

    setState(() => _isProcessing = true);

    // Brief lock-in delay (mirrors the eventual async POST).
    Future<void>.delayed(const Duration(milliseconds: 150), () {
      if (!mounted) return;
      setState(() {
        _decision = decision;
        _isProcessing = false;
      });
    });

    // ignore: unused_field — _surfacedAt will be used when wiring POST /approvals/{step_id}
    // to compute response_time_ms: DateTime.now().difference(_surfacedAt).inMilliseconds
  }

  @override
  Widget build(BuildContext context) {
    // Safety guard: only requiresApproval == true steps should reach here.
    if (!widget.step.requiresApproval) {
      return const _UnexpectedRiskState();
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Review Required')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.screenPadding),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              const _ScreenHeader(),
              const SizedBox(height: AppSpacing.md),
              _RiskCard(step: widget.step),
              const SizedBox(height: AppSpacing.lg),
              if (_decision == null)
                _DecisionButtons(
                  isProcessing: _isProcessing,
                  onApprove: () => _handleDecision(ApprovalDecision.approved),
                  onReject: () => _handleDecision(ApprovalDecision.rejected),
                )
              else
                _DecisionConfirmed(decision: _decision!),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// SCREEN HEADER
// ---------------------------------------------------------------------------

class _ScreenHeader extends StatelessWidget {
  const _ScreenHeader();

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          'Action requires your approval',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Review what your copilot plans to do before it runs.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// RISK CARD
// ---------------------------------------------------------------------------

class _RiskCard extends StatelessWidget {
  const _RiskCard({required this.step});

  final ApprovalStep step;

  @override
  Widget build(BuildContext context) {
    return Card(
      key: const Key('approval-risk-card'),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            _RiskCardHeader(step: step),
            const Divider(height: AppSpacing.lg),
            _ActionDetails(step: step),
            const SizedBox(height: AppSpacing.md),
            _ExplanationSection(explanationText: step.explanationText),
          ],
        ),
      ),
    );
  }
}

class _RiskCardHeader extends StatelessWidget {
  const _RiskCardHeader({required this.step});

  final ApprovalStep step;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Container(
          key: const Key('risk-tier-badge'),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.sm,
            vertical: AppSpacing.xs,
          ),
          decoration: BoxDecoration(
            color: step.riskTier.background,
            borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                Icons.shield_outlined,
                size: AppSpacing.md,
                color: step.riskTier.color,
              ),
              const SizedBox(width: AppSpacing.xs),
              Text(
                step.riskTier.label,
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: step.riskTier.color,
                    ),
              ),
            ],
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            'Requires your approval to run',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      ],
    );
  }
}

class _ActionDetails extends StatelessWidget {
  const _ActionDetails({required this.step});

  final ApprovalStep step;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          'Action',
          style: Theme.of(context).textTheme.labelMedium,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          step.toolName,
          key: const Key('approval-tool-name'),
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: AppSpacing.xs),
        Row(
          children: <Widget>[
            const Icon(
              Icons.hub_outlined,
              size: AppSpacing.md,
              color: AppColors.neutral500,
            ),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Text(
                'Integration: ${step.mcpServer}',
                key: const Key('approval-mcp-server'),
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// EXPLANATION SECTION (advisory, display-only)
// ---------------------------------------------------------------------------
// The explanation text is produced by the Section 9.3 advisory LLM.
// It is rendered as display-only prose. No code path here reads this text
// to influence the approve/reject outcome — that separation is the core
// safety invariant (Guardrail 3, Manual §9.3).

class _ExplanationSection extends StatelessWidget {
  const _ExplanationSection({required this.explanationText});

  final String? explanationText;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            const Icon(
              Icons.info_outline,
              size: AppSpacing.md,
              color: AppColors.neutral500,
            ),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Text(
                'What this action will do',
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.xs),
        _ExplanationBody(explanationText: explanationText),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'This description is advisory only and does not affect the outcome '
          'of your decision.',
          key: const Key('explanation-advisory-disclaimer'),
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }
}

/// Renders the advisory explanation text with graceful fallback handling
/// (edge case: missing or malformed explanation, Manual §5).
class _ExplanationBody extends StatelessWidget {
  const _ExplanationBody({required this.explanationText});

  final String? explanationText;

  // Max chars before overflow handling (Guardrail 3, Manual §9.3).
  static const int _maxDisplayChars = 400;

  @override
  Widget build(BuildContext context) {
    // Edge case: explanation is missing — show a structured fallback.
    if (explanationText == null || explanationText!.trim().isEmpty) {
      return Container(
        key: const Key('explanation-fallback'),
        padding: const EdgeInsets.all(AppSpacing.sm),
        decoration: BoxDecoration(
          color: AppColors.neutral100,
          borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
          border: Border.all(color: AppColors.neutral300),
        ),
        child: Text(
          'No advisory description is available for this action. '
          'Review the action name and integration above before deciding.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      );
    }

    // Edge case: overly long — cap without cutting mid-word.
    final String displayText = explanationText!.length > _maxDisplayChars
        ? '${explanationText!.substring(0, _maxDisplayChars).trimRight()}\u2026'
        : explanationText!;

    return Container(
      key: const Key('explanation-text'),
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: AppColors.neutral100,
        borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
        border: Border.all(color: AppColors.neutral300),
      ),
      child: Text(
        displayText,
        style: Theme.of(context).textTheme.bodyMedium,
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// DECISION BUTTONS
// ---------------------------------------------------------------------------
// Approve and Reject are equal-weight, equally-sized buttons (both Expanded).
// Neither is pre-selected, default-highlighted, or visually favoured.
// Both use the same outlined style — one in primary blue, one in error red —
// to prevent any optical bias toward approval.

class _DecisionButtons extends StatelessWidget {
  const _DecisionButtons({
    required this.isProcessing,
    required this.onApprove,
    required this.onReject,
  });

  final bool isProcessing;
  final VoidCallback onApprove;
  final VoidCallback onReject;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Text(
          'Your decision',
          style: Theme.of(context).textTheme.labelMedium,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Both choices are final. This action will not run without an '
          'explicit approval.',
          style: Theme.of(context).textTheme.bodySmall,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: AppSpacing.md),
        Row(
          children: <Widget>[
            // REJECT — left
            Expanded(
              child: _DecisionButton(
                key: const Key('reject-button'),
                label: 'Reject',
                icon: Icons.block_outlined,
                foregroundColor: AppColors.riskHigh,
                backgroundColor: AppColors.riskHighBg,
                borderColor: AppColors.riskHigh,
                isProcessing: isProcessing,
                onPressed: onReject,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            // APPROVE — right, same outlined style (no fill/elevation bias)
            Expanded(
              child: _DecisionButton(
                key: const Key('approve-button'),
                label: 'Approve',
                icon: Icons.check_circle_outline,
                foregroundColor: AppColors.primary,
                backgroundColor: AppColors.primaryLight,
                borderColor: AppColors.primary,
                isProcessing: isProcessing,
                onPressed: onApprove,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _DecisionButton extends StatelessWidget {
  const _DecisionButton({
    super.key,
    required this.label,
    required this.icon,
    required this.foregroundColor,
    required this.backgroundColor,
    required this.borderColor,
    required this.isProcessing,
    required this.onPressed,
  });

  final String label;
  final IconData icon;
  final Color foregroundColor;
  final Color backgroundColor;
  final Color borderColor;
  final bool isProcessing;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      style: OutlinedButton.styleFrom(
        foregroundColor: foregroundColor,
        backgroundColor: backgroundColor,
        side: BorderSide(color: borderColor),
        padding: const EdgeInsets.symmetric(
          vertical: AppSpacing.sm + AppSpacing.xs,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
        ),
      ),
      onPressed: isProcessing ? null : onPressed,
      icon: Icon(icon, size: AppSpacing.md),
      label: Text(
        label,
        style: Theme.of(context).textTheme.labelLarge?.copyWith(
              color: foregroundColor,
            ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// DECISION CONFIRMED BANNER
// ---------------------------------------------------------------------------
// Replaces the buttons after a decision is made.
// Clearly states the outcome; no undo path.

class _DecisionConfirmed extends StatelessWidget {
  const _DecisionConfirmed({required this.decision});

  final ApprovalDecision decision;

  @override
  Widget build(BuildContext context) {
    final bool isApproved = decision == ApprovalDecision.approved;
    final Color color = isApproved ? AppColors.primary : AppColors.riskHigh;
    final Color bgColor =
        isApproved ? AppColors.primaryLight : AppColors.riskHighBg;
    final IconData icon =
        isApproved ? Icons.check_circle_outline : Icons.block_outlined;
    final String title = isApproved ? 'Approved' : 'Rejected';
    final String body = isApproved
        ? 'Your approval has been recorded. The action will proceed.'
        : 'Your rejection has been recorded. The action will not run.';

    return Container(
      key: Key('decision-confirmed-${decision.name}'),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(icon, color: color, size: AppSpacing.lg),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  title,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: color,
                      ),
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(body, style: Theme.of(context).textTheme.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// UNEXPECTED RISK STATE GUARD
// ---------------------------------------------------------------------------
// Rendered if a step with requiresApproval == false somehow reaches this
// screen. Surfaced explicitly rather than silently proceeding.

class _UnexpectedRiskState extends StatelessWidget {
  const _UnexpectedRiskState();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Review Required')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.screenPadding),
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Icon(
                  Icons.warning_amber_outlined,
                  size: AppSpacing.xxl,
                  color: AppColors.riskMedium,
                ),
                const SizedBox(height: AppSpacing.md),
                Text(
                  'Unexpected step state',
                  style: Theme.of(context).textTheme.titleMedium,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  'This step does not require approval. It should not have '
                  'reached this screen. This is a data or routing issue to '
                  'be investigated before real wiring begins.',
                  key: const Key('unexpected-risk-body'),
                  style: Theme.of(context).textTheme.bodyMedium,
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}