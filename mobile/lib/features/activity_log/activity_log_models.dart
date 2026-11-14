import 'package:flutter/material.dart';

import '../../core/theme.dart';

enum LogEventType {
  planCreated,
  riskTagged,
  approvalRequested,
  approvalDecided,
  toolCalled,
  toolResult,
  error,
}

extension LogEventTypePresentation on LogEventType {
  String get apiValue => switch (this) {
        LogEventType.planCreated => 'plan_created',
        LogEventType.riskTagged => 'risk_tagged',
        LogEventType.approvalRequested => 'approval_requested',
        LogEventType.approvalDecided => 'approval_decided',
        LogEventType.toolCalled => 'tool_called',
        LogEventType.toolResult => 'tool_result',
        LogEventType.error => 'error',
      };

  String get label => switch (this) {
        LogEventType.planCreated => 'Plan created',
        LogEventType.riskTagged => 'Risk tagged',
        LogEventType.approvalRequested => 'Approval requested',
        LogEventType.approvalDecided => 'Approval decided',
        LogEventType.toolCalled => 'Tool called',
        LogEventType.toolResult => 'Tool result',
        LogEventType.error => 'Error',
      };

  String get chipLabel => label;

  Color get color => this == LogEventType.error
      ? AppColors.error
      : this == LogEventType.approvalDecided
          ? AppColors.riskLow
          : AppColors.primary;

  Color get backgroundColor => this == LogEventType.error
      ? AppColors.riskHighBg
      : this == LogEventType.approvalDecided
          ? AppColors.riskLowBg
          : AppColors.primaryLight;

  IconData get icon => switch (this) {
        LogEventType.planCreated => Icons.account_tree_outlined,
        LogEventType.riskTagged => Icons.shield_outlined,
        LogEventType.approvalRequested => Icons.gpp_maybe_outlined,
        LogEventType.approvalDecided => Icons.fact_check_outlined,
        LogEventType.toolCalled => Icons.build_circle_outlined,
        LogEventType.toolResult => Icons.check_circle_outline,
        LogEventType.error => Icons.error_outline,
      };

  static LogEventType fromApi(String value) => switch (value) {
        'plan_created' => LogEventType.planCreated,
        'risk_tagged' => LogEventType.riskTagged,
        'approval_requested' => LogEventType.approvalRequested,
        'approval_decided' => LogEventType.approvalDecided,
        'tool_called' => LogEventType.toolCalled,
        'tool_result' => LogEventType.toolResult,
        'error' => LogEventType.error,
        _ => LogEventType.error,
      };
}

class ActivityLogEntry {
  const ActivityLogEntry({
    required this.id,
    required this.eventType,
    required this.title,
    required this.description,
    required this.timestamp,
    this.agentName,
    this.taskId,
    this.stepId,
    this.integration,
    this.riskTier,
    this.decision,
    this.payload = const <String, dynamic>{},
  });

  final String id;
  final LogEventType eventType;
  final String title;
  final String description;
  final DateTime timestamp;
  final String? agentName;
  final String? taskId;
  final String? stepId;
  final String? integration;
  final RiskTier? riskTier;
  final String? decision;
  final Map<String, dynamic> payload;
}
