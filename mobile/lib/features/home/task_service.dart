import 'dart:convert';
import 'package:http/http.dart' as http;
import 'home_screen.dart' show AppTask;

class TaskService {
  static const String baseUrl = String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');

  // For testing
  static Future<List<AppTask>> Function()? fetchTasksOverride;

  // Stub for getting JWT until full Auth is integrated
  static Future<String?> _getToken() async {
    return 'stub-jwt-token';
  }

  static Future<List<AppTask>> fetchTasks() async {
    if (fetchTasksOverride != null) {
      return fetchTasksOverride!();
    }
    
    final token = await _getToken();
    final response = await http.get(
      Uri.parse('$baseUrl/tasks'),
      headers: {
        'Authorization': 'Bearer $token',
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
}
