// AgentOps Copilot — Design Tokens & Theme
//
// Owner: Ishani (Frontend Design Lead & Trust Surfaces)
// Day 1 — colour / type / spacing tokens + Flutter ThemeData setup.
//
// These tokens are deliberately built around the app's core trust loop
// (Plan View, Approval Screen, Trust Dashboard) rather than a generic
// palette: risk tiers (low / medium / high) are first-class colours
// because the whole product exists to make risk legible before an
// action executes (Manual §9, §4.2).

import 'package:flutter/material.dart';

/// -----------------------------------------------------------------------
/// COLOUR TOKENS
/// -----------------------------------------------------------------------
/// Base palette is a calm, low-saturation blue/slate family — chosen so
/// the risk-tier accent colours (which DO need to grab attention) stand
/// out clearly against it instead of competing with a busy brand colour.
class AppColors {
  AppColors._();

  // Brand / primary
  static const Color primary = Color(0xFF3556D6); // confident, calm blue
  static const Color primaryDark = Color(0xFF243B99);
  static const Color primaryLight = Color(0xFFE7EBFB);

  // Secondary / accent (used sparingly — links, active states)
  static const Color secondary = Color(0xFF00A896);

  // Neutrals — slate scale, not pure black/white (softer on long sessions)
  static const Color neutral900 = Color(0xFF14171F); // primary text
  static const Color neutral700 = Color(0xFF3C4256); // secondary text
  static const Color neutral500 = Color(0xFF6B7086); // muted text / icons
  static const Color neutral300 = Color(0xFFD3D6E0); // borders, dividers
  static const Color neutral100 = Color(0xFFF3F4F8); // surface / cards
  static const Color neutral0 = Color(0xFFFFFFFF); // background

  // Risk-tier colours — Manual §9.1: low / medium / high.
  // These MUST stay visually distinct at a glance (colour-blind-safe
  // hues, not just shade variation) since the Approval Screen and Plan
  // View are safety-critical (100% widget-test coverage, Manual §15.2).
  static const Color riskLow = Color(0xFF1E9E5A); // green — auto-executes
  static const Color riskLowBg = Color(0xFFE4F7EC);
  static const Color riskMedium = Color(0xFFB8790A); // amber — reversible
  static const Color riskMediumBg = Color(0xFFFCF0DA);
  static const Color riskHigh = Color(0xFFC62E3E); // red — needs approval
  static const Color riskHighBg = Color(0xFFFBE4E6);

  // Semantic status (task/connection states, distinct from risk tiers)
  static const Color success = riskLow;
  static const Color warning = riskMedium;
  static const Color error = riskHigh;
  static const Color info = Color(0xFF2E7FD1);
}

/// -----------------------------------------------------------------------
/// SPACING TOKENS
/// -----------------------------------------------------------------------
/// 4px base unit, geometric-ish scale. Used for padding, gaps, and
/// margins everywhere instead of literal numbers, so a spacing change
/// is a one-line edit here rather than a grep across every screen.
class AppSpacing {
  AppSpacing._();

  static const double xs = 4.0;
  static const double sm = 8.0;
  static const double md = 16.0;
  static const double lg = 24.0;
  static const double xl = 32.0;
  static const double xxl = 48.0;

  // Common derived values
  static const double screenPadding = md; // default page margin
  static const double cardRadius = 12.0;
  static const double buttonRadius = 10.0;
  static const double iconSize = md;
  static const double progressStrokeWidth = 2.0;
}

/// -----------------------------------------------------------------------
/// TYPOGRAPHY TOKENS
/// -----------------------------------------------------------------------
/// System font for now (no custom font asset committed yet — Jigyasu's
/// logo/asset pass is separate, Manual §3). Sizes/weights are fixed here
/// so every screen pulls from Theme.of(context).textTheme instead of
/// hardcoding a fontSize.
class AppTypography {
  AppTypography._();

  static const String fontFamily = 'Roboto'; // Flutter default; swap here later

