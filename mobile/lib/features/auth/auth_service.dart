// AuthService — thin client over the FastAPI /auth/* endpoints.
//
// Responsibilities:
//   - POST /auth/signup   → store tokens on success
//   - POST /auth/login    → store tokens on success
//   - POST /auth/refresh  → exchange refresh token for a new pair
//   - logout              → clear persisted tokens
//   - accessToken getter  → used by TaskService before each request
//
// Token storage uses SharedPreferences (device keychain-adjacent storage).
// The keys are intentionally simple strings so tests can override them.

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../home/task_service.dart';

class AuthException implements Exception {
  const AuthException(this.message);
  final String message;
  @override
  String toString() => message;
}

class AuthService {
  AuthService._();

  // -------------------------------------------------------------------------
  // Config — mirrors TaskService.baseUrl so we share the same host.
  // -------------------------------------------------------------------------
  static const String _baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  // SharedPreferences keys
  static const String _keyAccessToken = 'auth_access_token';
  static const String _keyRefreshToken = 'auth_refresh_token';

  // -------------------------------------------------------------------------
  // Token accessors
  // -------------------------------------------------------------------------

  static Future<String?> getAccessToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyAccessToken);
  }

  static Future<String?> getRefreshToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyRefreshToken);
  }

  static Future<bool> isLoggedIn() async {
    final token = await getAccessToken();
    return token != null && token.isNotEmpty;
  }

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  static Future<void> _saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyAccessToken, accessToken);
    await prefs.setString(_keyRefreshToken, refreshToken);
    // Wire TaskService so future requests carry the token automatically.
    TaskService.accessTokenProvider = getAccessToken;
    TaskService.refreshAccessTokenProvider = _refreshAndGet;
  }

  static Future<String?> _refreshAndGet() async {
    try {
      await refreshSession();
      return getAccessToken();
    } catch (_) {
      return null;
    }
  }

  static String _extractDetail(http.Response response) {
    try {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      final detail = body['detail'];
      if (detail is String && detail.isNotEmpty) return detail;
    } catch (_) {}
    return 'Unexpected error (HTTP ${response.statusCode})';
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  /// Sign up with [email] and [password].
  /// Stores the returned token pair so the user is immediately signed in.
  static Future<void> signup({
    required String email,
    required String password,
  }) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/auth/signup'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );

    if (response.statusCode == 201) {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      await _saveTokens(
        accessToken: body['access_token'] as String? ?? '',
        refreshToken: body['refresh_token'] as String? ?? '',
      );
      return;
    }

    throw AuthException(_extractDetail(response));
  }

  /// Sign in with [email] and [password].
  /// Stores the returned token pair.
  static Future<void> login({
    required String email,
    required String password,
  }) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );

    if (response.statusCode == 200) {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      await _saveTokens(
        accessToken: body['access_token'] as String? ?? '',
        refreshToken: body['refresh_token'] as String? ?? '',
      );
      return;
    }

    throw AuthException(_extractDetail(response));
  }

  /// Exchange the stored refresh token for a fresh token pair.
  static Future<void> refreshSession() async {
    final refreshToken = await getRefreshToken();
    if (refreshToken == null || refreshToken.isEmpty) {
      throw const AuthException('No refresh token — please sign in again.');
    }

    final response = await http.post(
      Uri.parse('$_baseUrl/auth/refresh'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'refresh_token': refreshToken}),
    );

    if (response.statusCode == 200) {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      await _saveTokens(
        accessToken: body['access_token'] as String? ?? '',
        refreshToken: body['refresh_token'] as String? ?? '',
      );
      return;
    }

    throw const AuthException('Session expired. Please sign in again.');
  }

  /// Clear stored tokens and detach the TaskService providers.
  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyAccessToken);
    await prefs.remove(_keyRefreshToken);
    TaskService.accessTokenProvider = null;
    TaskService.refreshAccessTokenProvider = null;
  }

  /// Re-attach the token providers to TaskService after a cold start,
  /// if the user is already logged in. Call this once from [main].
  static Future<void> restoreSession() async {
    if (await isLoggedIn()) {
      TaskService.accessTokenProvider = getAccessToken;
      TaskService.refreshAccessTokenProvider = _refreshAndGet;
    }
  }
}
