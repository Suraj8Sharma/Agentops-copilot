import 'package:flutter/material.dart';

import '../../core/router.dart';
import '../../core/theme.dart';
import '../home/home_screen.dart';
import '../home/task_service.dart';

class TaskComposerRouteArgs {
  const TaskComposerRouteArgs({this.onTaskSubmitted});
  final VoidCallback? onTaskSubmitted;
}

enum _SubmissionState { idle, submitting, submitted, failure }

class TaskComposerScreen extends StatefulWidget {
  const TaskComposerScreen({
    super.key,
    this.onTaskSubmitted,
    this.voiceModeEnabled = true,
    this.navigateOnSuccess = false,
  });

  final VoidCallback? onTaskSubmitted;
  final bool voiceModeEnabled;
  final bool navigateOnSuccess;

  @override
  State<TaskComposerScreen> createState() => _TaskComposerScreenState();
}

class _TaskComposerScreenState extends State<TaskComposerScreen> {
  static const double _wideLayoutBreakpoint = 960;
  static const double _historyPanelWidth = 280;
  static const double _composerMaxWidth = 760;

  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  final TextEditingController _textController = TextEditingController();
  List<AppTask> _taskHistory = <AppTask>[];
  _SubmissionState _submissionState = _SubmissionState.idle;
  String? _validationMessage;
  String? _submissionError;
  String? _submittedTaskText;
  String? _historyError;
  AppTask? _lastCreatedTask;
  bool _historyLoading = true;
  int _historyRequestId = 0;

  @override
  void initState() {
    super.initState();
    _textController.addListener(_onTextChanged);
    _loadTaskHistory();
  }

  void _onTextChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _loadTaskHistory() async {
    final requestId = ++_historyRequestId;
    setState(() {
      _historyLoading = true;
      _historyError = null;
    });
    try {
      final tasks = await TaskService.fetchTasks();
      if (!mounted || requestId != _historyRequestId) return;
      setState(() {
        _taskHistory = _sortTasks(tasks);
        _historyLoading = false;
      });
    } on TaskServiceException catch (error) {
      if (!mounted || requestId != _historyRequestId) return;
      setState(() {
        _historyError = error.message;
        _historyLoading = false;
      });
      if (error.requiresSignIn) {
        Navigator.of(context).pushNamed(AppRoutes.signIn);
      }
    } catch (_) {
      if (!mounted || requestId != _historyRequestId) return;
      setState(() {
        _historyError =
            'Could not load task history. Check your connection and try again.';
        _historyLoading = false;
      });
    }
  }

  List<AppTask> _sortTasks(Iterable<AppTask> tasks) {
    final sorted = tasks.toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return sorted;
  }

  void _rememberTask(AppTask task) {
    setState(() {
      _lastCreatedTask = task;
      _taskHistory = _sortTasks(<AppTask>[
        task,
        ..._taskHistory.where((existing) => existing.id != task.id),
      ]);
    });
  }

