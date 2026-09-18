import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:agentops_copilot/features/home/task_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_service.dart';
import 'package:agentops_copilot/features/plan_view/plan_view_screen.dart';

void main() {
  tearDown(() {
    PlanService.httpClientOverride = null;
    PlanService.fetchPlanOverride = null;
    TaskService.accessTokenProvider = null;
    TaskService.refreshAccessTokenProvider = null;
  });

  test('loads the active plan with the authenticated token', () async {
    String? authorization;
    TaskService.accessTokenProvider = () async => 'plan-token';
    PlanService.httpClientOverride = MockClient((request) async {
      authorization = request.headers['authorization'];
      return http.Response(
          jsonEncode(<String, dynamic>{
            'task_plan': <String, dynamic>{
              'id': 'plan-1',
              'task_id': 'task-1',
              'planner_version': 'planner-v1',
              'status': 'active',
            },
            'plan_steps': <Map<String, dynamic>>[
              <String, dynamic>{
                'id': 'step-1',
                'step_index': 0,
                'tool_name': 'gmail.send_message',
                'mcp_server': 'gmail',
                'risk_tier': 'high',
                'requires_approval': true,
                'status': 'awaiting_approval',
                'input_params': <String, dynamic>{},
                'output': null,
              },
            ],
          }),
          200);
    });

    final plan = await PlanService.fetchPlan('task-1');

    expect(authorization, 'Bearer plan-token');
    expect(plan.status, 'active');
    expect(plan.steps.single.status, PlanStepStatus.awaitingApproval);
  });
}
