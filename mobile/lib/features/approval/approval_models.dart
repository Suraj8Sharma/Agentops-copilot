import '../../core/theme.dart';

class ApprovalStep {
  const ApprovalStep({
    required this.id,
    this.taskId = '',
    required this.toolName,
    required this.mcpServer,
    required this.riskTier,
    required this.requiresApproval,
    required this.status,
    this.inputParams = const <String, dynamic>{},
    this.explanationText,
  });

  final String id;
  final String taskId;
  final String toolName;
  final String mcpServer;
  final RiskTier riskTier;
  final bool requiresApproval;
  final String status;
  final Map<String, dynamic> inputParams;
  final String? explanationText;

  factory ApprovalStep.fromJson(Map<String, dynamic> json) {
    final rawParams = json['input_params'];
    final risk = json['risk_tier'] as String?;
    return ApprovalStep(
      id: json['step_id'] as String? ?? json['id'] as String,
      taskId: json['task_id'] as String? ?? '',
      toolName: json['tool_name'] as String? ?? 'Unknown action',
      mcpServer: json['mcp_server'] as String? ?? 'Unknown integration',
      riskTier: risk == 'low'
          ? RiskTier.low
          : risk == 'medium'
              ? RiskTier.medium
              : RiskTier.high,
      requiresApproval: json['requires_approval'] as bool? ?? true,
      status: json['status'] as String? ?? 'awaiting_approval',
      inputParams: rawParams is Map<String, dynamic>
          ? rawParams
          : const <String, dynamic>{},
      explanationText: json['explanation_text'] as String?,
    );
  }
}

enum ApprovalDecision { approved, rejected }
