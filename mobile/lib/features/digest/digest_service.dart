import 'dart:convert';

import 'package:http/http.dart' as http;

import '../home/task_service.dart';
import 'digest_models.dart';

class DigestServiceException implements Exception {
  const DigestServiceException(this.message, {this.requiresSignIn = false});
  final String message;
  final bool requiresSignIn;

  @override
  String toString() => message;
}

class DigestService {
  static const String baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  // Test seam — override in widget tests
  static Future<DigestList> Function({String? periodType, int limit, int offset})?
      fetchDigestsOverride;
  static http.Client? httpClientOverride;

  static Future<String?> _getToken() =>
      TaskService.accessTokenProvider?.call() ?? Future.value(null);

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  /// Fetch digests for the current user.
  ///
  /// [periodType] — optional filter: "daily" | "weekly" | null (both)
  /// [limit]      — max rows per page (1–100, default 20)
  /// [offset]     — pagination cursor (default 0)
  static Future<DigestList> fetchDigests({
    String? periodType,
    int limit = 20,
    int offset = 0,
  }) async {
    if (fetchDigestsOverride != null) {
      return fetchDigestsOverride!(
          periodType: periodType, limit: limit, offset: offset);
    }

    var token = await _getToken();
    var response = await _get(token, periodType: periodType, limit: limit, offset: offset);

    // Transparent token refresh on 401
    if (response.statusCode == 401 &&
        TaskService.refreshAccessTokenProvider != null) {
      token = await TaskService.refreshAccessTokenProvider!();
      if (token == null || token.isEmpty) throw _sessionExpired();
      response = await _get(token, periodType: periodType, limit: limit, offset: offset);
    }

    if (response.statusCode == 401) throw _sessionExpired();

    if (response.statusCode == 200) {
      try {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return DigestList.fromJson(decoded);
      } catch (_) {
        throw const DigestServiceException('Server returned invalid digest data.');
      }
    }

    // Extract detail from error body if available
    String detail = 'Failed to load digests (HTTP ${response.statusCode})';
    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      if (decoded['detail'] is String) detail = decoded['detail'] as String;
    } catch (_) {}
    throw DigestServiceException(detail);
  }

  // -------------------------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------------------------

  static Future<http.Response> _get(
    String? token, {
    String? periodType,
    required int limit,
    required int offset,
  }) {
    final params = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (periodType != null) 'period_type': periodType,
    };
    final uri = Uri.parse('$baseUrl/digests').replace(queryParameters: params);
    return (httpClientOverride ?? http.Client()).get(
      uri,
      headers: <String, String>{
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );
  }

  static DigestServiceException _sessionExpired() =>
      const DigestServiceException(
        'Your session has expired. Please sign in again.',
        requiresSignIn: true,
      );
}
