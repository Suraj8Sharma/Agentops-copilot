// ActivityLogService — fetches real execution_logs from GET /me/activity.
//
// Mapping strategy:
//   Backend event_type         → LogEventType
//   tool_called / tool_result  → toolCall
//   approval_decided (payload.decision == 'approved') → approval
//   approval_decided (payload.decision == 'rejected') → rejection
//   plan_created               → taskCreated
//   step_completed             → taskCompleted (task-level equivalent)
//   step_failed / error        → taskFailed
//   everything else            → toolCall (safe fallback)
//
// Falls back to mockActivityLog if the network call fails so the
// screen always shows something useful.

import 'dart:convert';
import 'package:http/http.dart' as http;

import '../../core/theme.dart';
import '../home/task_service.dart' show TaskService;
import 'activity_log_models.dart';

class ActivityLogException implements Exception {
  const ActivityLogException(this.message, {this.requiresSignIn = false});
  final String message;
  final bool requiresSignIn;
  @override
  String toString() => message;
}

class ActivityLogService {
  ActivityLogService._();

  static const String _baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  // Override hook — lets tests inject a custom list without a network.
  static Future<List<ActivityLogEntry>> Function({
    int limit,
    int offset,
    String? eventTypeFilter,
  })? fetchOverride;

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /// Fetch activity log entries from the backend.
  ///
  /// Returns [mockActivityLog] on any network / parse error so the UI is
  /// always populated even when offline or the backend has no logs yet.
  static Future<List<ActivityLogEntry>> fetchActivityLog({
    int limit = 100,
    int offset = 0,
    String? eventTypeFilter,
  }) async {
    if (fetchOverride != null) {
      return fetchOverride!(
          limit: limit, offset: offset, eventTypeFilter: eventTypeFilter);
    }

    final token = await TaskService.accessTokenProvider?.call();

    final uri = Uri.parse('$_baseUrl/me/activity').replace(
      queryParameters: <String, String>{
        'limit': '$limit',
        'offset': '$offset',
        if (eventTypeFilter != null) 'event_type': eventTypeFilter,
      },
    );

    http.Response response;
    try {
      response = await http.get(
        uri,
        headers: <String, String>{
          if (token != null && token.isNotEmpty)
            'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
      ).timeout(const Duration(seconds: 10));
    } catch (_) {
      // Network error — fall back to mock so the screen stays useful.
      return _sortedMock();
    }

    if (response.statusCode == 401) {
      throw const ActivityLogException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
      );
    }

    if (response.statusCode != 200) {
      // Non-auth server error — fall back to mock.
      return _sortedMock();
    }

    try {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      final rawItems = body['items'] as List<dynamic>;
      return rawItems
          .map((item) => _fromJson(item as Map<String, dynamic>))
          .toList();
    } catch (_) {
      // Parse error — fall back to mock.
      return _sortedMock();
    }
  }

  // ---------------------------------------------------------------------------
  // Mapping helpers
  // ---------------------------------------------------------------------------

  static List<ActivityLogEntry> _sortedMock() {
    final sorted = List<ActivityLogEntry>.from(mockActivityLog);
    sorted.sort((a, b) => b.timestamp.compareTo(a.timestamp));
    return sorted;
  }

  static ActivityLogEntry _fromJson(Map<String, dynamic> json) {
    final rawEventType = json['event_type'] as String? ?? '';
    final payload = (json['payload'] as Map<String, dynamic>?) ?? {};

    final eventType = _mapEventType(rawEventType, payload);
    final agentName = json['agent_name'] as String? ?? '';
    final taskId = json['task_id'] as String?;
    final createdAt = DateTime.tryParse(
          json['created_at'] as String? ?? '',
        ) ??
        DateTime.now();

    // Derive title + description from event_type + payload.
    final title = _deriveTitle(rawEventType, agentName, payload);
    final description = _deriveDescription(rawEventType, agentName, payload);

    // Derive integration name from agent_name (mcp_gmail → gmail, etc.).
    final integration = _deriveIntegration(agentName);

    // Derive risk tier from payload if present.
    final riskTier = _deriveRiskTier(payload);

    return ActivityLogEntry(
      id: json['id']?.toString() ?? 'log-${json.hashCode}',
      eventType: eventType,
      title: title,
      description: description,
      timestamp: createdAt,
      integration: integration,
      taskId: taskId,
      riskTier: riskTier,
    );
  }

