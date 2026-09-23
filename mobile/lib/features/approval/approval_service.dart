import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/api_config.dart';
import '../home/task_service.dart';
import 'approval_models.dart';

class ApprovalServiceException implements Exception {
  const ApprovalServiceException(
    this.message, {
    this.requiresSignIn = false,
    this.refreshPending = false,
  });

  final String message;
  final bool requiresSignIn;
  final bool refreshPending;

  @override
  String toString() => message;
}

class ApprovalService {
  static String get baseUrl => ApiConfig.baseUrl;

  static Future<List<ApprovalStep>> Function()? fetchPendingOverride;
  static Future<void> Function(String, ApprovalDecision)? decideOverride;
  static http.Client? httpClientOverride;

  static Future<List<ApprovalStep>> fetchPending() async {
    if (fetchPendingOverride != null) return fetchPendingOverride!();

    var token = await _getToken();
    var response = await _getPending(token);
    if (response.statusCode == 401 &&
        TaskService.refreshAccessTokenProvider != null) {
      token = await TaskService.refreshAccessTokenProvider!();
      if (token == null || token.isEmpty) throw _signInException();
      response = await _getPending(token);
    }
    _throwForStatus(response, operation: 'load pending approvals');

    try {
      final decoded = jsonDecode(response.body);
      final rows =
          decoded is List ? decoded : decoded['approvals'] as List<dynamic>;
      return rows
          .map((row) => ApprovalStep.fromJson(row as Map<String, dynamic>))
          .toList();
    } catch (_) {
      throw const ApprovalServiceException(
          'The server returned invalid approval data.');
    }
  }

  static Future<void> decide(String stepId, ApprovalDecision decision) async {
    if (decideOverride != null) return decideOverride!(stepId, decision);

    var token = await _getToken();
    var response = await _postDecision(stepId, decision, token);
    if (response.statusCode == 401 &&
        TaskService.refreshAccessTokenProvider != null) {
      token = await TaskService.refreshAccessTokenProvider!();
      if (token == null || token.isEmpty) throw _signInException();
      response = await _postDecision(stepId, decision, token);
    }
    _throwForStatus(response, operation: 'record decision');
  }

  static Future<String?> _getToken() =>
      TaskService.accessTokenProvider?.call() ?? Future.value(null);

  static Future<http.Response> _getPending(String? token) =>
      (httpClientOverride ?? http.Client()).get(
        Uri.parse('$baseUrl/approvals/pending'),
        headers: _headers(token),
      );

  static Future<http.Response> _postDecision(
    String stepId,
    ApprovalDecision decision,
    String? token,
  ) =>
      (httpClientOverride ?? http.Client()).post(
        Uri.parse('$baseUrl/approvals/$stepId'),
        headers: _headers(token),
        body: jsonEncode(<String, String>{'decision': decision.name}),
      );

  static Map<String, String> _headers(String? token) => <String, String>{
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      };

  static void _throwForStatus(http.Response response,
      {required String operation}) {
    if (response.statusCode == 401) throw _signInException();
    if (response.statusCode == 404 || response.statusCode == 409) {
      throw const ApprovalServiceException(
        'This approval is no longer pending. Refreshing the list.',
        refreshPending: true,
      );
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      var detail = 'Could not $operation.';
      try {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        if (decoded['detail'] is String) detail = decoded['detail'] as String;
      } catch (_) {}
      throw ApprovalServiceException('$detail (HTTP ${response.statusCode})');
    }
  }

  static ApprovalServiceException _signInException() =>
      const ApprovalServiceException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
      );
}
