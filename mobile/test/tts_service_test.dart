import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:agentops_copilot/core/tts_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    TtsService.speakOverride = null;
    TtsService.stopOverride = null;
    TtsService.isSpeakingOverride = null;
  });

  group('TtsService - Text Sanitization', () {
    test('sanitizes markdown headers, bold, and bullet points', () {
      const input = '# Plan Summary\n- **Step 1**: Run `git status`\n- **Step 2**: Deploy app';
      final clean = TtsService.sanitizeTextForSpeech(input);
      expect(clean, contains('Plan Summary'));
      expect(clean, contains('Step 1: Run git status'));
      expect(clean, contains('Step 2: Deploy app'));
      expect(clean.contains('#'), isFalse);
      expect(clean.contains('**'), isFalse);
    });

    test('replaces markdown links with link text', () {
      const input = 'Check out [Supabase Docs](https://supabase.com/docs) for details.';
      final clean = TtsService.sanitizeTextForSpeech(input);
      expect(clean, equals('Check out Supabase Docs for details.'));
      expect(clean.contains('https'), isFalse);
    });

    test('replaces code blocks with natural speech fallback', () {
      const input = 'Run the following command:\n```bash\nnpm install express\n```\nAll done.';
      final clean = TtsService.sanitizeTextForSpeech(input);
      expect(clean, contains('Run the following command: Code block omitted. All done.'));
    });

    test('strips long UUIDs, JWT tokens, and raw URLs', () {
      const input = 'Execution id 123e4567-e89b-12d3-a456-426614174000 completed with token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG5fa2 at https://api.agentops.dev/v1/result.';
      final clean = TtsService.sanitizeTextForSpeech(input);
      expect(clean, equals('Execution id completed with token at'));
    });
  });

  group('TtsService - Speech Control & Preferences', () {
    test('saves and loads TTS settings properly in SharedPreferences', () async {
      await TtsService.setTtsEnabled(false);
      expect(await TtsService.isTtsEnabled(), isFalse);

      await TtsService.setSpeechRate(1.25);
      expect(await TtsService.getSpeechRate(), equals(1.25));

      await TtsService.setLanguage('hi-IN');
      expect(await TtsService.getLanguage(), equals('hi-IN'));

      await TtsService.setAutoSpeakApprovals(true);
      expect(await TtsService.isAutoSpeakApprovalsEnabled(), isTrue);
    });

    test('speak() does nothing if TTS is disabled', () async {
      await TtsService.setTtsEnabled(false);
      var called = false;
      TtsService.speakOverride = (text, {language, rate}) async {
        called = true;
      };

      await TtsService.speak('This should not be spoken');
      expect(called, isFalse);
    });

    test('speak() invokes hook with sanitized text and effective preferences', () async {
      await TtsService.setTtsEnabled(true);
      await TtsService.setSpeechRate(1.5);
      await TtsService.setLanguage('hi-IN');

      String? spokenText;
      String? spokenLang;
      double? spokenRate;

      TtsService.speakOverride = (text, {language, rate}) async {
        spokenText = text;
        spokenLang = language;
        spokenRate = rate;
      };

      await TtsService.speak('**Hello** world!');
      expect(spokenText, equals('Hello world!'));
      expect(spokenLang, equals('hi-IN'));
      expect(spokenRate, equals(1.5));
    });

    test('stop() invokes stop hook and updates speaking state', () async {
      var stopped = false;
      TtsService.stopOverride = () async {
        stopped = true;
      };

      await TtsService.stop();
      expect(stopped, isTrue);
      expect(TtsService.isSpeaking, isFalse);
    });
  });
}
