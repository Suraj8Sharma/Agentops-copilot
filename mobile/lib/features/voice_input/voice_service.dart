import 'dart:convert';
import 'package:http/http.dart' as http;

import '../../core/api_config.dart';
import '../auth/auth_service.dart';
import '../home/task_service.dart' show TaskService;

class VoiceTranscriptionException implements Exception {
  const VoiceTranscriptionException(this.message, {this.requiresSignIn = false});
  final String message;
  final bool requiresSignIn;

  @override
  String toString() => message;
}

class TranscriptionResult {
  const TranscriptionResult({
    required this.transcript,
    this.language,
    this.confidence,
    this.durationSeconds,
    required this.processingTimeMs,
    required this.engine,
  });

  final String transcript;
  final String? language;
  final double? confidence;
  final double? durationSeconds;
  final int processingTimeMs;
  final String engine;

  factory TranscriptionResult.fromJson(Map<String, dynamic> json) {
    return TranscriptionResult(
      transcript: json['transcript'] as String? ?? '',
      language: json['language'] as String?,
      confidence: (json['confidence'] as num?)?.toDouble(),
      durationSeconds: (json['duration_seconds'] as num?)?.toDouble(),
      processingTimeMs: (json['processing_time_ms'] as num?)?.toInt() ?? 0,
      engine: json['engine'] as String? ?? 'unknown',
    );
  }
}

class VoiceService {
  VoiceService._();

  static String get _baseUrl => ApiConfig.baseUrl;

  /// Test seam for unit/widget testing without network.
  static Future<TranscriptionResult> Function({
    required List<int> audioBytes,
    required String filename,
    String? languageHint,
  })? transcribeOverride;

  static http.Client? httpClientOverride;

  static Future<TranscriptionResult> transcribeAudio({
    required List<int> audioBytes,
    required String filename,
    String? languageHint,
  }) async {
    if (audioBytes.isEmpty) {
      throw const VoiceTranscriptionException('No audio data recorded (0 bytes).');
    }

    if (transcribeOverride != null) {
      return transcribeOverride!(
        audioBytes: audioBytes,
        filename: filename,
        languageHint: languageHint,
      );
    }

    var token = await AuthService.getAccessToken();
    var result = await _performMultipartUpload(
      audioBytes: audioBytes,
      filename: filename,
      languageHint: languageHint,
      token: token,
    );

    // Handle token expiration / retry
    if (result.statusCode == 401 && TaskService.refreshAccessTokenProvider != null) {
      token = await TaskService.refreshAccessTokenProvider!();
      if (token == null || token.isEmpty) {
        throw const VoiceTranscriptionException(
          'Your session has expired. Please sign in again.',
          requiresSignIn: true,
        );
      }
      result = await _performMultipartUpload(
        audioBytes: audioBytes,
        filename: filename,
        languageHint: languageHint,
        token: token,
      );
    }

    if (result.statusCode == 401) {
      throw const VoiceTranscriptionException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
      );
    }

    if (result.statusCode == 400) {
      final detail = _extractDetail(result.body, 'Invalid audio recording.');
      throw VoiceTranscriptionException(detail);
    }

    if (result.statusCode == 413) {
      throw const VoiceTranscriptionException(
        'Audio file is too large (maximum 25 MB supported).',
      );
    }

    if (result.statusCode != 200) {
      final detail = _extractDetail(
        result.body,
        'Voice transcription service error (HTTP ${result.statusCode}).',
      );
      throw VoiceTranscriptionException(detail);
    }

    try {
      final json = jsonDecode(result.body) as Map<String, dynamic>;
      return TranscriptionResult.fromJson(json);
    } catch (_) {
      throw const VoiceTranscriptionException(
        'Unexpected response format from speech transcription service.',
      );
    }
  }

  static Future<http.Response> _performMultipartUpload({
    required List<int> audioBytes,
    required String filename,
    String? languageHint,
    String? token,
  }) async {
    final uri = Uri.parse('$_baseUrl/voice/transcribe');
    final request = http.MultipartRequest('POST', uri);

    if (token != null && token.isNotEmpty) {
      request.headers['Authorization'] = 'Bearer $token';
    }

    if (languageHint != null && languageHint.trim().isNotEmpty) {
      request.fields['language'] = languageHint.trim();
    }

    final multipartFile = http.MultipartFile.fromBytes(
      'file',
      audioBytes,
      filename: filename,
    );
    request.files.add(multipartFile);

    final client = httpClientOverride ?? http.Client();
    final streamedResponse = await client.send(request);
    return http.Response.fromStream(streamedResponse);
  }

  static String _extractDetail(String responseBody, String fallback) {
    try {
      final decoded = jsonDecode(responseBody) as Map<String, dynamic>;
      final detail = decoded['detail'];
      if (detail is String && detail.isNotEmpty) return detail;
    } catch (_) {}
    return fallback;
  }
}
