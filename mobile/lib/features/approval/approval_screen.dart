import 'package:flutter/material.dart';

import '../../core/router.dart';
import '../../core/theme.dart';
export 'approval_models.dart';
import 'approval_models.dart';
import 'approval_service.dart';
import '../plan_view/plan_service.dart';
import '../plan_view/plan_view_screen.dart';

const ApprovalStep mockApprovalStep = ApprovalStep(
  id: 'step-gmail-send-001',
  toolName: 'gmail.send_message',
  mcpServer: 'gmail',
  riskTier: RiskTier.high,
  requiresApproval: true,
  status: 'awaiting_approval',
  explanationText:
      "This will send an email to professor.rao@university.edu with the subject 'Agenda for Thursday's call'.",
);

class ApprovalScreen extends StatefulWidget {
  const ApprovalScreen({super.key, this.step});
  final ApprovalStep? step;

  @override
  State<ApprovalScreen> createState() => _ApprovalScreenState();
}

class _ApprovalScreenState extends State<ApprovalScreen> {
  List<ApprovalStep> _pending = <ApprovalStep>[];
  final Map<String, MockPlan> _plans = <String, MockPlan>{};
  final Set<String> _processing = <String>{};
  String? _errorMessage;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    if (widget.step != null) {
      _pending = <ApprovalStep>[widget.step!];
      _fetchPlansForPending();
    } else {
      _fetchPending();
    }
  }

  Future<void> _fetchPending() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final pending = await ApprovalService.fetchPending();
      if (!mounted) return;
      setState(() {
        _pending = pending;
      });
      await _fetchPlansForPending();
    } on ApprovalServiceException catch (error) {
      if (!mounted) return;
      if (error.requiresSignIn) {
        Navigator.of(context).pushNamed(AppRoutes.signIn);
      } else {
        setState(() {
          _errorMessage = error.message;
          _isLoading = false;
        });
      }
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _errorMessage =
            'Could not load approvals. Check your connection and try again.';
        _isLoading = false;
      });
    }
  }

  Future<void> _fetchPlansForPending() async {
    try {
      final taskIds = _pending.map((e) => e.taskId).where((id) => id.isNotEmpty).toSet();
      for (final taskId in taskIds) {
        if (!_plans.containsKey(taskId)) {
          final plan = await PlanService.fetchPlan(taskId);
          _plans[taskId] = plan;
        }
      }
    } catch (e) {
      // If fetching plan fails, we can fallback to just showing the pending step
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _decide(ApprovalStep step, ApprovalDecision decision) async {
    if (_processing.contains(step.id)) return;
    setState(() => _processing.add(step.id));
    try {
      await ApprovalService.decide(step.id, decision);
      if (!mounted) return;
      setState(() {
        _processing.remove(step.id);
        
        // Optimistically update the step in the plan so the UI reflects it
        if (_plans.containsKey(step.taskId)) {
          final plan = _plans[step.taskId]!;
          final updatedSteps = plan.steps.map((s) {
            if (s.id == step.id) {
              return PlanStep(
                id: s.id,
                stepIndex: s.stepIndex,
                toolName: s.toolName,
                mcpServer: s.mcpServer,
                riskTier: s.riskTier,
                requiresApproval: s.requiresApproval,
                status: decision == ApprovalDecision.approved ? PlanStepStatus.approved : PlanStepStatus.rejected,
                inputParams: s.inputParams,
                output: s.output,
              );
            }
            return s;
          }).toList();
          _plans[step.taskId] = MockPlan(
            id: plan.id,
            taskId: plan.taskId,
            plannerVersion: plan.plannerVersion,
            status: plan.status,
            steps: updatedSteps,
            planJson: plan.planJson,
          );
        } else {
          // If no plan context, remove from pending
          _pending.removeWhere((item) => item.id == step.id);
        }
      });
    } on ApprovalServiceException catch (error) {
      if (!mounted) return;
      setState(() {
        _processing.remove(step.id);
        _errorMessage = error.message;
      });
      if (error.requiresSignIn) {
        Navigator.of(context).pushNamed(AppRoutes.signIn);
      } else if (error.refreshPending) {
        await _fetchPending();
      }
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _processing.remove(step.id);
        _errorMessage = 'An error occurred while saving your decision.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Approvals')),
      body: SafeArea(child: _buildBody(context)),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isLoading) {
      return const Center(
        key: Key('approval-loading'),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            CircularProgressIndicator(),
            SizedBox(height: AppSpacing.md),
            Text('Loading approvals...'),
          ],
        ),
      );
    }
    if (_errorMessage != null && _pending.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Icon(Icons.error_outline,
                  color: AppColors.error, size: AppSpacing.xxl),
              const SizedBox(height: AppSpacing.md),
              Text('Approval service unavailable',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: AppSpacing.xs),
              Text(_errorMessage!, textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.md),
              ElevatedButton(
                onPressed: _fetchPending,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }
    if (_pending.isEmpty) {
      return const Center(
        key: Key('approval-empty'),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.inbox_outlined,
                size: AppSpacing.xxl, color: AppColors.neutral500),
            SizedBox(height: AppSpacing.md),
            Text('Nothing waiting on you right now'),
          ],
        ),
      );
    }
    return ListView(
      key: const Key('approval-pending-list'),
      padding: const EdgeInsets.all(AppSpacing.screenPadding),
      children: <Widget>[
        const _ScreenHeader(),
        if (_errorMessage != null) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          _DecisionErrorBanner(message: _errorMessage!),
        ],
        const SizedBox(height: AppSpacing.md),
        for (final step in _pending) ...<Widget>[
          if (_plans.containsKey(step.taskId))
            _buildPlanContext(context, step, _plans[step.taskId]!)
          else
            _buildFallbackCard(context, step),
          const SizedBox(height: AppSpacing.lg),
        ],
      ],
    );
  }

  Widget _buildPlanContext(BuildContext context, ApprovalStep pendingStep, MockPlan plan) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        PlanSummary(plan: plan),
        const SizedBox(height: AppSpacing.md),
        ...plan.steps.asMap().entries.map((entry) {
          final pStep = entry.value;
          final isLast = entry.key == plan.steps.length - 1;
          return Column(
            children: [
              PlanStepCard(step: pStep, isLast: isLast),
              if (pStep.id == pendingStep.id &&
                  pStep.status == PlanStepStatus.awaitingApproval &&
                  pendingStep.status == 'awaiting_approval') ...[
                const SizedBox(height: AppSpacing.sm),
                _buildApprovalControls(context, pendingStep),
                const SizedBox(height: AppSpacing.md),
              ],
            ],
          );
        }),
      ],
    );
  }

  Widget _buildFallbackCard(BuildContext context, ApprovalStep step) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (step.requiresApproval)
          _RiskCard(step: step)
        else
          const _UnexpectedRiskState(),
        if (step.requiresApproval && step.status == 'awaiting_approval') ...<Widget>[
          const SizedBox(height: AppSpacing.md),
          _DecisionButtons(
            isProcessing: _processing.contains(step.id),
            approveKey: Key('approve-button-${step.id}'),
            rejectKey: Key('reject-button-${step.id}'),
            onApprove: () => _decide(step, ApprovalDecision.approved),
            onReject: () => _decide(step, ApprovalDecision.rejected),
          ),
        ],
      ],
    );
  }

  Widget _buildApprovalControls(BuildContext context, ApprovalStep step) {
    return Card(
      color: AppColors.riskMediumBg,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Requires your approval to run',
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: AppSpacing.sm),
            Text('What this action will do',
                style: Theme.of(context).textTheme.labelMedium),
            const SizedBox(height: AppSpacing.xs),
            _Explanation(explanationText: step.explanationText),
            const SizedBox(height: AppSpacing.xs),
            Text(
                'This description is advisory only and does not affect the outcome of your decision.',
                key: const Key('explanation-advisory-disclaimer'),
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: AppSpacing.md),
            _DecisionButtons(
              isProcessing: _processing.contains(step.id),
              approveKey: Key('approve-button-${step.id}'),
              rejectKey: Key('reject-button-${step.id}'),
              onApprove: () => _decide(step, ApprovalDecision.approved),
              onReject: () => _decide(step, ApprovalDecision.rejected),
            ),
          ],
        ),
      ),
    );
  }
}

