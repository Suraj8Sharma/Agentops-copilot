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

import '../../core/api_config.dart';
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
  static String get _baseUrl => ApiConfig.baseUrl;

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

  /// Decodes the JWT payload (no network call) and returns true if the token
  /// is expired or within [bufferSeconds] of expiry.
  ///
  /// Returns true (treat as expired) on any parse failure so the caller
  /// falls through to the refresh path rather than using a bad token.
  static bool _isTokenExpired(String jwt, {int bufferSeconds = 60}) {
    try {
      final parts = jwt.split('.');
      if (parts.length != 3) return true;

      // JWT payload is base64url-encoded (no padding).
      final payload = parts[1];
      // Normalise to standard base64 by re-adding padding.
      final normalised = base64.normalize(payload);
      final decoded = utf8.decode(base64Url.decode(normalised));
      final map = jsonDecode(decoded) as Map<String, dynamic>;

      final exp = map['exp'];
      if (exp == null) return false; // no expiry claim → treat as valid

      final expiresAt =
          DateTime.fromMillisecondsSinceEpoch((exp as int) * 1000, isUtc: true);
      return DateTime.now().toUtc().isAfter(
            expiresAt.subtract(Duration(seconds: bufferSeconds)),
          );
    } catch (_) {
      return true; // parse failure → assume expired
    }
  }

  /// Returns true only if a non-empty, non-expired access token is stored.
  ///
  /// Uses [_isTokenExpired] for an offline JWT exp-claim check, so no network
  /// call is needed here. A 401 retry in TaskService is still the safety net
  /// for clock-skew edge cases.
  static Future<bool> isLoggedIn() async {
    final token = await getAccessToken();
    if (token == null || token.isEmpty) return false;
    return !_isTokenExpired(token);
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
      return await getAccessToken();
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

  /// Re-attach the token providers to TaskService after a cold start.
  ///
  /// Three cases on startup:
  ///   1. No token stored          → do nothing (user sees sign-in screen).
  ///   2. Token stored and valid   → wire providers immediately.
  ///   3. Token stored but expired → attempt a silent refresh before wiring.
  ///      If the refresh fails (revoked, no network) → clear storage so the
  ///      user is redirected to sign-in rather than landing in a broken state.
  ///
  /// Call this once from [main] before [runApp].
  static Future<void> restoreSession() async {
    final token = await getAccessToken();
    if (token == null || token.isEmpty) return; // case 1

    if (_isTokenExpired(token)) {
      // case 3 — try silent refresh
      final refreshed = await _refreshAndGet();
      if (refreshed == null) {
        // Refresh failed — clear tokens so app shows sign-in screen.
        await logout();
        return;
      }
    }

    // case 2 (or case 3 after successful refresh)
    TaskService.accessTokenProvider = getAccessToken;
    TaskService.refreshAccessTokenProvider = _refreshAndGet;
  }
}
