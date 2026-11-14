import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:agentops_copilot/features/activity_log/activity_log_models.dart';
import 'package:agentops_copilot/features/activity_log/activity_log_service.dart';
import 'package:agentops_copilot/features/home/task_service.dart';

void main() {
  tearDown(() {
    ActivityLogService.httpClientOverride = null;
    TaskService.accessTokenProvider = null;
  });

  test('requests activity-log with auth and parses the audit contract', () async {
    Uri? requested;
    ActivityLogService.httpClientOverride = MockClient((request) async {
      requested = request.url;
      expect(request.headers['Authorization'], 'Bearer activity-token');
      return http.Response('''{
        "items": [{
          "id": 9007199254740991,
          "task_id": "task-1",
          "step_id": null,
          "agent_name": "risk_gate",
          "event_type": "approval_decided",
          "payload": {"decision": "rejected", "access_token": "secret", "tool_name": "gmail.send_message"},
          "created_at": "2026-09-24T09:15:30Z"
        }],
        "next_cursor": "cursor-2"
      }''', 200);
    });
    TaskService.accessTokenProvider = () async => 'activity-token';

    final page = await ActivityLogService.fetchPage(
      eventTypes: const {LogEventType.approvalDecided},
      query: 'gmail',
    );

    expect(requested!.path, '/activity-log');
    expect(requested!.queryParameters['event_type'], 'approval_decided');
    expect(requested!.queryParameters['q'], 'gmail');
    expect(page.nextCursor, 'cursor-2');
    expect(page.items.single.id, '9007199254740991');
    expect(page.items.single.decision, 'rejected');
    expect(page.items.single.payload.containsKey('access_token'), isFalse);
  });

  test('401 is surfaced as sign-in handoff instead of mock data', () async {
    ActivityLogService.httpClientOverride =
        MockClient((_) async => http.Response('Unauthorized', 401));

    expect(
      () => ActivityLogService.fetchPage(),
      throwsA(isA<ActivityLogException>().having(
        (error) => error.requiresSignIn,
        'requiresSignIn',
        isTrue,
      )),
    );
  });
}
