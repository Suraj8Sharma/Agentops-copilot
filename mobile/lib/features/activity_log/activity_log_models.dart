// Activity Log — data model + mock dataset.
//
// LogEventType maps to real MCP tool call event types that will come
// from the backend's plan_steps / audit table in a future sprint.
// Mock data covers all event types so every filter chip gets results.

import 'package:flutter/material.dart';
import '../../core/theme.dart';

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

enum LogEventType {
  toolCall,      // Any MCP tool was called (auto-executed, low risk)
  approval,      // A step required and received human approval
  rejection,     // A step was rejected by the user
  taskCreated,   // A new task was submitted
  taskCompleted, // A task finished successfully
  taskFailed,    // A task failed
}

extension LogEventTypePresentation on LogEventType {
  String get label {
    switch (this) {
      case LogEventType.toolCall:
        return 'Tool Call';
      case LogEventType.approval:
        return 'Approved';
      case LogEventType.rejection:
        return 'Rejected';
      case LogEventType.taskCreated:
        return 'Task Created';
      case LogEventType.taskCompleted:
        return 'Task Completed';
      case LogEventType.taskFailed:
        return 'Task Failed';
    }
  }

  // Short label used in filter chips.
  String get chipLabel {
    switch (this) {
      case LogEventType.toolCall:
        return 'Tool Calls';
      case LogEventType.approval:
        return 'Approvals';
      case LogEventType.rejection:
        return 'Rejections';
      case LogEventType.taskCreated:
        return 'Tasks';
      case LogEventType.taskCompleted:
        return 'Completed';
      case LogEventType.taskFailed:
        return 'Failed';
    }
  }

  Color get color {
    switch (this) {
      case LogEventType.toolCall:
        return AppColors.primary;
      case LogEventType.approval:
        return AppColors.riskLow;
      case LogEventType.rejection:
        return AppColors.riskHigh;
      case LogEventType.taskCreated:
        return AppColors.info;
      case LogEventType.taskCompleted:
        return AppColors.success;
      case LogEventType.taskFailed:
        return AppColors.error;
    }
  }

  Color get backgroundColor {
    switch (this) {
      case LogEventType.toolCall:
        return AppColors.primaryLight;
      case LogEventType.approval:
        return AppColors.riskLowBg;
      case LogEventType.rejection:
        return AppColors.riskHighBg;
      case LogEventType.taskCreated:
        return const Color(0xFFE4F0FC);
      case LogEventType.taskCompleted:
        return AppColors.riskLowBg;
      case LogEventType.taskFailed:
        return AppColors.riskHighBg;
    }
  }

  IconData get icon {
    switch (this) {
      case LogEventType.toolCall:
        return Icons.build_circle_outlined;
      case LogEventType.approval:
        return Icons.thumb_up_alt_outlined;
      case LogEventType.rejection:
        return Icons.block_outlined;
      case LogEventType.taskCreated:
        return Icons.add_task_outlined;
      case LogEventType.taskCompleted:
        return Icons.check_circle_outline;
      case LogEventType.taskFailed:
        return Icons.error_outline;
    }
  }
}

// ---------------------------------------------------------------------------
// Model
// ---------------------------------------------------------------------------

class ActivityLogEntry {
  const ActivityLogEntry({
    required this.id,
    required this.eventType,
    required this.title,
    required this.description,
    required this.timestamp,
    this.integration,
    this.taskId,
    this.riskTier,
  });

  final String id;
  final LogEventType eventType;

  /// Short headline shown in the list (e.g. "gmail.send_message called").
  final String title;

  /// One-line human-readable description of what happened.
  final String description;

  final DateTime timestamp;

  /// MCP integration name (gmail, calendar, github, slack, etc.).
  /// Null for task-level events.
  final String? integration;

  /// Task this event belongs to (optional — used for deep linking later).
  final String? taskId;

  /// Risk tier — present only for tool call events.
  final RiskTier? riskTier;
}

// ---------------------------------------------------------------------------
// Mock dataset
// ---------------------------------------------------------------------------