class _ScreenHeader extends StatelessWidget {
  const _ScreenHeader();
  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Action requires your approval',
              style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: AppSpacing.xs),
          Text('Review what your copilot plans to do before it runs.',
              style: Theme.of(context).textTheme.bodyMedium),
        ],
      );
}

class _DecisionErrorBanner extends StatelessWidget {
  const _DecisionErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Card(
        key: const Key('approval-decision-error'),
        color: AppColors.riskHighBg,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.sm),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Icon(Icons.error_outline, color: AppColors.error),
              const SizedBox(width: AppSpacing.sm),
              Expanded(child: Text(message)),
            ],
          ),
        ),
      );
}

class _RiskCard extends StatelessWidget {
  const _RiskCard({required this.step});
  final ApprovalStep step;
  @override
  Widget build(BuildContext context) => Card(
        key: const Key('approval-risk-card'),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Container(
                    key: const Key('risk-tier-badge'),
                    padding: const EdgeInsets.symmetric(
                        horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
                    decoration: BoxDecoration(
                        color: step.riskTier.background,
                        borderRadius:
                            BorderRadius.circular(AppSpacing.buttonRadius)),
                    child: Text(
                      step.riskTier.label,
                      style: Theme.of(context)
                          .textTheme
                          .labelMedium
                          ?.copyWith(color: step.riskTier.color),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text('Requires your approval to run',
                        style: Theme.of(context).textTheme.bodySmall),
                  ),
                ],
              ),
              const Divider(height: AppSpacing.lg),
              Text('Action', style: Theme.of(context).textTheme.labelMedium),
              const SizedBox(height: AppSpacing.xs),
              Text(step.toolName,
                  key: const Key('approval-tool-name'),
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: AppSpacing.xs),
              Text('Integration: ${step.mcpServer}',
                  key: const Key('approval-mcp-server'),
                  style: Theme.of(context).textTheme.bodyMedium),
              const SizedBox(height: AppSpacing.md),
              Text('What this action will do',
                  style: Theme.of(context).textTheme.labelMedium),
              const SizedBox(height: AppSpacing.xs),
              _Explanation(explanationText: step.explanationText),
              const SizedBox(height: AppSpacing.xs),
              Text(
                  'This description is advisory only and does not affect the outcome of your decision.',
                  key: const Key('explanation-advisory-disclaimer'),
                  style: Theme.of(context).textTheme.bodySmall),
              // FR-AP SS5.2 - structured params alongside explanation (fail-closed):
              if (step.inputParams.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.sm),
                Text('Parameters',
                    key: const Key('approval-input-params-label'),
                    style: Theme.of(context).textTheme.labelMedium),
                const SizedBox(height: AppSpacing.xs),
                ...step.inputParams.entries.map(
                  (e) => Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.xs),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${e.key}: ',
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600)),
                        Expanded(
                          child: Text(
                            e.value.toString(),
                            key: Key('approval-param-${e.key}'),
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      );
}

