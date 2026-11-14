import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/theme.dart';
import '../home/task_service.dart';
import 'activity_log_models.dart';

class ActivityLogException implements Exception {
  const ActivityLogException(
    this.message, {
    this.requiresSignIn = false,
    this.retryable = false,
    this.statusCode,
  });

  final String message;
  final bool requiresSignIn;
  final bool retryable;
  final int? statusCode;

  @override
  String toString() => message;
}

class ActivityLogPage {
  const ActivityLogPage({required this.items, this.nextCursor});

  final List<ActivityLogEntry> items;
  final String? nextCursor;
}

class ActivityLogService {
  ActivityLogService._();

  static const String baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static Future<List<ActivityLogEntry>> Function({
    int limit,
    int offset,
    String? eventTypeFilter,
  })? fetchOverride;
  static Future<ActivityLogPage> Function({
    int limit,
    String? cursor,
    Set<LogEventType> eventTypes,
    DateTime? from,
    DateTime? to,
    String? query,
  })? fetchPageOverride;
  static http.Client? httpClientOverride;

  static Future<ActivityLogPage> fetchPage({
    int limit = 50,
    String? cursor,
    Set<LogEventType> eventTypes = const <LogEventType>{},
    DateTime? from,
    DateTime? to,
    String query = '',
  }) async {
    if (from != null && to != null && from.isAfter(to)) {
      throw const ActivityLogException(
        'The start date must be before the end date.',
        statusCode: 422,
      );
    }
    if (fetchPageOverride != null) {
      return fetchPageOverride!(
        limit: limit,
        cursor: cursor,
        eventTypes: eventTypes,
        from: from,
        to: to,
        query: query,
      );
    }
    if (fetchOverride != null) {
      final items = await fetchOverride!(
        limit: limit,
        offset: cursor == null ? 0 : int.tryParse(cursor) ?? 0,
        eventTypeFilter: eventTypes.isEmpty ? null : eventTypes.first.apiValue,
      );
      return ActivityLogPage(items: items);
    }

    final params = <String, String>{'limit': '$limit'};
    if (cursor != null) params['cursor'] = cursor;
    if (eventTypes.isNotEmpty) {
      params['event_type'] = eventTypes.map((e) => e.apiValue).join(',');
    }
    if (from != null) params['from'] = from.toUtc().toIso8601String();
    if (to != null) params['to'] = to.toUtc().toIso8601String();
    if (query.trim().isNotEmpty) params['q'] = query.trim();

    final token = await TaskService.accessTokenProvider?.call();
    final client = httpClientOverride ?? http.Client();
    late http.Response response;
    try {
      response = await client.get(
        Uri.parse('$baseUrl/activity-log').replace(queryParameters: params),
        headers: <String, String>{
          if (token != null && token.isNotEmpty)
            'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
      ).timeout(const Duration(seconds: 10));
    } catch (_) {
      throw const ActivityLogException(
        'Activity log is temporarily unavailable. Please try again.',
        retryable: true,
      );
    }
    if (response.statusCode == 401) {
      throw const ActivityLogException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
        statusCode: 401,
      );
    }
    if (response.statusCode == 422) {
      throw const ActivityLogException(
        'The selected filters are invalid.',
        statusCode: 422,
      );
    }
    if (response.statusCode == 429) {
      throw const ActivityLogException(
        'Activity log is rate limited. Please try again shortly.',
        retryable: true,
        statusCode: 429,
      );
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ActivityLogException(
        'Could not load activity. Please try again.',
        retryable: true,
        statusCode: response.statusCode,
      );
    }
    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      final rows = (decoded['items'] as List<dynamic>? ?? const <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .map(_fromJson)
          .toList();
      return ActivityLogPage(
        items: _dedupeAndSort(rows),
        nextCursor: decoded['next_cursor'] as String?,
      );
    } catch (_) {
      throw const ActivityLogException(
        'The server returned invalid activity data.',
      );
    }
  }

  static Future<List<ActivityLogEntry>> fetchActivityLog({
    int limit = 100,
    int offset = 0,
    String? eventTypeFilter,
  }) async {
    final types = eventTypeFilter == null
        ? const <LogEventType>{}
        : <LogEventType>{LogEventTypePresentation.fromApi(eventTypeFilter)};
    return (await fetchPage(
      limit: limit,
      cursor: offset == 0 ? null : '$offset',
      eventTypes: types,
    ))
        .items;
  }

  static ActivityLogEntry _fromJson(Map<String, dynamic> json) {
    final rawType = json['event_type'] as String? ?? 'error';
    final rawPayload = json['payload'];
    final payload = rawPayload is Map<String, dynamic>
        ? _safePayload(rawPayload)
        : <String, dynamic>{};
    final type = LogEventTypePresentation.fromApi(rawType);
    final decision = payload['decision']?.toString();
    final tool = payload['tool_name']?.toString() ??
        payload['tool']?.toString() ??
        json['agent_name']?.toString() ??
        'Activity';
    final title = switch (type) {
      LogEventType.planCreated => 'Plan created',
      LogEventType.riskTagged => 'Risk assessed for $tool',
      LogEventType.approvalRequested => '$tool awaiting approval',
      LogEventType.approvalDecided => '$tool ${decision ?? 'decided'}',
      LogEventType.toolCalled => '$tool called',
      LogEventType.toolResult => '$tool result',
      LogEventType.error => 'Activity error',
    };
    final description = payload['description']?.toString() ??
        payload['summary']?.toString() ??
        payload['message']?.toString() ??
        switch (type) {
          LogEventType.approvalDecided =>
            'Approval decision: ${decision ?? 'unknown'}.',
          LogEventType.error => 'An error was recorded by the agent.',
          _ => 'Recorded by ${json['agent_name'] ?? 'the agent'}.',
        };
    final agent = json['agent_name']?.toString();
    return ActivityLogEntry(
      id: json['id']?.toString() ?? 'unknown-${json.hashCode}',
      eventType: type,
      title: title,
      description: description,
      timestamp:
          DateTime.tryParse(json['created_at']?.toString() ?? '')?.toLocal() ??
              DateTime.fromMillisecondsSinceEpoch(0),
      agentName: agent,
      taskId: json['task_id']?.toString(),
      stepId: json['step_id']?.toString(),
      integration:
          agent?.startsWith('mcp_') == true ? agent!.substring(4) : null,
      riskTier: switch (payload['risk_tier']) {
        'low' => RiskTier.low,
        'medium' => RiskTier.medium,
        'high' => RiskTier.high,
        _ => null,
      },
      decision: decision,
      payload: payload,
    );
  }

  static Map<String, dynamic> _safePayload(Map<String, dynamic> raw) {
    const secretWords = <String>{
      'token',
      'access_token',
      'refresh_token',
      'secret',
      'password',
      'api_key',
      'authorization',
    };
    return Map<String, dynamic>.fromEntries(raw.entries.where((entry) {
      final key = entry.key.toLowerCase();
      return !secretWords.any(key.contains);
    }));
  }

  static List<ActivityLogEntry> _dedupeAndSort(
      Iterable<ActivityLogEntry> values) {
    final byId = <String, ActivityLogEntry>{};
    for (final value in values) {
      byId[value.id] ??= value;
    }
    final result = byId.values.toList();
    result.sort((a, b) {
      final time = b.timestamp.compareTo(a.timestamp);
      return time != 0 ? time : b.id.compareTo(a.id);
    });
    return result;
  }
}
