import 'dart:convert';
import 'package:http/http.dart' as http;
import '../../features/home/task_service.dart';
import 'oauth_connections_screen.dart';

class OAuthConnectionService {
  static const String baseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// Test seams also make the screen's provider-specific failure states
  /// deterministic without ever putting OAuth tokens in widget fixtures.
  static Future<List<OAuthConnectionModel>> Function()?
      fetchConnectionsOverride;
  static Future<void> Function(OAuthProvider)? disconnectOverride;
  static Future<Uri?> Function(OAuthProvider)? connectOverride;
  static Future<void> Function(Uri)? authorizationUrlHandler;

  static Future<String?> _getToken() async {
    return TaskService.accessTokenProvider?.call();
  }

  static Future<List<OAuthConnectionModel>> fetchConnections() async {
    if (fetchConnectionsOverride != null) {
      return fetchConnectionsOverride!();
    }

    var token = await _getToken();
    var response = await (TaskService.httpClientOverride ?? http.Client()).get(
      Uri.parse('$baseUrl/oauth/connections'),
      headers: {
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 401 && TaskService.refreshAccessTokenProvider != null) {
      token = await TaskService.refreshAccessTokenProvider!();
      response = await (TaskService.httpClientOverride ?? http.Client()).get(
        Uri.parse('$baseUrl/oauth/connections'),
        headers: {
          if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
      );
    }

    if (response.statusCode == 200) {
      final decoded = jsonDecode(response.body);
      final list = decoded['connections'] as List<dynamic>? ?? [];
      
      return list.map((e) {
        final map = e as Map<String, dynamic>;
        return _fromJson(map);
      }).toList();
    } else {
      throw Exception('Failed to load connections');
    }
  }

  static OAuthConnectionModel _fromJson(Map<String, dynamic> json) {
    final providerStr = json['provider'] as String;
    final statusStr = json['status'] as String?;
    
    OAuthProvider provider;
    switch (providerStr) {
      case 'google_calendar':
        provider = OAuthProvider.googleCalendar;
        break;
      case 'gmail':
        provider = OAuthProvider.gmail;
        break;
      case 'github':
        provider = OAuthProvider.github;
        break;
      case 'slack':
        provider = OAuthProvider.slack;
        break;
      default:
        provider = OAuthProvider.github; // fallback
    }

    OAuthStatus? status;
    if (statusStr != null) {
      switch (statusStr) {
        case 'active':
          status = OAuthStatus.active;
          break;
        case 'expired':
        case 'expired_testing_mode':
          status = OAuthStatus.expired;
          break;
        case 'revoked':
          status = OAuthStatus.revoked;
          break;
        case 'scope_mismatch':
          status = OAuthStatus.scopeMismatch;
          break;
        default:
          status = OAuthStatus.active;
      }
    }

    List<String> scopes = [];
    if (json['scopes'] != null) {
      scopes = (json['scopes'] as List).map((e) => e.toString()).toList();
    }

    DateTime? connectedAt;
    if (json['connected_at'] != null) {
      connectedAt = DateTime.tryParse(json['connected_at']);
    }
    
    DateTime? expiresAt;
    if (json['expires_at'] != null) {
      expiresAt = DateTime.tryParse(json['expires_at']);
    }

    return OAuthConnectionModel(
      provider: provider,
      status: status,
      scopes: scopes,
      connectedAt: connectedAt,
      expiresAt: expiresAt,
      reauthReason: _stringValue(json, const [
        'reauth_reason',
        'failure_reason',
        'task_failure_reason',
      ]),
      failedOperation: _stringValue(json, const [
        'failed_operation',
        'failure_context',
        'feature',
      ]),
    );
  }

  static String? _stringValue(
    Map<String, dynamic> json,
    List<String> keys,
  ) {
    for (final key in keys) {
      final value = json[key];
      if (value is String && value.trim().isNotEmpty) return value;
    }
    return null;
  }

  static Future<void> disconnect(OAuthProvider provider) async {
    if (disconnectOverride != null) {
      return disconnectOverride!(provider);
    }

    var token = await _getToken();
    var response = await (TaskService.httpClientOverride ?? http.Client()).delete(
      Uri.parse('$baseUrl/oauth/${provider.key}'),
      headers: {
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 401 && TaskService.refreshAccessTokenProvider != null) {
      token = await TaskService.refreshAccessTokenProvider!();
      response = await (TaskService.httpClientOverride ?? http.Client()).delete(
        Uri.parse('$baseUrl/oauth/${provider.key}'),
        headers: {
          if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
      );
    }

    if (response.statusCode != 200 && response.statusCode != 204) {
      throw Exception('Failed to disconnect');
    }
  }

  static Future<Uri?> connect(OAuthProvider provider) async {
    if (connectOverride != null) {
      return connectOverride!(provider);
    }

    // According to spec: GET /oauth/{provider}/connect
    // Wait, the connect flow redirects the user to the browser!
    // The screen only triggers the flow. It can use url_launcher.
    // "Tapping "connect" on a provider starts the real consent redirect via GET /oauth/{provider}/connect."
    
    var token = await _getToken();
    var response = await (TaskService.httpClientOverride ?? http.Client()).get(
      Uri.parse('$baseUrl/oauth/${provider.key}/connect'),
      headers: {
        if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
    );

    if (response.statusCode == 401 && TaskService.refreshAccessTokenProvider != null) {
      token = await TaskService.refreshAccessTokenProvider!();
      response = await (TaskService.httpClientOverride ?? http.Client()).get(
        Uri.parse('$baseUrl/oauth/${provider.key}/connect'),
        headers: {
          if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
      );
    }

    if (response.statusCode == 200) {
      final decoded = jsonDecode(response.body);
      final authUrl = decoded['authorization_url'] as String?;
      if (authUrl != null) {
        final uri = Uri.tryParse(authUrl);
        if (uri != null && authorizationUrlHandler != null) {
          await authorizationUrlHandler!(uri);
        }
        return uri;
      }
    } else {
      throw Exception('Failed to get authorization url');
    }
    return null;
  }
}
