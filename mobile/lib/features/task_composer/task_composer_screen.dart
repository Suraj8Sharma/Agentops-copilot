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
  final TextEditingController _textController = TextEditingController();
  _SubmissionState _submissionState = _SubmissionState.idle;
  String? _validationMessage;
  String? _submissionError;
  String? _submittedTaskText;
  AppTask? _lastCreatedTask;

  @override
  void initState() {
    super.initState();
    _textController.addListener(_onTextChanged);
  }

  void _onTextChanged() {
    if (mounted) setState(() {});
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
      setState(() => _validationMessage = 'Tell your copilot what to do first.');
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
        _lastCreatedTask = task;
      });
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
        _submissionError = 'Could not reach the service. Check your connection and try again.';
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
        _lastCreatedTask = task;
      });
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
        _submissionError = 'Could not reach the service. Check your connection and try again.';
        _submissionState = _SubmissionState.failure;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isSubmitting = _submissionState == _SubmissionState.submitting;
    return PopScope(
      canPop: _textController.text.trim().isEmpty || _submissionState == _SubmissionState.submitted,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        final shouldDiscard = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Discard draft?'),
            content: const Text('You have unsent text. Are you sure you want to discard it?'),
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
        appBar: AppBar(title: const Text('Create a task')),
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.screenPadding),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('What should your copilot do?', style: theme.textTheme.headlineMedium),
                const SizedBox(height: AppSpacing.xs),
                Text('Describe the task in your own words. You will review anything risky before it runs.', style: theme.textTheme.bodyMedium),
                const SizedBox(height: AppSpacing.lg),
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
                    hintText: 'For example: Find a time for a team sync next week',
                    errorText: _validationMessage,
                    alignLabelWithHint: true,
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    key: const Key('submit-task'),
                    onPressed: isSubmitting ? null : _submit,
                    icon: isSubmitting
                        ? const SizedBox(width: AppSpacing.md, height: AppSpacing.md, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.send_outlined),
                    label: Text(isSubmitting ? 'Submitting...' : 'Submit task'),
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                SizedBox(
                  width: double.infinity,
                  child: widget.voiceModeEnabled
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
                ),
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
    final background = isFailure ? AppColors.riskHighBg : AppColors.primaryLight;
    final title = isSubmitting ? 'Submitting your task' : isFailure ? 'Task could not be submitted' : 'Task submitted';
    final detail = isSubmitting ? 'The service may take a moment to wake up. Please keep this screen open.' : isFailure ? (error ?? 'Please try again when the service is available.') : 'It will appear in your task list with a submitted status.';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(AppSpacing.cardRadius)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
            Icon(isSubmitting ? Icons.hourglass_top_outlined : isFailure ? Icons.error_outline : Icons.check_circle_outline, color: color),
            const SizedBox(width: AppSpacing.sm),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: <Widget>[
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: AppSpacing.xs),
              Text(detail, style: Theme.of(context).textTheme.bodyMedium),
              if (taskText != null) ...<Widget>[
                const SizedBox(height: AppSpacing.sm),
                Text(key: const Key('submitted-task-text'), taskText!, maxLines: 3, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodySmall),
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
                  Navigator.of(context).pushNamed(AppRoutes.planView, arguments: taskId);
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
