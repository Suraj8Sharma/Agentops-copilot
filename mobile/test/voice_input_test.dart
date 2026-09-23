import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/home/home_screen.dart';
import 'package:agentops_copilot/features/home/task_service.dart';
import 'package:agentops_copilot/features/voice_input/voice_input_screen.dart';
import 'package:agentops_copilot/features/voice_input/voice_service.dart';

AppTask submittedVoiceTask(String transcript) => AppTask(
      id: 'task-voice-1',
      inputType: 'voice',
      rawInput: transcript,
      status: TaskStatus.submitted,
      createdAt: DateTime(2026, 9, 23),
    );

void main() {
  setUp(() {
    VoiceInputScreen.permissionOverride = () async => true;
    VoiceInputScreen.recordingOverride = () async => <int>[1, 2, 3, 4, 5];
    VoiceService.transcribeOverride = null;
    TaskService.createTaskOverride = null;
  });

  tearDown(() {
    VoiceInputScreen.permissionOverride = null;
    VoiceInputScreen.recordingOverride = null;
    VoiceService.transcribeOverride = null;
    TaskService.createTaskOverride = null;
  });

  Widget testApp() => MaterialApp(
        theme: AppTheme.light,
        home: const VoiceInputScreen(),
      );

  testWidgets('renders initial voice intake UI with mic button and title',
      (tester) async {
    await tester.pumpWidget(testApp());

    expect(find.text('Speak your task naturally'), findsOneWidget);
    expect(find.byKey(const Key('mic-record-button')), findsOneWidget);
    expect(find.byKey(const Key('switch-to-typed-input')), findsOneWidget);
    expect(find.text('Tap microphone to speak'), findsOneWidget);
  });

  testWidgets('handles recording start, stop, playback preview and transcribe flow',
      (tester) async {
    VoiceService.transcribeOverride = ({
      required audioBytes,
      required filename,
      languageHint,
    }) async {
      await Future<void>.delayed(const Duration(milliseconds: 50));
      return const TranscriptionResult(
        transcript: 'Schedule a sync meeting with Professor Rawat on Thursday at 3 PM',
        language: 'en',
        confidence: 0.95,
        durationSeconds: 3.2,
        processingTimeMs: 420,
        engine: 'faster-whisper-base',
      );
    };

    await tester.pumpWidget(testApp());

    // 1. Tap mic to start recording
    await tester.tap(find.byKey(const Key('mic-record-button')));
    await tester.pump();
    expect(find.text('Listening... Tap to finish'), findsOneWidget);

    // Simulate 2 seconds of recording
    await tester.pump(const Duration(seconds: 2));

    // 2. Tap mic again to stop recording
    await tester.tap(find.byKey(const Key('mic-record-button')));
    await tester.pump();

    expect(find.byKey(const Key('play-preview-button')), findsOneWidget);
    expect(find.byKey(const Key('cancel-audio-button')), findsOneWidget);
    expect(find.byKey(const Key('transcribe-button')), findsOneWidget);

    // 3. Tap transcribe button
    await tester.tap(find.byKey(const Key('transcribe-button')));
    await tester.pump();
    expect(find.text('Transcribing speech with faster-whisper...'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));

    // 4. Verify editable transcript field is populated
    expect(find.byKey(const Key('transcript-edit-field')), findsOneWidget);
    expect(
      find.text('Schedule a sync meeting with Professor Rawat on Thursday at 3 PM'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('confirm-task-button')), findsOneWidget);
  });

  testWidgets('allows editing recognized transcript and dispatches voice task',
      (tester) async {
    String? capturedInput;
    TaskService.createTaskOverride = (input) async {
      capturedInput = input;
      return submittedVoiceTask(input);
    };

    VoiceService.transcribeOverride = ({
      required audioBytes,
      required filename,
      languageHint,
    }) async {
      return const TranscriptionResult(
        transcript: 'Schedule a team meeting',
        language: 'en',
        confidence: 0.90,
        durationSeconds: 2.1,
        processingTimeMs: 310,
        engine: 'faster-whisper-base',
      );
    };

    await tester.pumpWidget(testApp());

    // Record and transcribe
    await tester.tap(find.byKey(const Key('mic-record-button')));
    await tester.pump(const Duration(seconds: 2));
    await tester.tap(find.byKey(const Key('mic-record-button')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('transcribe-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));

    // User edits transcript
    const editedText = 'Schedule a team meeting with Professor Rawat and email agenda';
    await tester.enterText(find.byKey(const Key('transcript-edit-field')), editedText);
    await tester.pump();

    // Confirm and send to planner
    await tester.ensureVisible(find.byKey(const Key('confirm-task-button')));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.byKey(const Key('confirm-task-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));

    expect(capturedInput, editedText);
    expect(find.text('Task Dispatched to Planner'), findsOneWidget);
  });

  testWidgets('surfaces transcription errors with retry capability', (tester) async {
    VoiceService.transcribeOverride = ({
      required audioBytes,
      required filename,
      languageHint,
    }) async {
      throw const VoiceTranscriptionException('Speech service timed out (HTTP 504)');
    };

    await tester.pumpWidget(testApp());

    await tester.tap(find.byKey(const Key('mic-record-button')));
    await tester.pump(const Duration(seconds: 2));
    await tester.tap(find.byKey(const Key('mic-record-button')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('transcribe-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('Speech service timed out (HTTP 504)'), findsOneWidget);
  });
}
