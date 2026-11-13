import 'dart:convert';

import 'package:http/http.dart' as http;

import '../auth/auth_service.dart';

class SettingsService {
  static const String baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static Future<Map<String, dynamic>> fetchProfile() async {
    final token = await AuthService.getAccessToken();
    var response = await http.Client().get(
      Uri.parse('$baseUrl/me'),
      headers: {
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 401) {
      // refreshSession is a static method, so we call it directly.
      try {
        await AuthService.refreshSession();
        final refreshedToken = await AuthService.getAccessToken();
        response = await http.Client().get(
          Uri.parse('$baseUrl/me'),
          headers: {
            if (refreshedToken != null && refreshedToken.isNotEmpty)
              'Authorization': 'Bearer $refreshedToken',
            'Content-Type': 'application/json',
          },
        );
      } catch (_) {
        rethrow;
      }
    }

    if (response.statusCode == 200) {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      return decoded;
    }

    final detail = _readDetail(response.body);
    throw Exception(detail.isNotEmpty ? detail : 'Failed to load profile');
  }

  static Future<void> deleteAccount() async {
    final token = await AuthService.getAccessToken();
    var response = await http.Client().delete(
      Uri.parse('$baseUrl/me/account?confirm=true'),
      headers: {
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 401) {
      try {
        await AuthService.refreshSession();
        final refreshedToken = await AuthService.getAccessToken();
        response = await http.Client().delete(
          Uri.parse('$baseUrl/me/account?confirm=true'),
          headers: {
            if (refreshedToken != null && refreshedToken.isNotEmpty)
              'Authorization': 'Bearer $refreshedToken',
            'Content-Type': 'application/json',
          },
        );
      } catch (_) {
        rethrow;
      }
    }

    if (response.statusCode != 204) {
      final detail = _readDetail(response.body);
      throw Exception(detail.isNotEmpty ? detail : 'Failed to delete account');
    }

    await AuthService.logout();
  }

  static String _readDetail(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'];
        if (detail is String && detail.isNotEmpty) return detail;
      }
    } catch (_) {}
    return '';
  }
}
