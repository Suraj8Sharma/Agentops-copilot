import 'dart:convert';

import 'package:http/http.dart' as http;

import '../auth/auth_service.dart';

class MemoryPrefsService {
  static const String baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static Future<Map<String, dynamic>> fetchPreferences() async {
    final token = await AuthService.getAccessToken();
    var response = await http.Client().get(
      Uri.parse('$baseUrl/me/preferences'),
      headers: {
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 401) {
      await AuthService.refreshSession();
      final refreshedToken = await AuthService.getAccessToken();
      response = await http.Client().get(
        Uri.parse('$baseUrl/me/preferences'),
        headers: {
          if (refreshedToken != null && refreshedToken.isNotEmpty)
            'Authorization': 'Bearer $refreshedToken',
          'Content-Type': 'application/json',
        },
      );
    }

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
    final token = await AuthService.getAccessToken();
    var response = await http.Client().put(
      Uri.parse('$baseUrl/me/preferences/$key'),
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

    if (response.statusCode == 401) {
      await AuthService.refreshSession();
      final refreshedToken = await AuthService.getAccessToken();
      response = await http.Client().put(
        Uri.parse('$baseUrl/me/preferences/$key'),
        headers: {
          if (refreshedToken != null && refreshedToken.isNotEmpty)
            'Authorization': 'Bearer $refreshedToken',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'value': value,
          'confidence': confidence,
          'source': source,
        }),
      );
    }

    if (response.statusCode != 200) {
      throw Exception(_readDetail(response.body, 'Failed to save preference'));
    }
  }

  static Future<void> deletePreference(String key) async {
    final token = await AuthService.getAccessToken();
    var response = await http.Client().delete(
      Uri.parse('$baseUrl/me/preferences/$key'),
      headers: {
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 401) {
      await AuthService.refreshSession();
      final refreshedToken = await AuthService.getAccessToken();
      response = await http.Client().delete(
        Uri.parse('$baseUrl/me/preferences/$key'),
        headers: {
          if (refreshedToken != null && refreshedToken.isNotEmpty)
            'Authorization': 'Bearer $refreshedToken',
          'Content-Type': 'application/json',
        },
      );
    }

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
