import 'package:flutter/material.dart';

import '../../core/router.dart';
import '../../core/theme.dart';

/// Task data mirrors the fields needed by the future GET /tasks response.
class MockTask {
  const MockTask({
    required this.id,
    required this.inputType,
    required this.rawInput,
    required this.status,
    required this.createdAt,
    this.transcriptionText,
    this.completedAt,
  });

  final String id;
  final String inputType;
  final String rawInput;
  final String? transcriptionText;
  final TaskStatus status;
  final DateTime createdAt;
  final DateTime? completedAt;
}

enum TaskStatus {
  submitted,
  planning,
  awaitingApproval,
  executing,
  completed,
  failed,
  cancelled,
}

extension TaskStatusPresentation on TaskStatus {
  String get label {
    switch (this) {
      case TaskStatus.submitted:
        return 'SUBMITTED';
      case TaskStatus.planning:
        return 'PLANNING';
      case TaskStatus.awaitingApproval:
        return 'AWAITING APPROVAL';
      case TaskStatus.executing:
        return 'EXECUTING';
      case TaskStatus.completed:
        return 'COMPLETED';
      case TaskStatus.failed:
        return 'FAILED';
      case TaskStatus.cancelled:
        return 'CANCELLED';
    }
  }

  Color get color {
    switch (this) {
      case TaskStatus.submitted:
      case TaskStatus.planning:
      case TaskStatus.executing:
        return AppColors.primary;
      case TaskStatus.awaitingApproval:
        return AppColors.riskMedium;
      case TaskStatus.completed:
        return AppColors.success;
      case TaskStatus.failed:
        return AppColors.error;
      case TaskStatus.cancelled:
        return AppColors.neutral500;
    }
  }

  Color get backgroundColor {
    switch (this) {
      case TaskStatus.submitted:
      case TaskStatus.planning:
      case TaskStatus.executing:
        return AppColors.primaryLight;
      case TaskStatus.awaitingApproval:
        return AppColors.riskMediumBg;
      case TaskStatus.completed:
        return AppColors.riskLowBg;
      case TaskStatus.failed:
        return AppColors.riskHighBg;
      case TaskStatus.cancelled:
        return AppColors.neutral100;
    }
  }

  IconData get icon {
    switch (this) {
      case TaskStatus.submitted:
        return Icons.inbox_outlined;
      case TaskStatus.planning:
        return Icons.account_tree_outlined;
      case TaskStatus.awaitingApproval:
        return Icons.gpp_maybe_outlined;
      case TaskStatus.executing:
        return Icons.sync;
      case TaskStatus.completed:
        return Icons.check_circle_outline;
      case TaskStatus.failed:
        return Icons.error_outline;
      case TaskStatus.cancelled:
        return Icons.cancel_outlined;
    }
  }
}

final List<MockTask> mockTasks = <MockTask>[
  MockTask(
    id: 'task-submitted',
    inputType: 'text',
    rawInput: 'Find the latest project brief and summarize it',
    status: TaskStatus.submitted,
    createdAt: DateTime(2026, 8, 27, 9, 0),
  ),
  MockTask(
    id: 'task-planning',
    inputType: 'text',
    rawInput: 'Prepare a weekly team update from my calendar',
    status: TaskStatus.planning,
    createdAt: DateTime(2026, 8, 27, 8, 45),
  ),
  MockTask(
    id: 'task-awaiting-approval',
    inputType: 'text',
    rawInput: 'Send the revised launch plan to the team',
    status: TaskStatus.awaitingApproval,
    createdAt: DateTime(2026, 8, 27, 8, 30),
  ),
  MockTask(
    id: 'task-executing',
    inputType: 'voice',
    rawInput: '',
    transcriptionText: 'Create an issue for the onboarding bug',
    status: TaskStatus.executing,
    createdAt: DateTime(2026, 8, 27, 8, 15),
  ),
  MockTask(
    id: 'task-completed',
    inputType: 'text',
    rawInput: 'Add the design review to my calendar',
    status: TaskStatus.completed,
    createdAt: DateTime(2026, 8, 26, 16, 0),
    completedAt: DateTime(2026, 8, 26, 16, 2),
  ),
  MockTask(
    id: 'task-failed',
    inputType: 'text',
    rawInput: 'Find an available room for tomorrow',
    status: TaskStatus.failed,
    createdAt: DateTime(2026, 8, 26, 15, 30),
  ),
  MockTask(
    id: 'task-cancelled',
    inputType: 'text',
    rawInput: 'Draft a reply to the vendor email',
    status: TaskStatus.cancelled,
    createdAt: DateTime(2026, 8, 26, 14, 0),
  ),
];

class HomeScreen extends StatelessWidget {
  HomeScreen({super.key, List<MockTask>? tasks}) : tasks = tasks ?? mockTasks;

  final List<MockTask> tasks;

  void _openTaskComposer(BuildContext context) {
    Navigator.of(context).pushNamed(AppRoutes.taskComposer);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Home')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.screenPadding),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('Your tasks',
                  style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'See what your copilot is working on.',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: AppSpacing.md),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: () => _openTaskComposer(context),
                  icon: const Icon(Icons.add),
                  label: const Text('Create a task'),
                ),
              ),
              const SizedBox(height: AppSpacing.lg),
              Expanded(
                child: tasks.isEmpty
                    ? const _EmptyTaskState()
                    : ListView.separated(
                        key: const Key('home-task-list'),
                        itemCount: tasks.length,
                        separatorBuilder: (_, __) =>
                            const SizedBox(height: AppSpacing.sm),
                        itemBuilder: (context, index) =>
                            _TaskTile(task: tasks[index]),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TaskTile extends StatelessWidget {
  const _TaskTile({required this.task});
  final MockTask task;

  String get displayInput => task.rawInput.isNotEmpty
      ? task.rawInput
      : (task.transcriptionText ?? 'Voice task');

  @override
  Widget build(BuildContext context) {
    final status = task.status;
    return Card(
      key: Key(task.id),
      child: InkWell(
        onTap: () => Navigator.of(context).pushNamed(AppRoutes.planView),
        borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Icon(status.icon, color: status.color),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(displayInput,
                        style: Theme.of(context).textTheme.bodyLarge),
                    const SizedBox(height: AppSpacing.sm),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.sm,
                          vertical: AppSpacing.xs,
                        ),
                        decoration: BoxDecoration(
                          color: status.backgroundColor,
                          borderRadius:
                              BorderRadius.circular(AppSpacing.buttonRadius),
                        ),
                        child: Text(
                          status.label,
                          style: Theme.of(context)
                              .textTheme
                              .labelMedium
                              ?.copyWith(color: status.color),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyTaskState extends StatelessWidget {
  const _EmptyTaskState();

  @override
  Widget build(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const Icon(Icons.inbox_outlined,
                size: AppSpacing.xxl, color: AppColors.neutral500),
            const SizedBox(height: AppSpacing.md),
            Text('No tasks yet', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Create a task and your copilot will keep you posted here.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      );
}
