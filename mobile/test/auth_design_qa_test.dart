import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agentops_copilot/core/router.dart';
import 'package:agentops_copilot/core/theme.dart';

void main() {
  const authScreens = <String, String>{
    AppRoutes.signUp: 'Sign Up',
    AppRoutes.signIn: 'Sign In',
    AppRoutes.forgotPassword: 'Forgot Password / OTP',
  };

  for (final entry in authScreens.entries) {
    testWidgets('${entry.value} keeps the shared auth shell contract',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
        theme: AppTheme.light,
        onGenerateRoute: AppRouter.generateRoute,
        initialRoute: entry.key,
      ));
      await tester.pumpAndSettle();

      expect(find.text(entry.value), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('auth shells use the D1 AppTheme and shared AppBar treatment',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      onGenerateRoute: AppRouter.generateRoute,
      initialRoute: AppRoutes.signIn,
    ));
    await tester.pumpAndSettle();

    final appBar = tester.widget<AppBar>(find.byType(AppBar));
    expect(appBar.backgroundColor, AppColors.neutral0);
    expect(appBar.foregroundColor, AppColors.neutral900);
    expect(appBar.elevation, 0);
  });
}
