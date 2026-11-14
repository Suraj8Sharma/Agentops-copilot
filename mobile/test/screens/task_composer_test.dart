// AgentOps Copilot — Task Composer Screen widget tests.
// Owner: Ishani (Frontend Design Lead & Trust Surfaces)
// Spec: Day 26 (A7, Gate 3, §15.2) — render & interaction coverage for Task Composer.

import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/home/home_screen.dart';
import 'package:agentops_copilot/features/home/task_service.dart';
import 'package:agentops_copilot/features/task_composer/task_composer_screen.dart';

AppTask mockTaskResult(String input,
    {String inputType = 'text', String? transcription}) {
  return AppTask(
    id: 'task-new-123',
    inputType: inputType,
    rawInput: input,
    transcriptionText: transcription,
    status: TaskStatus.submitted,
    createdAt: DateTime(2026, 9, 22, 10, 30),
  );
}

void main() {
  setUp(() {
    TaskService.fetchTasksOverride = () async => <AppTask>[];
  });

  tearDown(() {
    TaskService.createTaskOverride = null;
    TaskService.createVoiceTaskOverride = null;
    TaskService.fetchTasksOverride = null;
    TaskService.accessTokenProvider = null;
    TaskService.refreshAccessTokenProvider = null;
  });

  Widget composerApp({
    bool voiceModeEnabled = true,
    bool navigateOnSuccess = false,
    String? voiceResultToReturn,
  }) {
    return MaterialApp(
      theme: AppTheme.light,
      initialRoute: AppRoutes.taskComposer,
      onGenerateRoute: (settings) {
        if (settings.name == AppRoutes.taskComposer) {
          return MaterialPageRoute(
            builder: (_) => TaskComposerScreen(
              voiceModeEnabled: voiceModeEnabled,
              navigateOnSuccess: navigateOnSuccess,
            ),
          );
        }
        if (settings.name == AppRoutes.voiceInput) {
          return MaterialPageRoute(
            settings: settings,
            builder: (context) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  key: const Key('return-voice-result'),
                  onPressed: () =>
                      Navigator.of(context).pop(voiceResultToReturn),
                  child: const Text('Return Voice Result'),
                ),
              ),
            ),
          );
        }
        return MaterialPageRoute(
          settings: settings,
          builder: (_) => Scaffold(
            body: Center(
              child:
                  Text('Route: ${settings.name}, Args: ${settings.arguments}'),
            ),
          ),
        );
      },
    );
  }

  // FR-TC-1: Text-entry mode with enabled submit and voice switch affordance.
  testWidgets('test_composer_renders_text_mode', (tester) async {
    await tester.pumpWidget(composerApp());

    expect(find.text('What can I help you get done?'), findsOneWidget);
    expect(find.byKey(const Key('task-composer-card')), findsOneWidget);
    expect(find.byKey(const Key('task-input')), findsOneWidget);
    expect(find.byKey(const Key('submit-task')), findsOneWidget);
    expect(find.text('Submit task'), findsOneWidget);
    expect(find.byKey(const Key('switch-to-voice-mode')), findsOneWidget);
    expect(find.text('Switch to voice mode'), findsOneWidget);
  });

  testWidgets('wide composer shows task history beside the centered composer',
      (tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    TaskService.fetchTasksOverride = () async => <AppTask>[
          AppTask(
            id: 'history-task-1',
            inputType: 'text',
            rawInput: 'Summarize last week',
            status: TaskStatus.completed,
            createdAt: DateTime(2026, 9, 22, 10, 30),
          ),
        ];

    await tester.pumpWidget(composerApp());
    await tester.pumpAndSettle();

    expect(find.text('Task history'), findsOneWidget);
    expect(find.text('Summarize last week'), findsOneWidget);
    expect(find.byKey(const Key('task-history-item-history-task-1')),
        findsOneWidget);
    expect(find.byKey(const Key('task-input')), findsOneWidget);

    await tester.enterText(
      find.byKey(const Key('task-input')),
      'An unsent draft',
    );
    await tester.tap(find.byKey(const Key('new-task-button')));
    await tester.pumpAndSettle();
    expect(find.text('Discard draft?'), findsOneWidget);
    await tester.tap(find.byKey(const Key('keep-draft-button')));
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('task-input')))
          .controller!
          .text,
      'An unsent draft',
    );

    await tester.tap(find.byKey(const Key('task-history-item-history-task-1')));
    await tester.pumpAndSettle();
    expect(
        find.text('Route: /plan-view, Args: history-task-1'), findsOneWidget);
  });

  testWidgets('narrow composer opens task history from the app bar',
      (tester) async {
    await tester.pumpWidget(composerApp());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('open-task-history')), findsOneWidget);
    await tester.tap(find.byKey(const Key('open-task-history')));
    await tester.pumpAndSettle();

    expect(find.text('Task history'), findsOneWidget);
    expect(find.byKey(const Key('new-task-button')), findsOneWidget);
  });

  // FR-TC-2: Blocks empty or whitespace-only input without submitting.
  testWidgets('test_composer_blocks_empty_submit', (tester) async {
    var callCount = 0;
    TaskService.createTaskOverride = (input) async {
      callCount++;
      return mockTaskResult(input);
    };

    await tester.pumpWidget(composerApp());

    // Tap submit while empty
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pump();

    expect(find.text('Tell your copilot what to do first.'), findsOneWidget);
    expect(callCount, 0);

    // Enter only whitespace
    await tester.enterText(find.byKey(const Key('task-input')), '   \n  \t  ');
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pump();

    expect(find.text('Tell your copilot what to do first.'), findsOneWidget);
    expect(callCount, 0);
  });

  // FR-TC-3: Valid text input submitted with input_type: "text", shows submitting state.
  testWidgets('test_composer_submits_text_task', (tester) async {
    final completer = Completer<AppTask>();
    String? submittedText;

    TaskService.createTaskOverride = (input) {
      submittedText = input;
      return completer.future;
    };

    await tester.pumpWidget(composerApp());

    const taskText = 'Schedule daily standup for 10am tomorrow';
    await tester.enterText(find.byKey(const Key('task-input')), taskText);
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pump();

    // Verify submitting state
    expect(find.text('Submitting...'), findsOneWidget);
    expect(find.text('Submitting your task'), findsOneWidget);
    expect(submittedText, taskText);

    completer.complete(mockTaskResult(taskText));
    await tester.pumpAndSettle();

    expect(find.text('Task submitted'), findsOneWidget);
  });

  // FR-TC-4: On success, navigates onward with the returned task id.
  testWidgets('test_composer_success_navigates_with_task_id', (tester) async {
    TaskService.createTaskOverride = (input) async => mockTaskResult(input);

    // Test with navigateOnSuccess: true
    await tester.pumpWidget(composerApp(navigateOnSuccess: true));

    await tester.enterText(
        find.byKey(const Key('task-input')), 'Deploy to staging');
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pumpAndSettle();

    expect(find.text('Route: /plan-view, Args: task-new-123'), findsOneWidget);
  });

  // FR-TC-5: Voice mode hands off to Voice Input screen and submits transcription as voice task.
  testWidgets('test_composer_voice_mode_submits_transcription', (tester) async {
    const voiceText = 'Summarize yesterday meetings';
    String? submittedTranscription;

    TaskService.createVoiceTaskOverride = (transcription) async {
      submittedTranscription = transcription;
      return mockTaskResult('',
          inputType: 'voice', transcription: transcription);
    };

    await tester.pumpWidget(composerApp(
      voiceResultToReturn: voiceText,
      navigateOnSuccess: true,
    ));

    // Tap voice mode button to open voice input screen
    await tester.tap(find.byKey(const Key('switch-to-voice-mode')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('return-voice-result')), findsOneWidget);

    // Return transcription from voice screen
    await tester.tap(find.byKey(const Key('return-voice-result')));
    await tester.pumpAndSettle();

    expect(submittedTranscription, voiceText);
    expect(find.text('Route: /plan-view, Args: task-new-123'), findsOneWidget);
  });

  // FR-TC-6: A failed submission shows an error, keeps typed text, and allows retry.
  testWidgets('test_composer_error_preserves_input_and_allows_retry',
      (tester) async {
    var callCount = 0;
    const taskInput = 'Review pull request #42';

    TaskService.createTaskOverride = (input) async {
      callCount++;
      if (callCount == 1) {
        throw const TaskServiceException('Network failure. Please retry.');
      }
      return mockTaskResult(input);
    };

    await tester.pumpWidget(composerApp());

    await tester.enterText(find.byKey(const Key('task-input')), taskInput);
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pumpAndSettle();

    // Verify error shown and input preserved
    expect(find.text('Task could not be submitted'), findsOneWidget);
    expect(find.text('Network failure. Please retry.'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('task-input')))
          .controller!
          .text,
      taskInput,
    );

    // Retry submit
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pumpAndSettle();

    expect(callCount, 2);
    expect(find.text('Task submitted'), findsOneWidget);
  });

  // FR-TC-7: Double-tapping submit sends exactly one request.
  testWidgets('test_composer_double_tap_submits_once', (tester) async {
    final completer = Completer<AppTask>();
    var calls = 0;

    TaskService.createTaskOverride = (input) {
      calls++;
      return completer.future;
    };

    await tester.pumpWidget(composerApp());

    await tester.enterText(
        find.byKey(const Key('task-input')), 'Single submission test');
    // Rapid double-tap
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pump();

    expect(calls, 1);
    expect(find.text('Submitting...'), findsOneWidget);

    completer.complete(mockTaskResult('Single submission test'));
    await tester.pumpAndSettle();
  });

  // Edge Case §5.3: 429 rate limit shows friendly message and preserves text.
  testWidgets('test_composer_rate_limited_shows_retry_message', (tester) async {
    const userInput = 'Generate end of quarter summary';
    TaskService.createTaskOverride = (input) async {
      throw const TaskServiceException(
          'Rate limit reached. Please wait a moment and try again.');
    };

    await tester.pumpWidget(composerApp());

    await tester.enterText(find.byKey(const Key('task-input')), userInput);
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pumpAndSettle();

    expect(
      find.text('Rate limit reached. Please wait a moment and try again.'),
      findsOneWidget,
    );
    expect(
      tester
          .widget<TextField>(find.byKey(const Key('task-input')))
          .controller!
          .text,
      userInput,
    );
  });

  // Edge Case §5.3: 401 mid-submit triggers auth handoff to Sign In without losing input.
  testWidgets('test_composer_401_triggers_auth_handoff', (tester) async {
    const userInput = 'Unauthenticated submission';
    TaskService.createTaskOverride = (input) async {
      throw const TaskServiceException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
      );
    };

    await tester.pumpWidget(composerApp());

    await tester.enterText(find.byKey(const Key('task-input')), userInput);
    await tester.tap(find.byKey(const Key('submit-task')));
    await tester.pumpAndSettle();

    expect(find.text('Route: /sign-in, Args: null'), findsOneWidget);
  });

  // Edge Case §5.3: Voice empty/denied returns user to text mode with clear message; no submit.
  testWidgets('test_composer_voice_empty_transcription_not_submitted',
      (tester) async {
    var voiceCalls = 0;
    TaskService.createVoiceTaskOverride = (transcription) async {
      voiceCalls++;
      return mockTaskResult(transcription);
    };

    // Return empty string from voice input screen
    await tester.pumpWidget(composerApp(voiceResultToReturn: '   '));

    await tester.tap(find.byKey(const Key('switch-to-voice-mode')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('return-voice-result')));
    await tester.pumpAndSettle();

    expect(voiceCalls, 0);
    expect(find.text('Voice input was empty or cancelled.'), findsOneWidget);
    expect(find.byKey(const Key('task-input')), findsOneWidget);
  });

  // Edge Case §5.3: Long input respects max length limit.
  testWidgets('test_composer_long_input_handling', (tester) async {
    await tester.pumpWidget(composerApp());

    final textField =
        tester.widget<TextField>(find.byKey(const Key('task-input')));
    expect(textField.maxLength, 5000);
  });

  // Edge Case §5.3: Back navigation with unsent text prompts confirmation dialog.
  testWidgets('test_composer_back_with_draft', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: ElevatedButton(
              key: const Key('open-composer-button'),
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const TaskComposerScreen()),
                );
              },
              child: const Text('Open Composer'),
            ),
          ),
        ),
      ),
    ));

    // Open composer
    await tester.tap(find.byKey(const Key('open-composer-button')));
    await tester.pumpAndSettle();
    expect(find.byType(TaskComposerScreen), findsOneWidget);

    // Type draft text
    await tester.enterText(
        find.byKey(const Key('task-input')), 'Unsaved draft text');
    await tester.pump();

    // Trigger back pop
    final navigator = tester.state<NavigatorState>(find.byType(Navigator));
    navigator.maybePop();
    await tester.pumpAndSettle();

    // Discard draft confirmation dialog appears
    expect(find.text('Discard draft?'), findsOneWidget);
    expect(
        find.text('You have unsent text. Are you sure you want to discard it?'),
        findsOneWidget);

    // Tap Keep Editing -> stay on screen
    await tester.tap(find.byKey(const Key('keep-draft-button')));
    await tester.pumpAndSettle();
    expect(find.byType(TaskComposerScreen), findsOneWidget);

    // Trigger back pop again
    navigator.maybePop();
    await tester.pumpAndSettle();

    // Tap Discard -> pops screen
    await tester.tap(find.byKey(const Key('discard-draft-button')));
    await tester.pumpAndSettle();
    expect(find.byType(TaskComposerScreen), findsNothing);
  });
}
