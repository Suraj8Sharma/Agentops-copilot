import 'dart:convert';

import 'package:http/http.dart' as http;

import '../home/task_service.dart';

class TrustDashboardException implements Exception {
  const TrustDashboardException(
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

class DashboardMetricPoint {
  const DashboardMetricPoint({required this.label, required this.value});

  final String label;
  final double value;

  factory DashboardMetricPoint.fromJson(Map<String, dynamic> json) {
    final value = json['value'];
    return DashboardMetricPoint(
      label: (json['label'] ?? json['suite_name'] ?? json['provider'] ?? 'N/A')
          .toString(),
      value: value is num ? value.toDouble() : 0.0,
    );
  }
}

class TrustDashboardSummary {
  const TrustDashboardSummary({
    required this.p95Latency,
    required this.totalCost,
    required this.avgAccuracy,
    required this.fallbackEventsCount,
  });

  final double p95Latency;
  final double totalCost;
  final double avgAccuracy;
  final int fallbackEventsCount;

  factory TrustDashboardSummary.fromJson(Map<String, dynamic> json) {
    return TrustDashboardSummary(
      p95Latency: (json['p95_latency'] ?? json['p95Latency'] ?? 0.0) is num
          ? ((json['p95_latency'] ?? json['p95Latency'] ?? 0.0) as num).toDouble()
          : 0.0,
      totalCost: (json['total_cost'] ?? json['totalCost'] ?? 0.0) is num
          ? ((json['total_cost'] ?? json['totalCost'] ?? 0.0) as num).toDouble()
          : 0.0,
      avgAccuracy: (json['avg_accuracy'] ?? json['avgAccuracy'] ?? 0.0) is num
          ? ((json['avg_accuracy'] ?? json['avgAccuracy'] ?? 0.0) as num).toDouble()
          : 0.0,
      fallbackEventsCount: ((json['fallback_events_count'] ??
                  json['fallbackEventsCount'] ??
                  0) as num?)
              ?.toInt() ??
          0,
    );
  }
}

class TrustDashboardMetrics {
  const TrustDashboardMetrics({
    required this.latency,
    required this.cost,
    required this.accuracy,
    this.summary,
    this.generatedAt,
    this.fallbackEvents = 0,
  });

  final List<DashboardMetricPoint> latency;
  final List<DashboardMetricPoint> cost;
  final List<DashboardMetricPoint> accuracy;
  final TrustDashboardSummary? summary;
  final DateTime? generatedAt;
  final int fallbackEvents;

  bool get isEmpty => latency.isEmpty && cost.isEmpty && accuracy.isEmpty;

  static List<DashboardMetricPoint> _coerceSeries(dynamic value) {
    if (value is! List) return const <DashboardMetricPoint>[];
    return value
        .whereType<Map<String, dynamic>>()
        .map(DashboardMetricPoint.fromJson)
        .toList(growable: false);
  }

  factory TrustDashboardMetrics.fromJson(Map<String, dynamic> json) {
    final summary = json['summary'] is Map<String, dynamic>
        ? TrustDashboardSummary.fromJson(json['summary'] as Map<String, dynamic>)
        : null;

    final generatedAt = json['generated_at'] != null
        ? DateTime.tryParse(json['generated_at'].toString())
        : null;

    return TrustDashboardMetrics(
      latency: _coerceSeries(json['latency']),
      cost: _coerceSeries(json['cost']),
      accuracy: _coerceSeries(json['accuracy']),
      summary: summary,
      generatedAt: generatedAt,
      fallbackEvents: ((json['fallback_events'] ??
                  (summary?.fallbackEventsCount ?? 0)) as num?)
              ?.toInt() ??
          0,
    );
  }
}

class TrustDashboardService {
  TrustDashboardService._();

  static Future<TrustDashboardMetrics> Function({int days})? fetchMetricsOverride;
  static http.Client? httpClientOverride;

  static Future<TrustDashboardMetrics> fetchMetrics({int days = 7}) async {
    if (fetchMetricsOverride != null) {
      return fetchMetricsOverride!(days: days);
    }

    final token = await TaskService.accessTokenProvider?.call();
    final client = TaskService.httpClientOverride ?? httpClientOverride ?? http.Client();
    final uri = Uri.parse('${TaskService.baseUrl}/dashboard/metrics')
        .replace(queryParameters: {'days': '$days'});

    late http.Response response;
    try {
      response = await client
          .get(
            uri,
            headers: <String, String>{
              if (token != null && token.isNotEmpty)
                'Authorization': 'Bearer $token',
              'Content-Type': 'application/json',
            },
          )
          .timeout(const Duration(seconds: 10));
    } catch (_) {
      throw const TrustDashboardException(
        'Trust dashboard is temporarily unavailable. Please try again.',
        retryable: true,
      );
    }

    if (response.statusCode == 401) {
      throw const TrustDashboardException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
        statusCode: 401,
      );
    }
    if (response.statusCode == 429) {
      throw const TrustDashboardException(
        'Metrics are rate limited. Please try again shortly.',
        retryable: true,
        statusCode: 429,
      );
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw TrustDashboardException(
        'Could not load dashboard metrics. Please try again.',
        retryable: true,
        statusCode: response.statusCode,
      );
    }

    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      return TrustDashboardMetrics.fromJson(decoded);
    } catch (_) {
      throw const TrustDashboardException(
        'The server returned invalid dashboard data.',
        retryable: true,
      );
    }
  }
}
