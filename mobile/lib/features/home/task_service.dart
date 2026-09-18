import 'dart:convert';
import 'package:http/http.dart' as http;
import 'home_screen.dart' show AppTask;

class TaskServiceException implements Exception {
  const TaskServiceException(this.message, {this.requiresSignIn = false});

  final String message;
  final bool requiresSignIn;

  @override
  String toString() => message;
}

class TaskService {
  static const String baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// The app's auth/session layer supplies the current Supabase access token.
  static Future<String?> Function()? accessTokenProvider;
  static Future<String?> Function()? refreshAccessTokenProvider;
  static Future<List<AppTask>> Function()? fetchTasksOverride;
  static Future<AppTask> Function(String rawInput)? createTaskOverride;
  static http.Client? httpClientOverride;

  static Future<String?> _getToken() async {
    return accessTokenProvider?.call();
  }

  static Future<List<AppTask>> fetchTasks() async {
    if (fetchTasksOverride != null) {
      return fetchTasksOverride!();
    }
    
    final token = await _getToken();
    final response = await (httpClientOverride ?? http.Client()).get(
      Uri.parse('$baseUrl/tasks'),
      headers: {
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 200) {
      final decoded = jsonDecode(response.body);
      final list = decoded['tasks'] as List<dynamic>;
      return list.map((e) => AppTask.fromJson(e as Map<String, dynamic>)).toList();
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
      throw TaskServiceException(_errorMessage(response, 'Failed to submit task.'));
    }

    try {
      return AppTask.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
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

  static String _errorMessage(http.Response response, String fallback) {
    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      final detail = decoded['detail'];
      if (detail is String && detail.isNotEmpty) return detail;
    } catch (_) {}
    return '$fallback (HTTP ${response.statusCode})';
  }
}
