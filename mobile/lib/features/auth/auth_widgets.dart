/// Shared small widgets used across the auth screens.
/// Kept in one file so signin, signup, and forgot-password screens
/// can all import them without circular dependencies.

library;

import 'package:flutter/material.dart';
import '../../core/theme.dart';

/// Branded header with icon, title and subtitle — used at the top of
/// every auth screen.
class AuthHeader extends StatelessWidget {
  const AuthHeader({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Container(
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: BoxDecoration(
            color: AppColors.primaryLight,
            borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
          ),
          child: Icon(icon, color: AppColors.primary, size: AppSpacing.xl),
        ),
        const SizedBox(height: AppSpacing.md),
        Text(title, style: tt.headlineMedium),
        const SizedBox(height: AppSpacing.xs),
        Text(subtitle, style: tt.bodyMedium),
      ],
    );
  }
}

/// Red banner shown below the form when an auth error occurs.
class AuthErrorBanner extends StatelessWidget {
  const AuthErrorBanner({super.key, required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.riskHighBg,
        borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
        border: Border.all(color: AppColors.riskHigh),
      ),
      child: Row(
        children: <Widget>[
          const Icon(Icons.error_outline, color: AppColors.riskHigh, size: 18),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              message,
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: AppColors.riskHigh),
            ),
          ),
        ],
      ),
    );
  }
}

/// Loading spinner sized for use inside an ElevatedButton.
class AuthButtonSpinner extends StatelessWidget {
  const AuthButtonSpinner({super.key});

  @override
  Widget build(BuildContext context) => const SizedBox(
        height: 18,
        width: 18,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          color: AppColors.neutral0,
        ),
      );
}

