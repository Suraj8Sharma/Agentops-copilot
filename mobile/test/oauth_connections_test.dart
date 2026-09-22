import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/home/task_service.dart';
import 'package:agentops_copilot/features/oauth_connections/oauth_connections_screen.dart';

Widget _screen() => MaterialApp(
      theme: AppTheme.light,
      home: const OAuthConnectionsScreen(),
    );

void main() {
  setUp(() {
    var gmailConnected = false;
    TaskService.accessTokenProvider = () async => 'fake-token';
    TaskService.httpClientOverride = MockClient((request) async {
      if (request.method == 'GET' && request.url.path.endsWith('/oauth/connections')) {
        return http.Response(
          jsonEncode({
            'connections': [
              {
                'provider': 'google_calendar',
                'status': 'active',
                'scopes': ['calendar.events'],
                'connected_at': '2026-08-20T00:00:00Z',
              },
              {
                'provider': 'github',
                'status': 'active',
                'scopes': ['repo'],
                'connected_at': '2026-08-22T00:00:00Z',
              },
              if (gmailConnected)
                {
                  'provider': 'gmail',
                  'status': 'active',
                  'scopes': ['gmail.send', 'gmail.compose'],
                  'connected_at': '2026-08-22T00:00:00Z',
                },
            ],
          }),
          200,
        );
      }
      if (request.method == 'GET' && request.url.path.contains('/connect')) {
        gmailConnected = true;
        return http.Response(
          jsonEncode({'authorization_url': 'https://example.com/auth'}),
          200,
        );
      }
      if (request.method == 'DELETE') {
        gmailConnected = false;
        return http.Response(jsonEncode({'message': 'ok'}), 200);
      }
      return http.Response('Not Found', 404);
    });
  });

  testWidgets(
      'test_oauth_connections_shows_correct_connect_state_per_provider',
      (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle(); // Wait for fetch

    expect(find.text('Google Calendar'), findsOneWidget);
    expect(find.text('Gmail'), findsOneWidget);
    expect(find.text('GitHub'), findsOneWidget);
    expect(find.text('Slack'), findsOneWidget);
    expect(find.text('Connected'), findsNWidgets(2));
    expect(find.text('Not Connected'), findsNWidgets(2));
    expect(find.text('Disconnect'), findsNWidgets(2));
    expect(find.text('Connect'), findsNWidgets(2));
    expect(find.text('Can view and create calendar events'), findsOneWidget);
    expect(find.text('Can create issues and comments on your repos'),
        findsOneWidget);
    expect(find.textContaining('Connected since'), findsNWidgets(2));
  });

  testWidgets('connect and disconnect use the backend state', (tester) async {
    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('connect-btn-gmail')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.text('Can draft and send email on your behalf'), findsOneWidget);
    expect(find.byKey(const Key('disconnect-btn-gmail')), findsOneWidget);

    await tester.tap(find.byKey(const Key('disconnect-btn-gmail')));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.text('Can draft and send email on your behalf'), findsNothing);
    expect(find.byKey(const Key('connect-btn-gmail')), findsOneWidget);
  });

  testWidgets('action is disabled while the mock operation is in flight',
      (tester) async {
    // We delay the client manually to test loading state
    TaskService.httpClientOverride = MockClient((request) async {
      if (request.method == 'GET' && request.url.path.endsWith('/oauth/connections')) {
        return http.Response(jsonEncode({'connections': []}), 200);
      }
      await Future.delayed(const Duration(milliseconds: 100));
      return http.Response(
        jsonEncode({'authorization_url': 'https://example.com/auth'}),
        200,
      );
    });

    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('connect-btn-slack')));
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pumpAndSettle();
    expect(find.text('Can post messages in one connected workspace'), findsNothing);
    expect(find.byKey(const Key('connect-btn-slack')), findsOneWidget);
  });

  testWidgets('screen is registered in the app navigation shell', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      initialRoute: AppRoutes.oauthConnections,
      onGenerateRoute: AppRouter.generateRoute,
    ));

    await tester.pumpAndSettle();
    expect(find.byType(OAuthConnectionsScreen), findsOneWidget);
  });

  testWidgets('renders provider-specific failure states and expiry flag',
      (tester) async {
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
            {
              'provider': 'gmail',
              'status': 'expired',
              'failure_reason': 'Gmail needs consent again after token expiry.',
              'failed_operation': 'gmail_send',
            },
            {'provider': 'github', 'status': 'revoked'},
            {'provider': 'slack', 'status': 'scope_mismatch'},
          ],
        }),
        200,
      );
    });

    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    expect(find.text('Connected'), findsOneWidget);
    expect(find.text('Expired - reconnect required'), findsOneWidget);
    expect(find.text('Revoked - reconnect required'), findsOneWidget);
    expect(find.text('Limited access'), findsOneWidget);
    expect(find.byKey(const Key('google-testing-mode-expiry-flag')),
        findsOneWidget);
    expect(find.text('Gmail needs consent again after token expiry.'),
        findsOneWidget);
    expect(find.text('Re-authenticate before sending this email.'),
        findsOneWidget);
    expect(find.byKey(const Key('scope-mismatch-slack')), findsOneWidget);
  });

  testWidgets('Gmail draft failure says saved, not sent without re-auth prompt',
      (tester) async {
    TaskService.httpClientOverride = MockClient((request) async {
      return http.Response(
        jsonEncode({
          'connections': [
            {
              'provider': 'gmail',
              'status': 'expired',
              'failed_operation': 'gmail_draft',
            },
          ],
        }),
        200,
      );
    });

    await tester.pumpWidget(_screen());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('gmail-draft-fallback')), findsOneWidget);
    expect(find.text('Re-authenticate before sending this email.'), findsNothing);
  });

  test('mock model exposes the oauth_connections row shape', () {
    const connection = OAuthConnectionModel(
      provider: OAuthProvider.gmail,
      status: OAuthStatus.active,
    );

    expect(connection.provider, OAuthProvider.gmail);
    expect(connection.status, OAuthStatus.active);
    expect(connection.scopes, isEmpty);
    expect(connection.expiresAt, isNull);
    expect(connection.connectedAt, isNull);
  });

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
}