  static LogEventType _mapEventType(
      String rawType, Map<String, dynamic> payload) {
    switch (rawType) {
      case 'tool_called':
      case 'tool_result':
      case 'step_started':
      case 'risk_tagged':
        return LogEventType.toolCall;

      case 'approval_decided':
        // payload.decision == 'approved' | 'rejected'
        final decision = payload['decision'] as String? ?? '';
        return decision == 'rejected'
            ? LogEventType.rejection
            : LogEventType.approval;

      case 'approval_requested':
        return LogEventType.approval;

      case 'plan_created':
        return LogEventType.taskCreated;

      case 'step_completed':
        return LogEventType.taskCompleted;

      case 'step_failed':
      case 'error':
        return LogEventType.taskFailed;

      default:
        return LogEventType.toolCall;
    }
  }

  static String _deriveTitle(
      String rawType, String agentName, Map<String, dynamic> payload) {
    final toolName = payload['tool_name'] as String? ??
        payload['tool'] as String? ??
        agentName;

    switch (rawType) {
      case 'tool_called':
        return '$toolName called';
      case 'tool_result':
        return '$toolName result';
      case 'approval_decided':
        final decision = payload['decision'] as String? ?? 'decided';
        return '$toolName $decision';
      case 'approval_requested':
        return '$toolName awaiting approval';
      case 'plan_created':
        return 'Task created';
      case 'step_completed':
        return '$toolName completed';
      case 'step_failed':
        return '$toolName failed';
      case 'step_started':
        return '$toolName started';
      case 'risk_tagged':
        return 'Risk assessed for $toolName';
      case 'error':
        return 'Error in $agentName';
      default:
        return rawType.replaceAll('_', ' ');
    }
  }

  static String _deriveDescription(
      String rawType, String agentName, Map<String, dynamic> payload) {
    // Use an explicit description from the payload if the backend set one.
    final explicit = payload['description'] as String? ??
        payload['summary'] as String? ??
        payload['message'] as String?;
    if (explicit != null && explicit.isNotEmpty) return explicit;

    // Otherwise build a generic one from what we know.
    switch (rawType) {
      case 'tool_called':
        return 'Agent $agentName called a tool.';
      case 'tool_result':
        return 'Tool result received by $agentName.';
      case 'approval_decided':
        final decision = payload['decision'] as String? ?? 'decided';
        return 'You $decision this action.';
      case 'approval_requested':
        return 'Waiting for your approval before continuing.';
      case 'plan_created':
        return 'A new task plan was generated by the planner.';
      case 'step_completed':
        return 'Step completed successfully.';
      case 'step_failed':
        final err = payload['error'] as String? ?? 'unknown error';
        return 'Step failed: $err';
      case 'step_started':
        return 'Step execution started.';
      case 'risk_tagged':
        final tier = payload['risk_tier'] as String? ?? 'unknown';
        return 'Risk tier assessed as $tier.';
      case 'error':
        final err = payload['error'] as String? ?? 'An unexpected error occurred.';
        return err;
      default:
        return 'Event recorded by $agentName.';
    }
  }

  static String? _deriveIntegration(String agentName) {
    // agent_name values: mcp_gmail, mcp_calendar, mcp_github, mcp_slack
    if (agentName.startsWith('mcp_')) {
      return agentName.substring(4); // strip "mcp_"
    }
    return null;
  }

  static RiskTier? _deriveRiskTier(Map<String, dynamic> payload) {
    final raw = payload['risk_tier'] as String?;
    switch (raw) {
      case 'low':
        return RiskTier.low;
      case 'medium':
        return RiskTier.medium;
      case 'high':
        return RiskTier.high;
      default:
        return null;
    }
  }
}
