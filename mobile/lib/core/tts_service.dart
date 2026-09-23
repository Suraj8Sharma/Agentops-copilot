import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class TtsService {
  TtsService._();

  static const String keyTtsEnabled = 'tts_enabled';
  static const String keyTtsSpeechRate = 'tts_speech_rate';
  static const String keyTtsLanguage = 'tts_language';
  static const String keyTtsAutoSpeakApprovals = 'tts_auto_speak_approvals';

  static bool _internalIsSpeaking = false;
  static String? _lastSpokenUtterance;

  /// Test hooks
  static Future<void> Function(String text, {String? language, double? rate})? speakOverride;
  static Future<void> Function()? stopOverride;
  static bool Function()? isSpeakingOverride;

  static bool get isSpeaking {
    if (isSpeakingOverride != null) return isSpeakingOverride!();
    return _internalIsSpeaking;
  }

  static String? get lastSpokenUtterance => _lastSpokenUtterance;

  /// Sanitizes raw text / JSON / markdown into natural, clear speech.
  static String sanitizeTextForSpeech(String rawText) {
    if (rawText.trim().isEmpty) return '';

    var text = rawText;

    // Remove markdown links: [link text](url) -> link text
    text = text.replaceAllMapped(
      RegExp(r'\[([^\]]+)\]\([^\)]+\)'),
      (match) => match.group(1) ?? '',
    );

    // Remove code blocks and inline code
    text = text.replaceAll(RegExp(r'```[\s\S]*?```'), ' Code block omitted. ');
    text = text.replaceAllMapped(RegExp(r'`([^`]+)`'), (m) => m.group(1) ?? '');

    // Remove markdown headers, bullets, bold/italic markers
    text = text.replaceAll(RegExp(r'^#+\s*', multiLine: true), '');
    text = text.replaceAll(RegExp(r'[\*\_\~]+'), '');
    text = text.replaceAll(RegExp(r'^[>\-\*\+]\s*', multiLine: true), ' ');

    // Strip long UUIDs / token hashes / hex strings
    text = text.replaceAll(
      RegExp(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'),
      '',
    );
    text = text.replaceAll(RegExp(r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'), '');

    // Remove raw URLs (excluding trailing sentence punctuation)
    text = text.replaceAll(RegExp(r'https?:\/\/[^\s]+'), '');

    // Collapse multiple whitespace/newlines
    text = text.replaceAll(RegExp(r'\s+'), ' ').trim();

    return text;
  }

  /// Synthesizes speech for the provided text if TTS is enabled.
  static Future<void> speak(
    String rawText, {
    String? language,
    double? rate,
  }) async {
    final cleanText = sanitizeTextForSpeech(rawText);
    if (cleanText.isEmpty) return;

    final prefs = await SharedPreferences.getInstance();
    final isEnabled = prefs.getBool(keyTtsEnabled) ?? true;
    if (!isEnabled) return;

    final effectiveRate = rate ?? prefs.getDouble(keyTtsSpeechRate) ?? 1.0;
    final effectiveLang = language ?? prefs.getString(keyTtsLanguage) ?? 'en-US';

    // Stop any existing utterance before starting new one
    await stop();

    _internalIsSpeaking = true;
    _lastSpokenUtterance = cleanText;

    if (speakOverride != null) {
      await speakOverride!(cleanText, language: effectiveLang, rate: effectiveRate);
      return;
    }

    // Platform / Web speech synthesis execution
    try {
      debugPrint('[TTS] Speaking: "$cleanText" [lang=$effectiveLang, rate=$effectiveRate]');
      // Simulated playback tick for standard Flutter runtime without native plugin
      Timer(Duration(milliseconds: (cleanText.length * 50).clamp(500, 5000)), () {
        _internalIsSpeaking = false;
      });
    } catch (e) {
      debugPrint('[TTS] Speech synthesis error: $e');
      _internalIsSpeaking = false;
    }
  }

  /// Stops current speech synthesis immediately.
  static Future<void> stop() async {
    _internalIsSpeaking = false;
    if (stopOverride != null) {
      await stopOverride!();
      return;
    }
    debugPrint('[TTS] Stopped speech synthesis.');
  }

  // ---------------------------------------------------------------------------
  // Preferences Helpers
  // ---------------------------------------------------------------------------

  static Future<bool> isTtsEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(keyTtsEnabled) ?? true;
  }

  static Future<void> setTtsEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(keyTtsEnabled, enabled);
    if (!enabled) {
      await stop();
    }
  }

  static Future<double> getSpeechRate() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getDouble(keyTtsSpeechRate) ?? 1.0;
  }

  static Future<void> setSpeechRate(double rate) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setDouble(keyTtsSpeechRate, rate);
  }

  static Future<bool> isAutoSpeakApprovalsEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(keyTtsAutoSpeakApprovals) ?? false;
  }

  static Future<void> setAutoSpeakApprovals(bool autoSpeak) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(keyTtsAutoSpeakApprovals, autoSpeak);
  }

  static Future<String> getLanguage() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(keyTtsLanguage) ?? 'en-US';
  }

  static Future<void> setLanguage(String lang) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(keyTtsLanguage, lang);
  }
}
