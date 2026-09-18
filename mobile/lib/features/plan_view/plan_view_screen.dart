import 'package:flutter/material.dart';

import '../../core/theme.dart';
import 'plan_service.dart';

/// Mock plan data mirrors the eventual task_plans + plan_steps response.
class MockPlan {
  const MockPlan({
    required this.id,
    required this.taskId,
    required this.plannerVersion,
    required this.status,
    required this.steps,
    this.planJson = const <String, dynamic>{},
  });

  final String id;
  final String taskId;
  final String plannerVersion;
  final String status;
  final Map<String, dynamic> planJson;
  final List<PlanStep> steps;
}

class PlanStep {
  const PlanStep({
    required this.id,
    required this.stepIndex,
    required this.toolName,
    required this.mcpServer,
    required this.riskTier,
    required this.requiresApproval,
    required this.status,
    this.inputParams = const <String, dynamic>{},
    this.output,
  });

  final String id;
  final int stepIndex;
  final String toolName;
  final String mcpServer;
  final RiskTier riskTier;
  final bool requiresApproval;
  final PlanStepStatus status;
  final Map<String, dynamic> inputParams;
  final Map<String, dynamic>? output;
}

enum PlanStepStatus {
  pending,
  awaitingApproval,
  approved,
  rejected,
  executing,
  done,
  failed,
}

extension PlanStepStatusPresentation on PlanStepStatus {
  String get label {
    switch (this) {
      case PlanStepStatus.pending:
        return 'PENDING';
      case PlanStepStatus.awaitingApproval:
        return 'AWAITING APPROVAL';
      case PlanStepStatus.approved:
        return 'APPROVED';
      case PlanStepStatus.rejected:
        return 'REJECTED';
      case PlanStepStatus.executing:
        return 'EXECUTING';
      case PlanStepStatus.done:
        return 'DONE';
      case PlanStepStatus.failed:
        return 'FAILED';
    }
  }

  Color get color {
    switch (this) {
      case PlanStepStatus.pending:
      case PlanStepStatus.approved:
        return AppColors.primary;
      case PlanStepStatus.awaitingApproval:
        return AppColors.riskMedium;
      case PlanStepStatus.rejected:
      case PlanStepStatus.failed:
        return AppColors.error;
      case PlanStepStatus.executing:
        return AppColors.info;
      case PlanStepStatus.done:
        return AppColors.success;
    }
  }

  Color get backgroundColor {
    switch (this) {
      case PlanStepStatus.pending:
      case PlanStepStatus.approved:
        return AppColors.primaryLight;
      case PlanStepStatus.awaitingApproval:
        return AppColors.riskMediumBg;
      case PlanStepStatus.rejected:
      case PlanStepStatus.failed:
        return AppColors.riskHighBg;
      case PlanStepStatus.executing:
        return const Color(0xFFE4F0FC);
      case PlanStepStatus.done:
        return AppColors.riskLowBg;
    }
  }

  IconData get icon {
    switch (this) {
      case PlanStepStatus.pending:
        return Icons.schedule_outlined;
      case PlanStepStatus.awaitingApproval:
        return Icons.gpp_maybe_outlined;
      case PlanStepStatus.approved:
        return Icons.thumb_up_alt_outlined;
      case PlanStepStatus.rejected:
        return Icons.block_outlined;
      case PlanStepStatus.executing:
        return Icons.sync;
      case PlanStepStatus.done:
        return Icons.check_circle_outline;
      case PlanStepStatus.failed:
        return Icons.error_outline;
    }
  }
}

const MockPlan mockPlan = MockPlan(
  id: 'plan-weekly-update',
  taskId: 'task-planning',
  plannerVersion: 'planner-v1-mock',
  status: 'active',
  steps: <PlanStep>[
    PlanStep(
      id: 'plan-step-calendar',
      stepIndex: 1,
      toolName: 'calendar.list_events',
      mcpServer: 'calendar',
      riskTier: RiskTier.low,
      requiresApproval: false,
      status: PlanStepStatus.done,
    ),
    PlanStep(
      id: 'plan-step-gmail',
      stepIndex: 2,
      toolName: 'gmail.search_messages',
      mcpServer: 'gmail',
      riskTier: RiskTier.medium,
      requiresApproval: false,
      status: PlanStepStatus.awaitingApproval,
    ),
    PlanStep(
      id: 'plan-step-draft',
      stepIndex: 3,
      toolName: 'gmail.create_draft',
      mcpServer: 'gmail',
      riskTier: RiskTier.high,
      requiresApproval: true,
      status: PlanStepStatus.pending,
    ),
  ],
);

class PlanViewScreen extends StatefulWidget {
  const PlanViewScreen({super.key, required this.taskId});

  final String taskId;

  @override
  State<PlanViewScreen> createState() => _PlanViewScreenState();
}

