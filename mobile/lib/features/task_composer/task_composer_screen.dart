import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/theme.dart';

/// Mock payload matching the eventual POST /tasks request.
class MockTaskSubmission {
  const MockTaskSubmission({
    required this.inputType,
    required this.rawInput,
    this.transcriptionText,
    required this.status,
  });

  final String inputType;
  final String rawInput;
  final String? transcriptionText;
  final String status;
}

enum _SubmissionState { idle, submitting, submitted, failure }

class TaskComposerScreen extends StatefulWidget {
  const TaskComposerScreen({super.key});

  @override
  State<TaskComposerScreen> createState() => _TaskComposerScreenState();
}

class _TaskComposerScreenState extends State<TaskComposerScreen> {
  static const Duration _mockSubmissionDuration = Duration(milliseconds: 500);

  final TextEditingController _textController = TextEditingController();
  Timer? _submissionTimer;
  _SubmissionState _submissionState = _SubmissionState.idle;
  String? _validationMessage;
  MockTaskSubmission? _submittedTask;

  @override
  void dispose() {
    _submissionTimer?.cancel();
    _textController.dispose();
    super.dispose();
  }

  void _submit() {
    final input = _textController.text.trim();
    if (input.isEmpty) {
      setState(
          () => _validationMessage = 'Tell your copilot what to do first.');
      return;
    }
    if (_submissionState == _SubmissionState.submitting) return;

    setState(() {
      _validationMessage = null;
      _submissionState = _SubmissionState.submitting;
    });
    _submissionTimer?.cancel();
    _submissionTimer = Timer(_mockSubmissionDuration, () {
      if (!mounted) return;
      setState(() {
        _submissionState = _SubmissionState.submitted;
        _submittedTask = MockTaskSubmission(
          inputType: 'text',
          rawInput: input,
          status: 'submitted',
        );
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isSubmitting = _submissionState == _SubmissionState.submitting;

    return Scaffold(
      appBar: AppBar(title: const Text('Create a task')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.screenPadding),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('What should your copilot do?',
                  style: theme.textTheme.headlineMedium),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Describe the task in your own words. You will review anything risky before it runs.',
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: AppSpacing.lg),
              TextField(
                key: const Key('task-input'),
                controller: _textController,
                enabled: !isSubmitting,
                minLines: 4,
                maxLines: 8,
                keyboardType: TextInputType.multiline,
                textInputAction: TextInputAction.newline,
                onChanged: (_) {
                  if (_validationMessage != null) {
                    setState(() => _validationMessage = null);
                  }
                },
                decoration: InputDecoration(
                  labelText: 'Task request',
                  hintText:
                      'For example: Find a time for a team sync next week',
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
                      ? const SizedBox(
                          width: AppSpacing.md,
                          height: AppSpacing.md,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.send_outlined),
                  label: Text(isSubmitting ? 'Submitting...' : 'Submit task'),
                ),
              ),
              const SizedBox(height: AppSpacing.sm),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  key: const Key('voice-mode-placeholder'),
                  onPressed: null,
                  icon: const Icon(Icons.mic_none_outlined),
                  label: const Text('Voice mode coming soon'),
                ),
              ),
              const SizedBox(height: AppSpacing.lg),
              _SubmissionFeedback(
                state: _submissionState,
                task: _submittedTask,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SubmissionFeedback extends StatelessWidget {
  const _SubmissionFeedback({required this.state, this.task});

  final _SubmissionState state;
  final MockTaskSubmission? task;

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
        ? 'Your copilot is getting things ready.'
        : isFailure
            ? 'Please try again when the service is available.'
            : 'It will appear in your task list with a submitted status.';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            isSubmitting
                ? Icons.hourglass_top_outlined
                : isFailure
                    ? Icons.error_outline
                    : Icons.check_circle_outline,
            color: color,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: AppSpacing.xs),
                Text(detail, style: Theme.of(context).textTheme.bodyMedium),
                if (task != null) ...<Widget>[
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    task!.rawInput,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
