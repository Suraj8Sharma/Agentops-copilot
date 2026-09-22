import 'package:flutter/material.dart';

import '../../core/router.dart';
import '../../core/theme.dart';
import '../task_composer/task_composer_screen.dart';
import 'task_service.dart';

class AppTask {
  const AppTask({
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

  factory AppTask.fromJson(Map<String, dynamic> json) {
    TaskStatus parseStatus(String s) {
      switch (s) {
        case 'submitted':
          return TaskStatus.submitted;
        case 'planning':
          return TaskStatus.planning;
        case 'awaiting_approval':
          return TaskStatus.awaitingApproval;
        case 'executing':
          return TaskStatus.executing;
        case 'completed':
          return TaskStatus.completed;
        case 'failed':
          return TaskStatus.failed;
        case 'cancelled':
          return TaskStatus.cancelled;
        default:
          return TaskStatus.submitted;
      }
    }

    return AppTask(
      id: json['id'] as String,
      inputType: json['input_type'] as String,
      rawInput: json['raw_input'] as String? ?? '',
      transcriptionText: json['transcription_text'] as String?,
      status: parseStatus(json['status'] as String),
      createdAt: DateTime.parse(json['created_at'] as String),
      completedAt: json['completed_at'] != null
          ? DateTime.parse(json['completed_at'] as String)
          : null,
    );
  }
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

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<List<AppTask>> _tasksFuture;

  @override
  void initState() {
    super.initState();
    _fetchData();
  }

  void _fetchData() {
    setState(() {
      _tasksFuture = TaskService.fetchTasks();
    });
  }

  void _openTaskComposer(BuildContext context) {
    Navigator.of(context).pushNamed(
      AppRoutes.taskComposer,
      arguments: TaskComposerRouteArgs(onTaskSubmitted: _fetchData),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Home')),
      drawer: Drawer(
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            const DrawerHeader(
              decoration: BoxDecoration(
                color: AppColors.primary,
              ),
              child: Text(
                'AgentOps Copilot',
                style: TextStyle(color: AppColors.neutral0, fontSize: 24),
              ),
            ),
            ListTile(
              leading: const Icon(Icons.home),
              title: const Text('Home'),
              onTap: () => Navigator.pop(context),
            ),
            ListTile(
              leading: const Icon(Icons.link),
              title: const Text('OAuth Connections'),
              onTap: () {
                Navigator.pop(context);
                Navigator.pushNamed(context, AppRoutes.oauthConnections);
              },
            ),
            ListTile(
              leading: const Icon(Icons.security),
              title: const Text('Trust Dashboard'),
              onTap: () {
                Navigator.pop(context);
                Navigator.pushNamed(context, AppRoutes.trustDashboard);
              },
            ),
            ListTile(
              leading: const Icon(Icons.settings),
              title: const Text('Settings'),
              onTap: () {
                Navigator.pop(context);
                Navigator.pushNamed(context, AppRoutes.settings);
              },
            ),
            ListTile(
              leading: const Icon(Icons.list_alt),
              title: const Text('Activity Log'),
              onTap: () {
                Navigator.pop(context);
                Navigator.pushNamed(context, AppRoutes.activityLog);
              },
            ),
          ],
        ),
      ),
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
                child: FutureBuilder<List<AppTask>>(
                  future: _tasksFuture,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const CircularProgressIndicator(),
                            const SizedBox(height: AppSpacing.md),
                            Text(
                              'Waking up backend...',
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                          ],
                        ),
                      );
                    } else if (snapshot.hasError) {
                      return Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.error_outline,
                                size: AppSpacing.xxl, color: AppColors.error),
                            const SizedBox(height: AppSpacing.md),
                            Text('Failed to load tasks',
                                style: Theme.of(context).textTheme.titleLarge),
                            const SizedBox(height: AppSpacing.xs),
                            Text(
                              snapshot.error.toString(),
                              textAlign: TextAlign.center,
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                            const SizedBox(height: AppSpacing.md),
                            ElevatedButton(
                              onPressed: _fetchData,
                              child: const Text('Retry'),
                            ),
                          ],
                        ),
                      );
                    } else if (!snapshot.hasData || snapshot.data!.isEmpty) {
                      return const _EmptyTaskState();
                    }

                    final tasks = snapshot.data!;
                    return RefreshIndicator(
                      onRefresh: () async {
                        _fetchData();
                        await _tasksFuture;
                      },
                      child: ListView.separated(
                        key: const Key('home-task-list'),
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: tasks.length,
                        separatorBuilder: (_, __) =>
                            const SizedBox(height: AppSpacing.sm),
                        itemBuilder: (context, index) =>
                            _TaskTile(task: tasks[index]),
                      ),
                    );
                  },
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
  final AppTask task;

  String get displayInput => task.rawInput.isNotEmpty
      ? task.rawInput
      : (task.transcriptionText ?? 'Voice task');

  @override
  Widget build(BuildContext context) {
    final status = task.status;
    return Card(
      key: Key(task.id),
      child: InkWell(
        onTap: () => Navigator.of(context).pushNamed(AppRoutes.planView, arguments: task.id),
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
