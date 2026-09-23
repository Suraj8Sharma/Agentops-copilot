import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'core/api_config.dart';
import 'core/theme.dart';
import 'core/router.dart';
import 'features/auth/auth_service.dart';
import 'features/oauth_connections/oauth_connection_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await ApiConfig.loadSavedBaseUrl();

  OAuthConnectionService.authorizationUrlHandler = (Uri uri) async {
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  };

  // Re-attach the token providers to TaskService after a cold start
  // so the first fetch on HomeScreen carries the stored access token.
  await AuthService.restoreSession();

  runApp(const AgentOpsApp());
}

class AgentOpsApp extends StatelessWidget {
  const AgentOpsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AgentOps Copilot',
      theme: AppTheme.light,
      initialRoute: AppRoutes.onboarding,
      onGenerateRoute: AppRouter.generateRoute,
    );
  }
}
