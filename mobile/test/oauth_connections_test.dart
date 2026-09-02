import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';
import 'package:agentops_copilot/features/oauth_connections/oauth_connections_screen.dart';

Widget _screen() => MaterialApp(
      theme: AppTheme.light,
      home: const OAuthConnectionsScreen(),
    );

void main() {
  testWidgets(
      'test_oauth_connections_shows_correct_connect_state_per_provider',
      (tester) async {
    await tester.pumpWidget(_screen());

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

  testWidgets('connect and disconnect are local state toggles', (tester) async {
    await tester.pumpWidget(_screen());

    await tester.tap(find.byKey(const Key('connect-btn-gmail')));
    await tester.pump(const Duration(milliseconds: 301));
    expect(find.text('Can draft and send email on your behalf'), findsOneWidget);
    expect(find.byKey(const Key('disconnect-btn-gmail')), findsOneWidget);

    await tester.tap(find.byKey(const Key('disconnect-btn-gmail')));
    await tester.pump(const Duration(milliseconds: 301));
    expect(find.text('Can draft and send email on your behalf'), findsNothing);
    expect(find.byKey(const Key('connect-btn-gmail')), findsOneWidget);
  });

  testWidgets('action is disabled while the mock operation is in flight',
      (tester) async {
    await tester.pumpWidget(_screen());

    await tester.tap(find.byKey(const Key('connect-btn-slack')));
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 301));
    expect(find.text('Can post messages in one connected workspace'),
        findsOneWidget);
  });

  testWidgets('screen is registered in the app navigation shell', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      initialRoute: AppRoutes.oauthConnections,
      onGenerateRoute: AppRouter.generateRoute,
    ));

    expect(find.byType(OAuthConnectionsScreen), findsOneWidget);
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
}
