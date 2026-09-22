import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:agentops_copilot/features/approval/approval_screen.dart';
import 'package:agentops_copilot/features/approval/approval_service.dart';
import 'package:agentops_copilot/features/home/task_service.dart';

void main() {
  tearDown(() {
    ApprovalService.httpClientOverride = null;
    ApprovalService.fetchPendingOverride = null;
    ApprovalService.decideOverride = null;
    TaskService.accessTokenProvider = null;
    TaskService.refreshAccessTokenProvider = null;
  });

  test('fetches pending approvals with the bearer token', () async {
    String? authorization;
    TaskService.accessTokenProvider = () async => 'approval-token';
    ApprovalService.httpClientOverride = MockClient((request) async {
      authorization = request.headers['authorization'];
      return http.Response(
          jsonEncode(<Map<String, dynamic>>[
            <String, dynamic>{
              'step_id': 'step-1',
              'task_id': 'task-1',
              'tool_name': 'gmail.send_message',
              'mcp_server': 'gmail',
              'risk_tier': 'high',
              'requires_approval': true,
              'input_params': <String, dynamic>{},
              'explanation_text': 'Send it.',
              'status': 'awaiting_approval',
            },
          ]),
          200);
    });

    final result = await ApprovalService.fetchPending();

    expect(authorization, 'Bearer approval-token');
    expect(result.single.explanationText, 'Send it.');
  });

  test('posts the decision to the step endpoint', () async {
    String? path;
    Map<String, dynamic>? payload;
    TaskService.accessTokenProvider = () async => 'approval-token';
    ApprovalService.httpClientOverride = MockClient((request) async {
      path = request.url.path;
      payload = jsonDecode(request.body) as Map<String, dynamic>;
      return http.Response('{}', 200);
    });

    await ApprovalService.decide('step-1', ApprovalDecision.rejected);

    expect(path, '/approvals/step-1');
    expect(payload, <String, dynamic>{'decision': 'rejected'});
  });

  test('refreshes an expired token once before retrying', () async {
    var calls = 0;
    var refreshes = 0;
    TaskService.accessTokenProvider = () async => 'old-token';
    TaskService.refreshAccessTokenProvider = () async {
      refreshes++;
      return 'new-token';
    };
    ApprovalService.httpClientOverride = MockClient((request) async {
      calls++;
      if (calls == 1) return http.Response('{"detail":"token_expired"}', 401);
      return http.Response('[]', 200);
    });

    await ApprovalService.fetchPending();

    expect(calls, 2);
    expect(refreshes, 1);
  });
}