class _Explanation extends StatelessWidget {
  const _Explanation({this.explanationText});
  final String? explanationText;
  @override
  Widget build(BuildContext context) {
    if (explanationText == null || explanationText!.isEmpty) {
      return const Text('No explanation available.',
          key: Key('explanation-fallback'));
    }
    return Text(explanationText!,
        key: const Key('explanation-text'),
        style: Theme.of(context).textTheme.bodyMedium);
  }
}

class _DecisionButtons extends StatelessWidget {
  const _DecisionButtons({
    required this.isProcessing,
    required this.approveKey,
    required this.rejectKey,
    required this.onApprove,
    required this.onReject,
  });
  final bool isProcessing;
  final Key approveKey;
  final Key rejectKey;
  final VoidCallback onApprove;
  final VoidCallback onReject;
  @override
  Widget build(BuildContext context) => Column(
        children: <Widget>[
          if (isProcessing)
            const Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.sm),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  CircularProgressIndicator(strokeWidth: 2),
                  SizedBox(width: AppSpacing.sm),
                  Text('Recording decision...')
                ],
              ),
            ),
          Row(
            children: <Widget>[
              Expanded(
                child: OutlinedButton.icon(
                  key: rejectKey,
                  onPressed: isProcessing ? null : onReject,
                  icon: const Icon(Icons.block_outlined),
                  label: const Text('Reject'),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: OutlinedButton.icon(
                  key: approveKey,
                  onPressed: isProcessing ? null : onApprove,
                  icon: const Icon(Icons.check_circle_outline),
                  label: const Text('Approve'),
                ),
              ),
            ],
          ),
        ],
      );
}

class _UnexpectedRiskState extends StatelessWidget {
  const _UnexpectedRiskState();
  @override
  Widget build(BuildContext context) => Container(
        key: const Key('unexpected-risk-body'),
        padding: const EdgeInsets.all(AppSpacing.md),
        color: AppColors.riskMediumBg,
        child: const Text(
            'Unexpected step state: this step does not require approval.'),
      );
}