  static const TextTheme textTheme = TextTheme(
    displayLarge: TextStyle(
      fontSize: 32,
      fontWeight: FontWeight.w700,
      color: AppColors.neutral900,
      height: 1.2,
    ),
    headlineMedium: TextStyle(
      fontSize: 24,
      fontWeight: FontWeight.w700,
      color: AppColors.neutral900,
      height: 1.25,
    ),
    titleLarge: TextStyle(
      fontSize: 18,
      fontWeight: FontWeight.w600,
      color: AppColors.neutral900,
      height: 1.3,
    ),
    titleMedium: TextStyle(
      fontSize: 16,
      fontWeight: FontWeight.w600,
      color: AppColors.neutral900,
      height: 1.3,
    ),
    bodyLarge: TextStyle(
      fontSize: 16,
      fontWeight: FontWeight.w400,
      color: AppColors.neutral900,
      height: 1.5,
    ),
    bodyMedium: TextStyle(
      fontSize: 14,
      fontWeight: FontWeight.w400,
      color: AppColors.neutral700,
      height: 1.5,
    ),
    labelLarge: TextStyle(
      fontSize: 14,
      fontWeight: FontWeight.w600,
      color: AppColors.neutral0,
      height: 1.2,
    ), // button text
    labelMedium: TextStyle(
      fontSize: 12,
      fontWeight: FontWeight.w600,
      color: AppColors.neutral500,
      height: 1.2,
      letterSpacing: 0.4,
    ), // tags / risk-tier chips
    bodySmall: TextStyle(
      fontSize: 12,
      fontWeight: FontWeight.w400,
      color: AppColors.neutral500,
      height: 1.4,
    ), // captions, timestamps
  );
}

/// -----------------------------------------------------------------------
/// THEME DATA
/// -----------------------------------------------------------------------
/// Single light theme for Day 1. Dark mode is explicitly scheduled later
/// (Sanskriti, D9 — Manual §14) — kept out for now rather than half-built.
class AppTheme {
  AppTheme._();

  static ThemeData get light {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: Brightness.light,
      primary: AppColors.primary,
      secondary: AppColors.secondary,
      error: AppColors.error,
      surface: AppColors.neutral0,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: AppColors.neutral0,
      fontFamily: AppTypography.fontFamily,
      textTheme: AppTypography.textTheme,

      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.neutral0,
        foregroundColor: AppColors.neutral900,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: AppColors.neutral900,
        ),
      ),

      cardTheme: CardThemeData(
        color: AppColors.neutral100,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
          side: const BorderSide(color: AppColors.neutral300, width: 1),
        ),
      ),

      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: AppColors.neutral0,
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg,
            vertical: AppSpacing.sm + AppSpacing.xs,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
          ),
          textStyle: AppTypography.textTheme.labelLarge,
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.primary,
          side: const BorderSide(color: AppColors.neutral300),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg,
            vertical: AppSpacing.sm + AppSpacing.xs,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
          ),
        ),
      ),

      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.neutral100,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm + AppSpacing.xs,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
          borderSide: const BorderSide(color: AppColors.neutral300),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
          borderSide: const BorderSide(color: AppColors.neutral300),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
        ),
      ),

      dividerTheme: const DividerThemeData(
        color: AppColors.neutral300,
        thickness: 1,
        space: AppSpacing.md,
      ),
    );
  }
}

/// -----------------------------------------------------------------------
/// RISK-TIER HELPER
/// -----------------------------------------------------------------------
/// Small helper so every screen that renders a risk tier (Plan View,
/// Approval Screen, Activity Log) pulls colour + label from one place
/// instead of re-implementing a switch statement per screen.
enum RiskTier { low, medium, high }

extension RiskTierStyle on RiskTier {
  Color get color {
    switch (this) {
      case RiskTier.low:
        return AppColors.riskLow;
      case RiskTier.medium:
        return AppColors.riskMedium;
      case RiskTier.high:
        return AppColors.riskHigh;
    }
  }

  Color get background {
    switch (this) {
      case RiskTier.low:
        return AppColors.riskLowBg;
      case RiskTier.medium:
        return AppColors.riskMediumBg;
      case RiskTier.high:
        return AppColors.riskHighBg;
    }
  }

  String get label {
    switch (this) {
      case RiskTier.low:
        return 'LOW RISK';
      case RiskTier.medium:
        return 'MEDIUM RISK';
      case RiskTier.high:
        return 'HIGH RISK';
    }
  }
}
