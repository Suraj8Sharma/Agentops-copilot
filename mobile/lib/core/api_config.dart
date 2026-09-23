import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ApiConfig {
  ApiConfig._();

  static const String keyCustomBaseUrl = 'server_base_url';
  static String? _cachedBaseUrl;

  /// Default development LAN IP for physical device connection
  static const String defaultLanUrl = 'http://10.19.173.243:8000';
  static const String defaultEmulatorUrl = 'http://10.0.2.2:8000';
  static const String defaultLocalhostUrl = 'http://127.0.0.1:8000';

  static String get baseUrl {
    if (_cachedBaseUrl != null && _cachedBaseUrl!.isNotEmpty) {
      return _cachedBaseUrl!;
    }
    const envUrl = String.fromEnvironment('API_URL');
    if (envUrl.isNotEmpty) {
      return envUrl;
    }
    if (kIsWeb) {
      return defaultLocalhostUrl;
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return defaultLocalhostUrl;
      default:
        return defaultLocalhostUrl;
    }
  }

  static Future<void> loadSavedBaseUrl() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString(keyCustomBaseUrl);
      if (saved != null && saved.trim().isNotEmpty) {
        _cachedBaseUrl = saved.trim();
      }
    } catch (_) {}
  }

  static Future<void> setBaseUrl(String url) async {
    final clean = url.trim().replaceAll(RegExp(r'\/+$'), '');
    _cachedBaseUrl = clean;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(keyCustomBaseUrl, clean);
  }

  static Future<void> resetToDefault() async {
    _cachedBaseUrl = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(keyCustomBaseUrl);
  }
}
