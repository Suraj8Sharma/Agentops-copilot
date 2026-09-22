// AgentOps Copilot — navigation shell / routing skeleton.
//
// Owner: Ishani. Day 2 — route names + onGenerateRoute wiring for
// all 17 pages in the Section 6 inventory. Screens are stubs today;
// each owner replaces their screen's body on their assigned day
// (Manual §14) without touching this file's route table.

import 'package:flutter/material.dart';

import '../features/onboarding/onboarding_screen.dart';
import '../features/home/home_screen.dart';
import '../features/task_composer/task_composer_screen.dart';
import '../features/plan_view/plan_view_screen.dart';
import '../features/approval/approval_screen.dart';
import '../features/oauth_connections/oauth_connections_screen.dart';
import '../features/trust_dashboard/trust_dashboard_screen.dart';
import '../features/auth/signup_screen.dart';
import '../features/auth/signin_screen.dart';
import '../features/auth/forgot_password_screen.dart';
import '../features/voice_input/voice_input_screen.dart';
import '../features/activity_log/activity_log_screen.dart';
import '../features/notifications/notifications_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/memory_prefs/memory_prefs_screen.dart';
import '../features/manual_todo/manual_todo_screen.dart';
import '../features/digest/digest_screen.dart';

/// Route name constants — reference these, never a raw string, so a
/// typo'd route name is a compile error instead of a runtime crash.
class AppRoutes {
  AppRoutes._();

  static const String onboarding = '/onboarding';
  static const String home = '/home';
  static const String taskComposer = '/task-composer';
  static const String planView = '/plan-view';
  static const String approval = '/approval';
  static const String oauthConnections = '/oauth-connections';
  static const String trustDashboard = '/trust-dashboard';
  static const String signUp = '/sign-up';
  static const String signIn = '/sign-in';
  static const String forgotPassword = '/forgot-password';
  static const String voiceInput = '/voice-input';
  static const String activityLog = '/activity-log';
  static const String notifications = '/notifications';
  static const String settings = '/settings';
  static const String memoryPrefs = '/memory-prefs';
  static const String manualTodo = '/manual-todo';
  static const String digest = '/digest';
}

class AppRouter {
  AppRouter._();

  static Route<dynamic> generateRoute(RouteSettings settings) {
    switch (settings.name) {
      case AppRoutes.onboarding:
        return _page(const OnboardingScreen(), settings);
      case AppRoutes.home:
        return _page(const HomeScreen(), settings);
      case AppRoutes.taskComposer:
        return _page(const TaskComposerScreen(), settings);
      case AppRoutes.planView:
        final taskId = settings.arguments as String?;
        return _page(PlanViewScreen(taskId: taskId ?? ''), settings);
      case AppRoutes.approval:
        return _page(const ApprovalScreen(), settings);
      case AppRoutes.oauthConnections:
        return _page(const OAuthConnectionsScreen(), settings);
      case AppRoutes.trustDashboard:
        return _page(const TrustDashboardScreen(), settings);
      case AppRoutes.signUp:
        return _page(const SignUpScreen(), settings);
      case AppRoutes.signIn:
        return _page(const SignInScreen(), settings);
      case AppRoutes.forgotPassword:
        return _page(const ForgotPasswordScreen(), settings);
      case AppRoutes.voiceInput:
        return _page(const VoiceInputScreen(), settings);
      case AppRoutes.activityLog:
        return _page(const ActivityLogScreen(), settings);
      case AppRoutes.notifications:
        return _page(const NotificationsScreen(), settings);
      case AppRoutes.settings:
        return _page(const SettingsScreen(), settings);
      case AppRoutes.memoryPrefs:
        return _page(const MemoryPrefsScreen(), settings);
      case AppRoutes.manualTodo:
        return _page(const ManualTodoScreen(), settings);
      case AppRoutes.digest:
        return _page(const DigestScreen(), settings);
      default:
        return _page(
          Scaffold(
            body: Center(
              child: Text('No route defined for "${settings.name}"'),
            ),
          ),
          settings,
        );
    }
  }

  static MaterialPageRoute<dynamic> _page(
    Widget child,
    RouteSettings settings,
  ) {
    return MaterialPageRoute(builder: (_) => child, settings: settings);
  }
}
