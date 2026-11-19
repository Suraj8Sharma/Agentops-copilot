import 'package:flutter/material.dart';

import '../theme.dart';

/// Shared app logo widget.
///
/// Uses the branded image asset and falls back to a safe icon if the asset
/// is missing at runtime.
class AppLogoBadge extends StatelessWidget {
  const AppLogoBadge({
    super.key,
    this.size = 72,
    this.padding = AppSpacing.sm,
    this.backgroundColor,
    this.borderRadius = AppSpacing.cardRadius,
    this.fallbackIcon = Icons.auto_awesome,
  });

  final double size;
  final double padding;
  final Color? backgroundColor;
  final double borderRadius;
  final IconData fallbackIcon;

  static const String assetPath = 'assets/logo/app_logo.png';

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(padding),
      decoration: BoxDecoration(
        color: backgroundColor ?? AppColors.primaryLight,
        borderRadius: BorderRadius.circular(borderRadius),
      ),
      child: SizedBox(
        width: size,
        height: size,
        child: Image.asset(
          assetPath,
          fit: BoxFit.contain,
          errorBuilder: (context, error, stackTrace) => Icon(
            fallbackIcon,
            color: AppColors.primary,
            size: size * 0.6,
          ),
        ),
      ),
    );
  }
}