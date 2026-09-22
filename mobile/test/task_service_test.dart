import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:agentops_copilot/features/home/task_service.dart';

void main() {
  tearDown(() {
    TaskService.httpClientOverride = null;
    TaskService.accessTokenProvider = null;
    TaskService.refreshAccessTokenProvider = null;
    TaskService.createTaskOverride = null;
  });

  test('POSTs exact text payload with the bearer token', () async {
    String? auth;
    Map<String, dynamic>? body;
    TaskService.accessTokenProvider = () async => 'access-token';
    TaskService.httpClientOverride = MockClient((request) async {
      auth = request.headers['authorization'];
      body = jsonDecode(request.body) as Map<String, dynamic>;
      return http.Response(jsonEncode(<String, dynamic>{
        'id': 'task-1',
        'user_id': 'user-1',
        'input_type': 'text',
        'raw_input': '  exact text  ',
        'transcription_text': null,
        'status': 'submitted',
        'created_at': '2026-09-08T10:00:00Z',
        'completed_at': null,
      }), 201);
    });

    final task = await TaskService.createTextTask('  exact text  ');

    expect(auth, 'Bearer access-token');
    expect(body, <String, dynamic>{
      'input_type': 'text',
      'raw_input': '  exact text  ',
    });
    expect(task.status.name, 'submitted');
  });

  test('refreshes once after 401 and retries with the new token', () async {
    final tokens = <String?>['old-token', 'new-token'];
    final authHeaders = <String>[];
    var refreshes = 0;
    TaskService.accessTokenProvider = () async => tokens.removeAt(0);
    TaskService.refreshAccessTokenProvider = () async {
      refreshes++;
      return 'new-token';
    };
    TaskService.httpClientOverride = MockClient((request) async {
      authHeaders.add(request.headers['authorization']!);
      if (authHeaders.length == 1) return http.Response('{"detail":"token_expired"}', 401);
      return http.Response(jsonEncode(<String, dynamic>{
        'id': 'task-1', 'user_id': 'user-1', 'input_type': 'text',
        'raw_input': 'retry me', 'transcription_text': null,
        'status': 'submitted', 'created_at': '2026-09-08T10:00:00Z',
        'completed_at': null,
      }), 201);
    });

    await TaskService.createTextTask('retry me');

    expect(refreshes, 1);
    expect(authHeaders, <String>['Bearer old-token', 'Bearer new-token']);
  });
}
