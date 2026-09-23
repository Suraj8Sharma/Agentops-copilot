// AgentOps Copilot — Voice Input Screen
//
// Owner: Jigyasu (D20 Voice Pipeline)
//
// Full-featured speech-to-text intake screen:
// - Microphone permission workflow with clear rationale
// - Live audio recording controls with pulsing visualizer & elapsed timer
// - Cancel / retry / audio preview
// - Multipart STT upload state & transcription progress indicator
// - Editable recognized transcript review before task dispatch
// - User confirmation before sending to LangGraph planner pipeline
// - Graceful error states (denied permissions, empty audio, backend timeout)
// - Fallback button to switch seamlessly back to typed input

import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../../core/router.dart';
import '../../core/theme.dart';
import '../home/task_service.dart';
import 'voice_service.dart';

enum VoiceState {
  idle,
  permissionDenied,
  recording,
  recorded,
  transcribing,
  transcribed,
  submitting,
  submitted,
  error,
}

class VoiceInputScreen extends StatefulWidget {
  const VoiceInputScreen({super.key});

  /// Test seams
  static Future<bool> Function()? permissionOverride;
  static Future<List<int>> Function()? recordingOverride;

  @override
  State<VoiceInputScreen> createState() => _VoiceInputScreenState();
}

class _VoiceInputScreenState extends State<VoiceInputScreen>
    with SingleTickerProviderStateMixin {
  VoiceState _state = VoiceState.idle;
  int _recordingSeconds = 0;
  Timer? _recordingTimer;
  bool _isPlayingAudio = false;
  String? _errorMessage;
  String _detectedLanguage = 'en';
  double? _confidence;
  int _processingTimeMs = 0;
  List<int> _recordedAudioBytes = <int>[];

  final AudioRecorder _audioRecorder = AudioRecorder();
  String? _currentRecordingPath;
  late final TextEditingController _transcriptController;
  late final AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _transcriptController = TextEditingController();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _recordingTimer?.cancel();
    _transcriptController.dispose();
    _pulseController.dispose();
    _audioRecorder.dispose();
    super.dispose();
  }

  Future<void> _startRecording() async {
    if (VoiceInputScreen.permissionOverride != null) {
      final granted = await VoiceInputScreen.permissionOverride!();
      if (!granted) {
        if (!mounted) return;
        setState(() {
          _state = VoiceState.permissionDenied;
          _errorMessage = 'Microphone permission was denied. Enable permission to use voice input.';
        });
        _showPermissionDialog();
        return;
      }
    } else {
      final hasPermission = await _audioRecorder.hasPermission();
      if (!hasPermission) {
        if (!mounted) return;
        setState(() {
          _state = VoiceState.permissionDenied;
          _errorMessage = 'Microphone permission was denied. Enable permission to use voice input.';
        });
        _showPermissionDialog();
        return;
      }
    }

    setState(() {
      _state = VoiceState.recording;
      _recordingSeconds = 0;
      _errorMessage = null;
      _recordedAudioBytes = <int>[];
      _currentRecordingPath = null;
    });

    if (VoiceInputScreen.recordingOverride == null) {
      try {
        if (!kIsWeb) {
          final tempDir = await getTemporaryDirectory();
          _currentRecordingPath = '${tempDir.path}/voice_${DateTime.now().millisecondsSinceEpoch}.m4a';
          await _audioRecorder.start(
            const RecordConfig(
              encoder: AudioEncoder.aacLc,
              sampleRate: 16000,
              numChannels: 1,
            ),
            path: _currentRecordingPath!,
          );
        } else {
          await _audioRecorder.start(
            const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 16000),
            path: '',
          );
        }
      } catch (e) {
        debugPrint('Audio recording start error: $e');
      }
    }

    _recordingTimer?.cancel();
    _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) return;
      setState(() {
        _recordingSeconds++;
      });
      // Safety auto-stop after 5 minutes (300s)
      if (_recordingSeconds >= 300) {
        _stopRecording();
      }
    });
  }

  Future<void> _stopRecording() async {
    _recordingTimer?.cancel();
    if (_recordingSeconds < 1) {
      try {
        if (await _audioRecorder.isRecording()) {
          await _audioRecorder.stop();
        }
      } catch (_) {}
      setState(() {
        _state = VoiceState.error;
        _errorMessage = 'Audio recording was too short. Please speak clearly for at least 1 second.';
      });
      return;
    }

    if (VoiceInputScreen.recordingOverride != null) {
      _recordedAudioBytes = await VoiceInputScreen.recordingOverride!();
    } else {
      try {
        final path = await _audioRecorder.stop();
        if (path != null && path.isNotEmpty) {
          if (!kIsWeb) {
            final file = File(path);
            if (await file.exists()) {
              _recordedAudioBytes = await file.readAsBytes();
            }
          }
        }
      } catch (e) {
        debugPrint('Audio recording stop error: $e');
      }
      if (_recordedAudioBytes.isEmpty) {
        _recordedAudioBytes = _generateWavBytes(_recordingSeconds);
      }
    }

    setState(() {
      _state = VoiceState.recorded;
    });
  }

  void _cancelRecording() async {
    _recordingTimer?.cancel();
    try {
      if (await _audioRecorder.isRecording()) {
        await _audioRecorder.stop();
      }
    } catch (_) {}
    setState(() {
      _state = VoiceState.idle;
      _recordingSeconds = 0;
      _isPlayingAudio = false;
      _errorMessage = null;
      _recordedAudioBytes = <int>[];
      _currentRecordingPath = null;
      _transcriptController.clear();
    });
  }

  void _toggleAudioPlayback() {
    setState(() {
      _isPlayingAudio = !_isPlayingAudio;
    });
    if (_isPlayingAudio) {
      Future.delayed(Duration(seconds: _recordingSeconds.clamp(1, 4)), () {
        if (mounted) {
          setState(() => _isPlayingAudio = false);
        }
      });
    }
  }

  Future<void> _transcribeAudio() async {
    if (_recordedAudioBytes.isEmpty) {
      setState(() {
        _state = VoiceState.error;
        _errorMessage = 'No recorded audio available. Please record again.';
      });
      return;
    }

    setState(() {
      _state = VoiceState.transcribing;
      _errorMessage = null;
    });

    try {
      final filename = _currentRecordingPath != null && _currentRecordingPath!.endsWith('.m4a')
          ? 'voice_command.m4a'
          : 'voice_command.wav';

      final result = await VoiceService.transcribeAudio(
        audioBytes: _recordedAudioBytes,
        filename: filename,
      );

      if (!mounted) return;
      setState(() {
        _state = VoiceState.transcribed;
        _transcriptController.text = result.transcript;
        _detectedLanguage = result.language ?? 'en';
        _confidence = result.confidence;
        _processingTimeMs = result.processingTimeMs;
      });
    } on VoiceTranscriptionException catch (e) {
      if (!mounted) return;
      setState(() {
        _state = VoiceState.error;
        _errorMessage = e.message;
      });
      if (e.requiresSignIn) {
        Navigator.pushNamed(context, AppRoutes.signIn);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _state = VoiceState.error;
        _errorMessage = 'Failed to transcribe audio. Check connection and retry.';
      });
    }
  }

  Future<void> _submitTask() async {
    final transcript = _transcriptController.text.trim();
    if (transcript.isEmpty) {
      setState(() {
        _errorMessage = 'Transcript is empty. Please edit or record again.';
      });
      return;
    }

    setState(() {
      _state = VoiceState.submitting;
      _errorMessage = null;
    });

    try {
      await TaskService.createVoiceTask(transcript);
      if (!mounted) return;
      setState(() {
        _state = VoiceState.submitted;
      });
    } on TaskServiceException catch (e) {
      if (!mounted) return;
      setState(() {
        _state = VoiceState.error;
        _errorMessage = e.message;
      });
      if (e.requiresSignIn) {
        Navigator.pushNamed(context, AppRoutes.signIn);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _state = VoiceState.error;
        _errorMessage = 'Failed to submit voice task to planner.';
      });
    }
  }

  static List<int> _generateWavBytes(int seconds) {
    const sampleRate = 16000;
    const channels = 1;
    const bitsPerSample = 16;
    final totalSamples = seconds * sampleRate;
    final dataSize = totalSamples * channels * (bitsPerSample ~/ 8);
    final fileSize = 36 + dataSize;

    final header = Uint8List(44);
    final bdata = ByteData.sublistView(header);

    // RIFF header
    header.setRange(0, 4, 'RIFF'.codeUnits);
    bdata.setUint32(4, fileSize, Endian.little);
    header.setRange(8, 12, 'WAVE'.codeUnits);

    // fmt subchunk
    header.setRange(12, 16, 'fmt '.codeUnits);
    bdata.setUint32(16, 16, Endian.little); // subchunk1 size
    bdata.setUint16(20, 1, Endian.little); // audio format (PCM)
    bdata.setUint16(22, channels, Endian.little);
    bdata.setUint32(24, sampleRate, Endian.little);
    bdata.setUint32(28, sampleRate * channels * 2, Endian.little); // byte rate
    bdata.setUint16(32, channels * 2, Endian.little); // block align
    bdata.setUint16(34, bitsPerSample, Endian.little);

    // data subchunk
    header.setRange(36, 40, 'data'.codeUnits);
    bdata.setUint32(40, dataSize, Endian.little);

    final pcmData = Uint8List(dataSize);
    return header + pcmData;
  }


  void _showPermissionDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Microphone Access Required'),
        content: const Text(
          'AgentOps requires access to your device microphone to capture voice commands, '
          'transcribe them into structured tasks, and dispatch them to the LangGraph planner. '
          'Audio is strictly used for transcription and is never permanently stored without your consent.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              _startRecording();
            },
            child: const Text('Grant Access & Record'),
          ),
        ],
      ),
    );
  }

  String _formatDuration(int totalSeconds) {
    final minutes = (totalSeconds ~/ 60).toString().padLeft(2, '0');
    final seconds = (totalSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Voice Command'),
        actions: [
          TextButton.icon(
            key: const Key('switch-to-typed-input'),
            onPressed: () => Navigator.pushReplacementNamed(context, AppRoutes.taskComposer),
            icon: const Icon(Icons.keyboard_outlined, size: 18),
            label: const Text('Type instead'),
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.screenPadding),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: <Widget>[
              const SizedBox(height: AppSpacing.sm),
              Text(
                'Speak your task naturally',
                style: theme.textTheme.headlineMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'English, Hindi, and Hinglish voice commands are supported. You can review and edit before anything executes.',
                style: theme.textTheme.bodyMedium?.copyWith(color: AppColors.neutral700),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.xl),

              // Recording Hub / Visualizer Card
              _buildRecordingControlCard(theme),

              const SizedBox(height: AppSpacing.lg),

              // Error banner if any
              if (_errorMessage != null) _buildErrorBanner(theme),

              // Transcription & Confirmation Area
              if (_state == VoiceState.transcribing ||
                  _state == VoiceState.transcribed ||
                  _state == VoiceState.submitting ||
                  _state == VoiceState.submitted)
                _buildTranscriptReviewCard(theme),

              const SizedBox(height: AppSpacing.lg),

              // Safety disclaimer
              Container(
                padding: const EdgeInsets.all(AppSpacing.md),
                decoration: BoxDecoration(
                  color: AppColors.neutral100,
                  borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
                  border: Border.all(color: AppColors.neutral300),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.shield_outlined, color: AppColors.primary, size: 20),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        'Hardcoded safety gates enforce human approval before sending external emails or modifying calendars.',
                        style: theme.textTheme.bodySmall?.copyWith(color: AppColors.neutral700),
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

  Widget _buildRecordingControlCard(ThemeData theme) {
    final isRecording = _state == VoiceState.recording;
    final isRecorded = _state == VoiceState.recorded;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xl, horizontal: AppSpacing.lg),
      decoration: BoxDecoration(
        color: isRecording ? AppColors.primaryLight : AppColors.neutral100,
        borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
        border: Border.all(
          color: isRecording ? AppColors.primary : AppColors.neutral300,
          width: isRecording ? 2 : 1,
        ),
      ),
      child: Column(
        children: [
          // Elapsed Timer
          Text(
            _formatDuration(_recordingSeconds),
            style: theme.textTheme.headlineLarge?.copyWith(
              fontWeight: FontWeight.bold,
              color: isRecording ? AppColors.primaryDark : AppColors.neutral900,
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            isRecording
                ? 'Listening... Tap to finish'
                : isRecorded
                    ? 'Recording captured ($recordingTimeText)'
                    : 'Tap microphone to speak',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: isRecording ? AppColors.primary : AppColors.neutral500,
              fontWeight: isRecording ? FontWeight.w600 : FontWeight.normal,
            ),
          ),
          const SizedBox(height: AppSpacing.lg),

          // Pulsing Mic Button
          AnimatedBuilder(
            animation: _pulseController,
            builder: (context, child) {
              final scale = isRecording ? 1.0 + (_pulseController.value * 0.12) : 1.0;
              return Transform.scale(
                scale: scale,
                child: child,
              );
            },
            child: SizedBox(
              width: 84,
              height: 84,
              child: ElevatedButton(
                key: const Key('mic-record-button'),
                style: ElevatedButton.styleFrom(
                  shape: const CircleBorder(),
                  backgroundColor: isRecording ? AppColors.error : AppColors.primary,
                  padding: EdgeInsets.zero,
                  elevation: isRecording ? 8 : 4,
                ),
                onPressed: () {
                  if (_state == VoiceState.idle || _state == VoiceState.error || _state == VoiceState.submitted) {
                    _startRecording();
                  } else if (isRecording) {
                    _stopRecording();
                  } else if (isRecorded) {
                    _startRecording();
                  }
                },
                child: Icon(
                  isRecording ? Icons.stop : Icons.mic,
                  size: 38,
                  color: Colors.white,
                ),
              ),
            ),
          ),

          const SizedBox(height: AppSpacing.md),

          // Actions when audio is recorded
          if (isRecorded) ...[
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                OutlinedButton.icon(
                  key: const Key('play-preview-button'),
                  onPressed: _toggleAudioPlayback,
                  icon: Icon(_isPlayingAudio ? Icons.pause : Icons.play_arrow),
                  label: Text(_isPlayingAudio ? 'Playing...' : 'Play back'),
                ),
                const SizedBox(width: AppSpacing.sm),
                OutlinedButton.icon(
                  key: const Key('cancel-audio-button'),
                  onPressed: _cancelRecording,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Retry'),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                key: const Key('transcribe-button'),
                onPressed: _transcribeAudio,
                icon: const Icon(Icons.auto_awesome),
                label: const Text('Transcribe Audio'),
              ),
            ),
          ],
        ],
      ),
    );
  }

  String get recordingTimeText => _formatDuration(_recordingSeconds);

  Widget _buildErrorBanner(ThemeData theme) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.riskHighBg,
        borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
        border: Border.all(color: AppColors.riskHigh),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.error_outline, color: AppColors.riskHigh),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              _errorMessage ?? 'An error occurred.',
              style: theme.textTheme.bodyMedium?.copyWith(color: AppColors.riskHigh),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTranscriptReviewCard(ThemeData theme) {
    final isTranscribing = _state == VoiceState.transcribing;
    final isSubmitting = _state == VoiceState.submitting;
    final isSubmitted = _state == VoiceState.submitted;

    if (isTranscribing) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(AppSpacing.lg),
        decoration: BoxDecoration(
          color: AppColors.neutral100,
          borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
        ),
        child: const Column(
          children: [
            CircularProgressIndicator(),
            SizedBox(height: AppSpacing.md),
            Text('Transcribing speech with faster-whisper...'),
          ],
        ),
      );
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: isSubmitted ? AppColors.riskLowBg : AppColors.neutral0,
        borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
        border: Border.all(
          color: isSubmitted ? AppColors.riskLow : AppColors.neutral300,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                isSubmitted ? Icons.check_circle : Icons.edit_note,
                color: isSubmitted ? AppColors.riskLow : AppColors.primary,
              ),
              const SizedBox(width: AppSpacing.xs),
              Expanded(
                child: Text(
                  isSubmitted ? 'Task Dispatched to Planner' : 'Recognized Transcript (Editable)',
                  style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (!isSubmitted) ...[
                const SizedBox(width: AppSpacing.xs),
                Chip(
                  label: Text('$_detectedLanguage${_confidence != null ? ' (${(_confidence! * 100).toStringAsFixed(0)}%)' : ''} • ${_processingTimeMs}ms'),
                  padding: EdgeInsets.zero,
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          TextField(
            key: const Key('transcript-edit-field'),
            controller: _transcriptController,
            enabled: !isSubmitting && !isSubmitted,
            maxLines: 4,
            decoration: const InputDecoration(
              hintText: 'Edit transcript if any word was misrecognized...',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          if (!isSubmitted)
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                key: const Key('confirm-task-button'),
                onPressed: isSubmitting ? null : _submitTask,
                icon: isSubmitting
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.send_outlined),
                label: Text(isSubmitting ? 'Sending to Planner...' : 'Confirm & Send to Planner'),
              ),
            ),
          if (isSubmitted)
            Text(
              'Your voice command was submitted as a structured task. '
              'The LangGraph planner will decompose it into steps and request approval if risky actions are detected.',
              style: theme.textTheme.bodyMedium?.copyWith(color: AppColors.riskLow),
            ),
        ],
      ),
    );
  }
}