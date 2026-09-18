import re

with open('mobile/test/oauth_connections_test.dart', 'r') as f:
    content = f.read()

# Replace the generic test name with the three specific test names
if "renders provider-specific failure states and expiry flag" in content:
    # We will split this big test into smaller ones or just rename it.
    pass

# Let's just create a new test script that adds these explicit tests
new_tests = """
  testWidgets('test_oauth_scope_mismatch_disables_feature_gracefully', (tester) async {
    TaskService.httpClientOverride = MockClient((request) async {
      return http.Response(
        jsonEncode({
          'connections': [
            {'provider': 'slack', 'status': 'scope_mismatch'},
          ],
        }),
        200,
      );
    });

    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    expect(find.text('Limited access'), findsOneWidget);
    expect(find.byKey(const Key('scope-mismatch-slack')), findsOneWidget);
    expect(find.text('Slack messaging is unavailable until access is restored.'), findsOneWidget);
  });

  testWidgets('test_oauth_7day_testing_mode_expiry_is_flagged', (tester) async {
    final tomorrow = DateTime.now().toUtc().add(const Duration(days: 1));
    TaskService.httpClientOverride = MockClient((request) async {
      return http.Response(
        jsonEncode({
          'connections': [
            {
              'provider': 'google_calendar',
              'status': 'active',
              'scopes': ['calendar.events'],
              'expires_at': tomorrow.toIso8601String(),
            },
          ],
        }),
        200,
      );
    });

    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('google-testing-mode-expiry-flag')), findsOneWidget);
  });
"""

# Insert before the last closing brace
content = content[:content.rfind('}')] + new_tests + "}\n"
with open('mobile/test/oauth_connections_test.dart', 'w') as f:
    f.write(content)
