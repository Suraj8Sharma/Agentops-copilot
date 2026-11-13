import 'dart:convert';
import 'package:http/http.dart' as http;
import 'home_screen.dart' show AppTask;
import '../../core/api_config.dart';

class TaskServiceException implements Exception {
  const TaskServiceException(this.message, {this.requiresSignIn = false});

  final String message;
  final bool requiresSignIn;

  @override
  String toString() => message;
}

class TaskService {
  static String get baseUrl => ApiConfig.baseUrl;

  /// The app's auth/session layer supplies the current Supabase access token.
  static Future<String?> Function()? accessTokenProvider;
  static Future<String?> Function()? refreshAccessTokenProvider;
  static Future<List<AppTask>> Function()? fetchTasksOverride;
  static Future<AppTask> Function(String rawInput)? createTaskOverride;
  static Future<AppTask> Function(String transcriptionText)? createVoiceTaskOverride;
  static http.Client? httpClientOverride;

  static Future<String?> _getToken() async {
    return accessTokenProvider?.call();
  }

  static Future<List<AppTask>> fetchTasks() async {
    if (fetchTasksOverride != null) {
      return fetchTasksOverride!();
    }

    var token = await _getToken();
    var response = await (httpClientOverride ?? http.Client()).get(
      Uri.parse('$baseUrl/tasks'),
      headers: <String, String>{
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 401 && refreshAccessTokenProvider != null) {
      token = await refreshAccessTokenProvider!();
      if (token == null || token.isEmpty) {
        throw const TaskServiceException(
          'Your session has expired. Please sign in again.',
          requiresSignIn: true,
        );
      }
      response = await (httpClientOverride ?? http.Client()).get(
        Uri.parse('$baseUrl/tasks'),
        headers: <String, String>{
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
      );
    }

    if (response.statusCode == 401) {
      throw const TaskServiceException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
      );
    }

    if (response.statusCode == 200) {
      final decoded = jsonDecode(response.body);
      final List<dynamic> list;
      if (decoded is List) {
        list = decoded;
      } else if (decoded is Map<String, dynamic> && decoded['tasks'] is List) {
        list = decoded['tasks'] as List<dynamic>;
      } else {
        list = <dynamic>[];
      }
      return list
          .map((e) => AppTask.fromJson(e as Map<String, dynamic>))
          .toList();
    } else {
      String errorMessage = 'Failed to load tasks';
      try {
        final decoded = jsonDecode(response.body);
        if (decoded['detail'] != null) {
          errorMessage = decoded['detail'];
        }
      } catch (_) {}
      throw Exception(errorMessage);
    }
  }

  static Future<AppTask> createTextTask(String rawInput) async {
    if (rawInput.trim().isEmpty) {
      throw const TaskServiceException('Task input cannot be empty.');
    }
    if (createTaskOverride != null) return createTaskOverride!(rawInput);

    var token = await _getToken();
    var response = await _postTask(rawInput, token);

    if (response.statusCode == 401 && refreshAccessTokenProvider != null) {
      token = await refreshAccessTokenProvider!();
      if (token == null || token.isEmpty) {
        throw const TaskServiceException(
          'Your session has expired. Please sign in again.',
          requiresSignIn: true,
        );
      }
      response = await _postTask(rawInput, token);
    }
    if (response.statusCode == 401) {
      throw const TaskServiceException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
      );
    }
    if (response.statusCode != 201) {
      throw TaskServiceException(
          _errorMessage(response, 'Failed to submit task.'));
    }

    try {
      return AppTask.fromJson(
          jsonDecode(response.body) as Map<String, dynamic>);
    } catch (_) {
      throw const TaskServiceException('The server returned an invalid task.');
    }
  }

  static Future<AppTask> createVoiceTask(String transcriptionText) async {
    if (transcriptionText.trim().isEmpty) {
      throw const TaskServiceException('Voice transcription cannot be empty.');
    }
    if (createVoiceTaskOverride != null) {
      return createVoiceTaskOverride!(transcriptionText);
    }

    var token = await _getToken();
    var response = await _postVoiceTask(transcriptionText, token);

    if (response.statusCode == 401 && refreshAccessTokenProvider != null) {
      token = await refreshAccessTokenProvider!();
      if (token == null || token.isEmpty) {
        throw const TaskServiceException(
          'Your session has expired. Please sign in again.',
          requiresSignIn: true,
        );
      }
      response = await _postVoiceTask(transcriptionText, token);
    }
    if (response.statusCode == 401) {
      throw const TaskServiceException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
      );
    }
    if (response.statusCode != 201) {
      throw TaskServiceException(
          _errorMessage(response, 'Failed to submit task.'));
    }

    try {
      return AppTask.fromJson(
          jsonDecode(response.body) as Map<String, dynamic>);
    } catch (_) {
      throw const TaskServiceException('The server returned an invalid task.');
    }
  }

  static Future<http.Response> _postTask(String rawInput, String? token) {
    return (httpClientOverride ?? http.Client()).post(
      Uri.parse('$baseUrl/tasks'),
      headers: <String, String>{
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, String>{
        'input_type': 'text',
        'raw_input': rawInput,
      }),
    );
  }

  static Future<http.Response> _postVoiceTask(String transcriptionText, String? token) {
    return (httpClientOverride ?? http.Client()).post(
      Uri.parse('$baseUrl/tasks'),
      headers: <String, String>{
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, String>{
        'input_type': 'voice',
        'transcription_text': transcriptionText,
      }),
    );
  }

  static String _errorMessage(http.Response response, String fallback) {
    if (response.statusCode == 429) {
      return 'Rate limit reached. Please wait a moment and try again.';
    }
    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      final detail = decoded['detail'];
      if (detail is String && detail.isNotEmpty) return detail;
    } catch (_) {}
    return '$fallback (HTTP ${response.statusCode})';
  }
}
