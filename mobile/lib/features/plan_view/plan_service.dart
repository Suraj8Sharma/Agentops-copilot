import 'dart:convert';
import 'package:http/http.dart' as http;
import 'plan_view_screen.dart' show MockPlan, PlanStep, PlanStepStatus;
import '../../core/theme.dart' show RiskTier;
import '../home/task_service.dart';

class PlanService {
  static const String baseUrl =
      String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');

  static Future<MockPlan> Function(String taskId)? fetchPlanOverride;

  static http.Client? httpClientOverride;

  static Future<String?> _getToken() async =>
      TaskService.accessTokenProvider?.call();

  static RiskTier _parseRiskTier(String tier) {
    switch (tier) {
      case 'low':
        return RiskTier.low;
      case 'medium':
        return RiskTier.medium;
      case 'high':
        return RiskTier.high;
      default:
        return RiskTier.high;
    }
  }

  static PlanStepStatus _parseStatus(String status) {
    switch (status) {
      case 'pending':
        return PlanStepStatus.pending;
      case 'awaiting_approval':
        return PlanStepStatus.awaitingApproval;
      case 'approved':
        return PlanStepStatus.approved;
      case 'rejected':
        return PlanStepStatus.rejected;
      case 'executing':
        return PlanStepStatus.executing;
      case 'done':
        return PlanStepStatus.done;
      case 'failed':
        return PlanStepStatus.failed;
      default:
        // Unknown backend states must not be interpreted as successful or
        // actionable. The UI renders pending and the caller forces approval
        // for the same fail-closed path.
        return PlanStepStatus.pending;
    }
  }

  static Future<MockPlan> fetchPlan(String taskId) async {
    if (fetchPlanOverride != null) {
      return fetchPlanOverride!(taskId);
    }

    var token = await _getToken();
    var response = await (httpClientOverride ?? http.Client()).get(
      Uri.parse('$baseUrl/tasks/$taskId/plan'),
      headers: <String, String>{
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 401 &&
        TaskService.refreshAccessTokenProvider != null) {
      token = await TaskService.refreshAccessTokenProvider!();
      if (token == null || token.isEmpty) {
        throw const PlanAuthException(
            'Your session has expired. Please sign in again.');
      }
      response = await (httpClientOverride ?? http.Client()).get(
        Uri.parse('$baseUrl/tasks/$taskId/plan'),
        headers: <String, String>{
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
      );
    }

    if (response.statusCode == 401) {
      throw const PlanAuthException(
          'Your session has expired. Please sign in again.');
    }

    if (response.statusCode == 200) {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      // Accept the deployed task_plan/plan_steps contract and the documented
      // plan/steps shape while the API migration is in flight.
      final taskPlanJson =
          (decoded['task_plan'] ?? decoded['plan']) as Map<String, dynamic>;
      final planStepsList =
          (decoded['plan_steps'] ?? decoded['steps']) as List<dynamic>;

      final steps = planStepsList.map((stepJson) {
        final rawStatus = stepJson['status'] as String? ?? 'unknown';
        final rawRisk = stepJson['risk_tier'] as String? ?? 'unknown';
        final unknownStatus = !<String>{
          'pending',
          'awaiting_approval',
          'approved',
          'rejected',
          'executing',
          'done',
          'failed',
        }.contains(rawStatus);
        final unknownRisk = !<String>{'low', 'medium', 'high'}
            .contains(rawRisk);
        return PlanStep(
          id: stepJson['id'] as String,
          stepIndex: stepJson['step_index'] as int,
          toolName: stepJson['tool_name'] as String,
          mcpServer: stepJson['mcp_server'] as String,
          riskTier: _parseRiskTier(rawRisk),
          // Never let an unrecognised value become a safe, one-tap path.
          requiresApproval: unknownRisk || unknownStatus
              ? true
              : stepJson['requires_approval'] as bool? ?? true,
          status: _parseStatus(rawStatus),
          inputParams: stepJson['input_params'] as Map<String, dynamic>? ?? {},
          output: stepJson['output'] as Map<String, dynamic>?,
        );
      }).toList();

      return MockPlan(
        id: taskPlanJson['id'] as String,
        taskId: taskPlanJson['task_id'] as String,
        plannerVersion: taskPlanJson['planner_version'] as String,
        status: taskPlanJson['status'] as String,
        steps: steps,
      );
    } else if (response.statusCode == 404) {
      throw const PlanNotFoundException('Plan not ready yet');
    } else {
      String errorMessage = 'Failed to load plan';
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

class PlanNotFoundException implements Exception {
  const PlanNotFoundException(this.message);
  final String message;

  @override
  String toString() => message;
}

class PlanAuthException implements Exception {
  const PlanAuthException(this.message);
  final String message;

  @override
  String toString() => message;
}