class _PlanViewScreenState extends State<PlanViewScreen> {
  MockPlan? _plan;
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _fetchPlan();
  }

  Future<void> _fetchPlan() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final plan = await PlanService.fetchPlan(widget.taskId);
      if (!mounted) return;
      setState(() {
        _plan = plan;
        _isLoading = false;
      });
    } on PlanNotFoundException catch (_) {
      if (!mounted) return;
      setState(() {
        _plan = null;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Agent Plan View')),
      body: SafeArea(
        child: _buildBody(context),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isLoading) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            CircularProgressIndicator(),
            SizedBox(height: AppSpacing.md),
            Text('Waking up backend...'),
          ],
        ),
      );
    }

    if (_errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              const Icon(Icons.error_outline, color: AppColors.error, size: AppSpacing.xxl),
              const SizedBox(height: AppSpacing.md),
              Text('Failed to load plan', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: AppSpacing.xs),
              Text(_errorMessage!, textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodyMedium),
              const SizedBox(height: AppSpacing.lg),
              ElevatedButton.icon(
                onPressed: _fetchPlan,
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    if (_plan == null) {
      return const Center(child: _EmptyPlanState());
    }

    final plan = _plan!;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.screenPadding),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Your copilot\'s plan', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Review the sequence before any action runs.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: AppSpacing.md),
          _PlanSummary(plan: plan),
          const SizedBox(height: AppSpacing.lg),
          if (plan.steps.isEmpty)
            const _EmptyPlanState()
          else
            ...plan.steps.asMap().entries.map(
                  (entry) => _PlanStepCard(
                    step: entry.value,
                    isLast: entry.key == plan.steps.length - 1,
                  ),
                ),
        ],
      ),
    );
  }
}

class _PlanSummary extends StatelessWidget {
  const _PlanSummary({required this.plan});
  final MockPlan plan;

  @override
  Widget build(BuildContext context) {
    return Card(
      key: const Key('plan-summary'),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: <Widget>[
            const Icon(Icons.account_tree_outlined,
                color: AppColors.primary, size: AppSpacing.xl),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text('Weekly team update',
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: AppSpacing.xs),
                  Text('${plan.steps.length} planned steps',
                      style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            _StatusChip(
              label: plan.status.toUpperCase(),
              color: AppColors.primary,
              backgroundColor: AppColors.primaryLight,
            ),
          ],
        ),
      ),
    );
  }
}

class _PlanStepCard extends StatelessWidget {
  const _PlanStepCard({required this.step, required this.isLast});
  final PlanStep step;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final status = step.status;
    return Semantics(
      label: 'Step ${step.stepIndex}: ${step.toolName}, '
          '${step.riskTier.label}, ${status.label}',
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: AppSpacing.xl,
            child: Column(
              children: <Widget>[
                CircleAvatar(
                  radius: AppSpacing.md,
                  backgroundColor: step.riskTier.background,
                  child: Text(
                    '${step.stepIndex}',
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                          color: step.riskTier.color,
                        ),
                  ),
                ),
                if (!isLast)
                  Container(
                    width: 2,
                    height: AppSpacing.xxl,
                    color: AppColors.neutral300,
                  ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Card(
              key: Key('plan-step-${step.id}'),
              margin: const EdgeInsets.only(bottom: AppSpacing.md),
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.md),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      step.toolName,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text('Integration: ${step.mcpServer}',
                        style: Theme.of(context).textTheme.bodyMedium),
                    const SizedBox(height: AppSpacing.sm),
                    Wrap(
                      spacing: AppSpacing.sm,
                      runSpacing: AppSpacing.xs,
                      children: <Widget>[
                        _StatusChip(
                          label: step.riskTier.label,
                          color: step.riskTier.color,
                          backgroundColor: step.riskTier.background,
                        ),
                        _StatusChip(
                          label: status.label,
                          color: status.color,
                          backgroundColor: status.backgroundColor,
                          icon: status.icon,
                        ),
                      ],
                    ),
                    if (status == PlanStepStatus.awaitingApproval) ...[
                      const SizedBox(height: AppSpacing.sm),
                      Text(
                        'This step gates the steps that follow.',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: AppColors.riskMedium,
                            ),
                      ),
                    ],
                    if (status == PlanStepStatus.failed) ...[
                      const SizedBox(height: AppSpacing.sm),
                      Text(
                        'Later steps may not run until this is resolved.',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: AppColors.error,
                            ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({
    required this.label,
    required this.color,
    required this.backgroundColor,
    this.icon,
  });

  final String label;
  final Color color;
  final Color backgroundColor;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (icon != null) ...[
            Icon(icon, size: AppSpacing.md, color: color),
            const SizedBox(width: AppSpacing.xs),
          ],
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: color,
                ),
          ),
        ],
      ),
    );
  }
}

class _EmptyPlanState extends StatelessWidget {
  const _EmptyPlanState();

  @override
  Widget build(BuildContext context) {
    return Card(
      key: const Key('empty-plan-state'),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          children: <Widget>[
            const Icon(Icons.account_tree_outlined,
                size: AppSpacing.xxl, color: AppColors.neutral500),
            const SizedBox(height: AppSpacing.md),
            Text('No steps planned yet',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: AppSpacing.xs),
            Text('Your copilot will show the plan here before it runs.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}
