import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/api_config.dart';
import '../auth/auth_service.dart';

class MemoryPrefsService {
  static String get baseUrl => ApiConfig.baseUrl;

  // Test hooks
  static Future<Map<String, dynamic>> Function()? fetchPreferencesOverride;
  static Future<void> Function(String key, dynamic value, double confidence, String source)?
      savePreferenceOverride;
  static Future<void> Function(String key)? deletePreferenceOverride;
  static http.Client? httpClientOverride;

  static Future<http.Response> _requestWithAuthRetry(
    Future<http.Response> Function(String? token) request,
  ) async {
    var token = await AuthService.getAccessToken();
    var response = await request(token).timeout(
      const Duration(seconds: 10),
      onTimeout: () => throw Exception('Connection timed out. Please try again.'),
    );

    if (response.statusCode == 401) {
      await AuthService.refreshSession();
      token = await AuthService.getAccessToken();
      response = await request(token).timeout(
        const Duration(seconds: 10),
        onTimeout: () => throw Exception('Connection timed out. Please try again.'),
      );
    }

    return response;
  }

  static Future<Map<String, dynamic>> fetchPreferences() async {
    if (fetchPreferencesOverride != null) {
      return fetchPreferencesOverride!();
    }

    final response = await _requestWithAuthRetry((token) {
      return (httpClientOverride ?? http.Client()).get(
        Uri.parse('$baseUrl/me/preferences'),
        headers: {
          if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
      );
    });

    if (response.statusCode == 200) {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) return decoded;
      return {};
    }

    throw Exception(_readDetail(response.body, 'Failed to load memory preferences'));
  }

  static Future<void> savePreference(
    String key,
    dynamic value, {
    double confidence = 0.8,
    String source = 'user_stated_in_settings',
  }) async {
    if (savePreferenceOverride != null) {
      return savePreferenceOverride!(key, value, confidence, source);
    }

    final response = await _requestWithAuthRetry((token) {
      return (httpClientOverride ?? http.Client()).put(
        Uri.parse('$baseUrl/me/preferences/${Uri.encodeComponent(key)}'),
        headers: {
          if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'value': value,
          'confidence': confidence,
          'source': source,
        }),
      );
    });

    if (response.statusCode != 200) {
      throw Exception(_readDetail(response.body, 'Failed to save preference'));
    }
  }

  static Future<void> deletePreference(String key) async {
    if (deletePreferenceOverride != null) {
      return deletePreferenceOverride!(key);
    }

    final response = await _requestWithAuthRetry((token) {
      return (httpClientOverride ?? http.Client()).delete(
        Uri.parse('$baseUrl/me/preferences/${Uri.encodeComponent(key)}'),
        headers: {
          if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
      );
    });

    if (response.statusCode != 200 && response.statusCode != 204) {
      throw Exception(_readDetail(response.body, 'Failed to delete preference'));
    }
  }

  static String _readDetail(String body, String fallback) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'];
        if (detail is String && detail.isNotEmpty) return detail;
      }
    } catch (_) {}
    return fallback;
  }
}