final List<ActivityLogEntry> mockActivityLog = <ActivityLogEntry>[
  ActivityLogEntry(
    id: 'log-001',
    eventType: LogEventType.taskCreated,
    title: 'Task created',
    description: 'Prepare a weekly team update email and share with the group.',
    timestamp: DateTime(2026, 9, 20, 9, 0),
    taskId: 'task-001',
  ),
  ActivityLogEntry(
    id: 'log-002',
    eventType: LogEventType.toolCall,
    title: 'calendar.list_events called',
    description: 'Fetched 12 events from your calendar for the next 7 days.',
    timestamp: DateTime(2026, 9, 20, 9, 1),
    integration: 'calendar',
    taskId: 'task-001',
    riskTier: RiskTier.low,
  ),
  ActivityLogEntry(
    id: 'log-003',
    eventType: LogEventType.toolCall,
    title: 'gmail.search_messages called',
    description: 'Found 8 unread threads matching "team update".',
    timestamp: DateTime(2026, 9, 20, 9, 2),
    integration: 'gmail',
    taskId: 'task-001',
    riskTier: RiskTier.medium,
  ),
  ActivityLogEntry(
    id: 'log-004',
    eventType: LogEventType.approval,
    title: 'gmail.send_message approved',
    description: 'You approved sending the weekly update email to the team.',
    timestamp: DateTime(2026, 9, 20, 9, 5),
    integration: 'gmail',
    taskId: 'task-001',
    riskTier: RiskTier.high,
  ),
  ActivityLogEntry(
    id: 'log-005',
    eventType: LogEventType.toolCall,
    title: 'gmail.send_message called',
    description: 'Sent weekly update email to 5 recipients.',
    timestamp: DateTime(2026, 9, 20, 9, 6),
    integration: 'gmail',
    taskId: 'task-001',
    riskTier: RiskTier.high,
  ),
  ActivityLogEntry(
    id: 'log-006',
    eventType: LogEventType.taskCompleted,
    title: 'Task completed',
    description: 'Weekly team update task finished successfully.',
    timestamp: DateTime(2026, 9, 20, 9, 7),
    taskId: 'task-001',
  ),
  ActivityLogEntry(
    id: 'log-007',
    eventType: LogEventType.taskCreated,
    title: 'Task created',
    description: 'Open a GitHub PR for the auth branch and request a review.',
    timestamp: DateTime(2026, 9, 20, 14, 30),
    taskId: 'task-002',
  ),
  ActivityLogEntry(
    id: 'log-008',
    eventType: LogEventType.toolCall,
    title: 'github.list_repos called',
    description: 'Listed 14 repositories in your GitHub account.',
    timestamp: DateTime(2026, 9, 20, 14, 31),
    integration: 'github',
    taskId: 'task-002',
    riskTier: RiskTier.low,
  ),
  ActivityLogEntry(
    id: 'log-009',
    eventType: LogEventType.rejection,
    title: 'github.create_pull_request rejected',
    description: 'You rejected opening a PR on the main branch.',
    timestamp: DateTime(2026, 9, 20, 14, 35),
    integration: 'github',
    taskId: 'task-002',
    riskTier: RiskTier.high,
  ),
  ActivityLogEntry(
    id: 'log-010',
    eventType: LogEventType.taskFailed,
    title: 'Task failed',
    description: 'GitHub PR task could not complete — PR creation was rejected.',
    timestamp: DateTime(2026, 9, 20, 14, 36),
    taskId: 'task-002',
  ),
  ActivityLogEntry(
    id: 'log-011',
    eventType: LogEventType.toolCall,
    title: 'slack.post_message called',
    description: 'Posted a standup summary to #engineering channel.',
    timestamp: DateTime(2026, 9, 20, 17, 0),
    integration: 'slack',
    taskId: 'task-003',
    riskTier: RiskTier.medium,
  ),
  ActivityLogEntry(
    id: 'log-012',
    eventType: LogEventType.taskCompleted,
    title: 'Task completed',
    description: 'Daily standup post sent to Slack successfully.',
    timestamp: DateTime(2026, 9, 20, 17, 1),
    taskId: 'task-003',
  ),
];