  Future<void> _startNewTask() async {
    if (_textController.text.trim().isNotEmpty &&
        _submissionState != _SubmissionState.submitted) {
      final discardDraft = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Discard draft?'),
          content: const Text(
            'You have unsent text. Are you sure you want to discard it?',
          ),
          actions: <Widget>[
            TextButton(
              key: const Key('keep-draft-button'),
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Keep Editing'),
            ),
            TextButton(
              key: const Key('discard-draft-button'),
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Discard'),
            ),
          ],
        ),
      );
      if (discardDraft != true || !mounted) return;
    }

    _textController.clear();
    setState(() {
      _validationMessage = null;
      _submissionError = null;
      _submittedTaskText = null;
      _lastCreatedTask = null;
      _submissionState = _SubmissionState.idle;
    });
    _scaffoldKey.currentState?.closeDrawer();
  }

  void _openTask(AppTask task) {
    _scaffoldKey.currentState?.closeDrawer();
    Navigator.of(context).pushNamed(AppRoutes.planView, arguments: task.id);
  }

  @override
  void dispose() {
    _textController.removeListener(_onTextChanged);
    _textController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final rawInput = _textController.text;
    if (rawInput.trim().isEmpty) {
      setState(
          () => _validationMessage = 'Tell your copilot what to do first.');
      return;
    }
    if (_submissionState == _SubmissionState.submitting) return;

    setState(() {
      _validationMessage = null;
      _submissionError = null;
      _submissionState = _SubmissionState.submitting;
    });

    try {
      final task = await TaskService.createTextTask(rawInput);
      if (!mounted) return;
      setState(() {
        _submittedTaskText = task.rawInput;
        _submissionState = _SubmissionState.submitted;
      });
      _rememberTask(task);
      widget.onTaskSubmitted?.call();
      if (widget.navigateOnSuccess) {
        Navigator.of(context).pushNamed(AppRoutes.planView, arguments: task.id);
      }
    } on TaskServiceException catch (error) {
      if (!mounted) return;
      setState(() {
        _submissionError = error.message;
        _submissionState = _SubmissionState.failure;
      });
      if (error.requiresSignIn) {
        Navigator.of(context).pushNamed(AppRoutes.signIn);
      }
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _submissionError =
            'Could not reach the service. Check your connection and try again.';
        _submissionState = _SubmissionState.failure;
      });
    }
  }

  Future<void> _openVoiceMode() async {
    final result = await Navigator.of(context).pushNamed(AppRoutes.voiceInput);
    if (!mounted) return;
    if (result is String && result.trim().isNotEmpty) {
      await _submitVoice(result.trim());
    } else {
      setState(() {
        _submissionError = 'Voice input was empty or cancelled.';
        _submissionState = _SubmissionState.failure;
      });
    }
  }

  Future<void> _submitVoice(String transcription) async {
    if (_submissionState == _SubmissionState.submitting) return;

    setState(() {
      _validationMessage = null;
      _submissionError = null;
      _submissionState = _SubmissionState.submitting;
    });

    try {
      final task = await TaskService.createVoiceTask(transcription);
      if (!mounted) return;
      setState(() {
        _submittedTaskText = task.transcriptionText ?? transcription;
        _submissionState = _SubmissionState.submitted;
      });
      _rememberTask(task);
      widget.onTaskSubmitted?.call();
      if (widget.navigateOnSuccess) {
        Navigator.of(context).pushNamed(AppRoutes.planView, arguments: task.id);
      }
    } on TaskServiceException catch (error) {
      if (!mounted) return;
      setState(() {
        _submissionError = error.message;
        _submissionState = _SubmissionState.failure;
      });
      if (error.requiresSignIn) {
        Navigator.of(context).pushNamed(AppRoutes.signIn);
      }
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _submissionError =
            'Could not reach the service. Check your connection and try again.';
        _submissionState = _SubmissionState.failure;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isSubmitting = _submissionState == _SubmissionState.submitting;
    final isWideLayout =
        MediaQuery.sizeOf(context).width >= _wideLayoutBreakpoint;
    return PopScope(
      canPop: _textController.text.trim().isEmpty ||
          _submissionState == _SubmissionState.submitted,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        final shouldDiscard = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Discard draft?'),
            content: const Text(
                'You have unsent text. Are you sure you want to discard it?'),
            actions: [
              TextButton(
                key: const Key('keep-draft-button'),
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('Keep Editing'),
              ),
              TextButton(
                key: const Key('discard-draft-button'),
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Discard'),
              ),
            ],
          ),
        );
        if (shouldDiscard == true && context.mounted) {
          Navigator.of(context).pop();
        }
      },
      child: Scaffold(
        key: _scaffoldKey,
        appBar: AppBar(
          leading: isWideLayout
              ? null
              : IconButton(
                  key: const Key('open-task-history'),
                  tooltip: 'Open task history',
                  onPressed: () => _scaffoldKey.currentState?.openDrawer(),
                  icon: const Icon(Icons.menu),
                ),
          title: const Text('AgentOps Copilot'),
          actions: <Widget>[
            IconButton(
              key: const Key('refresh-task-history'),
              tooltip: 'Refresh task history',
              onPressed: _loadTaskHistory,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        drawer: isWideLayout
            ? null
            : Drawer(
                child: SafeArea(
                  child: _buildTaskHistoryPanel(),
                ),
              ),
        body: SafeArea(
          child: Row(
            children: <Widget>[
              if (isWideLayout) ...<Widget>[
                SizedBox(
                  width: _historyPanelWidth,
                  child: _buildTaskHistoryPanel(),
                ),
                const VerticalDivider(width: 1, thickness: 1),
              ],
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) => SingleChildScrollView(
                    child: ConstrainedBox(
                      constraints:
                          BoxConstraints(minHeight: constraints.maxHeight),
                      child: Center(
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(
                            maxWidth: _composerMaxWidth,
                          ),
                          child: Padding(
                            padding: const EdgeInsets.all(AppSpacing.xl),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: <Widget>[
                                Text(
                                  'What can I help you get done?',
                                  textAlign: TextAlign.center,
                                  style: theme.textTheme.headlineMedium,
                                ),
                                const SizedBox(height: AppSpacing.xs),
                                Text(
                                  'Describe a task. You will review anything risky before it runs.',
                                  textAlign: TextAlign.center,
                                  style: theme.textTheme.bodyMedium,
                                ),
                                const SizedBox(height: AppSpacing.lg),
                                _buildComposer(isSubmitting),
                                const SizedBox(height: AppSpacing.lg),
                                _SubmissionFeedback(
                                  state: _submissionState,
                                  taskText: _submittedTaskText,
                                  taskId: _lastCreatedTask?.id,
                                  error: _submissionError,
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildComposer(bool isSubmitting) {
    return Card(
      key: const Key('task-composer-card'),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            TextField(
              key: const Key('task-input'),
              controller: _textController,
              enabled: !isSubmitting,
              minLines: 4,
              maxLines: 8,
              maxLength: 5000,
              keyboardType: TextInputType.multiline,
              textInputAction: TextInputAction.newline,
              onChanged: (_) {
                if (_validationMessage != null || _submissionError != null) {
                  setState(() {
                    _validationMessage = null;
                    _submissionError = null;
                    if (_submissionState == _SubmissionState.failure) {
                      _submissionState = _SubmissionState.idle;
                    }
                  });
                }
              },
              decoration: InputDecoration(
                labelText: 'Task request',
                hintText:
                    'Ask AgentOps to coordinate, research, or take an action…',
                errorText: _validationMessage,
                alignLabelWithHint: true,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                filled: false,
                counterText: '',
              ),
            ),
            const Divider(height: AppSpacing.lg),
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: <Widget>[
                widget.voiceModeEnabled
                    ? OutlinedButton.icon(
                        key: const Key('switch-to-voice-mode'),
                        onPressed: isSubmitting ? null : _openVoiceMode,
                        icon: const Icon(Icons.mic_none_outlined),
                        label: const Text('Switch to voice mode'),
                      )
                    : OutlinedButton.icon(
                        key: const Key('voice-mode-placeholder'),
                        onPressed: null,
                        icon: const Icon(Icons.mic_none_outlined),
                        label: const Text('Voice mode coming soon'),
                      ),
                ElevatedButton.icon(
                  key: const Key('submit-task'),
                  onPressed: isSubmitting ? null : _submit,
                  icon: isSubmitting
                      ? const SizedBox(
                          width: AppSpacing.md,
                          height: AppSpacing.md,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.arrow_upward),
                  label: Text(isSubmitting ? 'Submitting...' : 'Submit task'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTaskHistoryPanel() {
    return Container(
      color: AppColors.neutral100,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          ElevatedButton.icon(
            key: const Key('new-task-button'),
            onPressed: _startNewTask,
            icon: const Icon(Icons.add),
            label: const Text('New task'),
          ),
          const SizedBox(height: AppSpacing.lg),
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  'Task history',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              if (_historyLoading)
                const SizedBox(
                  key: Key('task-history-loading'),
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Expanded(child: _buildTaskHistoryList()),
        ],
      ),
    );
  }

  Widget _buildTaskHistoryList() {
    if (_historyLoading && _taskHistory.isEmpty) {
      return const Center(
        child: Text('Loading recent tasks…'),
      );
    }
    if (_historyError != null && _taskHistory.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              _historyError!,
              key: const Key('task-history-error'),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.sm),
            TextButton(
              onPressed: _loadTaskHistory,
              child: const Text('Try again'),
            ),
          ],
        ),
      );
    }
    if (_taskHistory.isEmpty) {
      return Center(
        child: Text(
          'Your recent tasks will appear here.',
          key: const Key('task-history-empty'),
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodySmall,
        ),
      );
    }

    return ListView.separated(
      key: const Key('task-history-list'),
      itemCount: _taskHistory.length,
      separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.xs),
      itemBuilder: (context, index) {
        final task = _taskHistory[index];
        final label = task.rawInput.isNotEmpty
            ? task.rawInput
            : (task.transcriptionText ?? 'Voice task');
        return Material(
          color: AppColors.neutral0,
          borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
          child: InkWell(
            key: Key('task-history-item-${task.id}'),
            borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
            onTap: () => _openTask(task),
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.sm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    label,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    task.status.label,
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                          color: task.status.color,
                        ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _SubmissionFeedback extends StatelessWidget {
  const _SubmissionFeedback({
    required this.state,
    this.taskText,
    this.taskId,
    this.error,
  });

  final _SubmissionState state;
  final String? taskText;
  final String? taskId;
  final String? error;

  @override
  Widget build(BuildContext context) {
    if (state == _SubmissionState.idle) return const SizedBox.shrink();
    final isSubmitting = state == _SubmissionState.submitting;
    final isFailure = state == _SubmissionState.failure;
    final color = isFailure ? AppColors.error : AppColors.primary;
    final background =
        isFailure ? AppColors.riskHighBg : AppColors.primaryLight;
    final title = isSubmitting
        ? 'Submitting your task'
        : isFailure
            ? 'Task could not be submitted'
            : 'Task submitted';
    final detail = isSubmitting
        ? 'The service may take a moment to wake up. Please keep this screen open.'
        : isFailure
            ? (error ?? 'Please try again when the service is available.')
            : 'It will appear in your task list with a submitted status.';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(AppSpacing.cardRadius)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
            Icon(
                isSubmitting
                    ? Icons.hourglass_top_outlined
                    : isFailure
                        ? Icons.error_outline
                        : Icons.check_circle_outline,
                color: color),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                  Text(title, style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: AppSpacing.xs),
                  Text(detail, style: Theme.of(context).textTheme.bodyMedium),
                  if (taskText != null) ...<Widget>[
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                        key: const Key('submitted-task-text'),
                        taskText!,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodySmall),
                  ],
                ])),
          ]),
          if (state == _SubmissionState.submitted && taskId != null) ...[
            const SizedBox(height: AppSpacing.md),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                key: const Key('view-plan-button'),
                onPressed: () {
                  Navigator.of(context)
                      .pushNamed(AppRoutes.planView, arguments: taskId);
                },
                icon: const Icon(Icons.arrow_forward),
                label: const Text('View Plan'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
