import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/router.dart';
import '../../core/theme.dart';
import '../../core/widgets/app_logo.dart';

/// Service managing onboarding completion state.
class OnboardingService {
  static Future<void> Function()? completeOnboardingOverride;

  static Future<void> markCompleted() async {
    if (completeOnboardingOverride != null) {
      await completeOnboardingOverride!();
    }
  }
}

/// Static onboarding flow for D3. The completion flag is deliberately an
/// input so a persisted profiles.onboarding_completed value can be connected
/// later without changing the flow itself.
class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, this.onboardingCompleted = false});

  final bool onboardingCompleted;

  /// Optional override hook for simulating permission prompt request/response.
  static Future<bool> Function()? requestPermissionsOverride;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  static const Duration _splashDuration = Duration(milliseconds: 800);
  final PageController _pageController = PageController();
  Timer? _splashTimer;
  int _pageIndex = 0;
  bool _showSplash = true;
  bool _hasNavigated = false;

  static const List<_OnboardingSlide> _slides = <_OnboardingSlide>[
    _OnboardingSlide(Icons.auto_awesome, 'Your work, with a copilot',
        'AgentOps plans and runs tasks across the tools you already use.'),
    _OnboardingSlide(Icons.verified_user_outlined, 'You stay in control',
        'You\'ll always be asked before a risky action runs. Nothing happens in the dark.'),
    _OnboardingSlide(Icons.hub_outlined, 'Connect your tools next',
        'When you\'re ready, you\'ll be asked to connect Calendar, Gmail, GitHub, and Slack.'),
  ];

  @override
  void initState() {
    super.initState();
    if (widget.onboardingCompleted) {
      _splashTimer = Timer(Duration.zero, () {
        if (!mounted || _hasNavigated) return;
        _hasNavigated = true;
        Navigator.of(context).pushReplacementNamed(AppRoutes.signIn);
      });
    } else {
      _splashTimer = Timer(_splashDuration, () {
        if (mounted) setState(() => _showSplash = false);
      });
    }
  }

  @override
  void dispose() {
    _splashTimer?.cancel();
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _goToSignIn() async {
    if (!mounted || _hasNavigated) return;
    _hasNavigated = true;
    await OnboardingService.markCompleted();
    if (!mounted) return;
    Navigator.of(context).pushReplacementNamed(AppRoutes.signIn);
  }

  Future<void> _showPermissionPrimingModal() async {
    final granted = await showModalBottomSheet<bool>(
      context: context,
      isDismissible: true,
      builder: (context) => const PermissionPrimingSheet(),
    );
    if (!mounted) return;
    if (granted == true && OnboardingScreen.requestPermissionsOverride != null) {
      await OnboardingScreen.requestPermissionsOverride!();
    }
    await _goToSignIn();
  }

  void _next() {
    if (_pageIndex == _slides.length - 1) {
      _showPermissionPrimingModal();
      return;
    }
    _pageController.nextPage(
        duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
  }

  @override
  Widget build(BuildContext context) {
    if (_showSplash) return const _SplashView();
    return Scaffold(
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) => Padding(
            padding: const EdgeInsets.all(AppSpacing.screenPadding),
            child: Column(
              children: <Widget>[
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                      onPressed: _goToSignIn, child: const Text('Skip')),
                ),
                Expanded(
                  child: PageView.builder(
                    controller: _pageController,
                    itemCount: _slides.length,
                    onPageChanged: (index) =>
                        setState(() => _pageIndex = index),
                    itemBuilder: (context, index) =>
                        _SlideView(slide: _slides[index]),
                  ),
                ),
                _PageIndicator(
                    currentPage: _pageIndex, pageCount: _slides.length),
                const SizedBox(height: AppSpacing.lg),
                SizedBox(
                  width: constraints.maxWidth,
                  child: ElevatedButton(
                    onPressed: _next,
                    child: Text(_pageIndex == _slides.length - 1
                        ? 'Get Started'
                        : 'Next'),
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SplashView extends StatelessWidget {
  const _SplashView();

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: AppColors.primary,
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const AppLogoBadge(
                key: Key('app-logo-splash'),
                size: 72,
                padding: AppSpacing.md,
              ),
              const SizedBox(height: AppSpacing.md),
              Text('AgentOps Copilot',
                  style: AppTypography.textTheme.headlineMedium!
                      .copyWith(color: AppColors.neutral0)),
            ],
          ),
        ),
      );
}

class _SlideView extends StatelessWidget {
  const _SlideView({required this.slide});
  final _OnboardingSlide slide;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              const SizedBox(height: AppSpacing.xxl),
              Container(
                padding: const EdgeInsets.all(AppSpacing.xl),
                decoration: const BoxDecoration(
                    color: AppColors.primaryLight, shape: BoxShape.circle),
                child: Icon(slide.icon,
                    color: AppColors.primary, size: AppSpacing.xxl),
              ),
              const SizedBox(height: AppSpacing.xxl),
              Text(slide.title,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: AppSpacing.md),
              Text(slide.body,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge),
              const SizedBox(height: AppSpacing.xl),
            ],
          ),
        ),
      );
}

class PermissionPrimingSheet extends StatelessWidget {
  const PermissionPrimingSheet({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.screenPadding),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            'Permissions',
            style: theme.textTheme.headlineSmall,
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            'AgentOps works best with microphone and notifications enabled:',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: [
              const Icon(Icons.mic, color: AppColors.primary),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  'Microphone: to capture hands-free voice tasks.',
                  style: theme.textTheme.bodySmall,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              const Icon(Icons.notifications_active_outlined,
                  color: AppColors.primary),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  'Notifications: to alert you when a task needs approval.',
                  style: theme.textTheme.bodySmall,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              key: const Key('allow-permissions'),
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Allow permissions'),
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          SizedBox(
            width: double.infinity,
            child: TextButton(
              key: const Key('deny-permissions'),
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Not now'),
            ),
          ),
        ],
      ),
    );
  }
}

class _PageIndicator extends StatelessWidget {
  const _PageIndicator({required this.currentPage, required this.pageCount});
  final int currentPage;
  final int pageCount;

  @override
  Widget build(BuildContext context) => Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: List<Widget>.generate(
          pageCount,
          (index) => AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            margin: const EdgeInsets.symmetric(horizontal: AppSpacing.xs),
            width: index == currentPage ? AppSpacing.lg : AppSpacing.sm,
            height: AppSpacing.sm,
            decoration: BoxDecoration(
              color: index == currentPage
                  ? AppColors.primary
                  : AppColors.neutral300,
              borderRadius: BorderRadius.circular(AppSpacing.sm),
            ),
          ),
        ),
      );
}

class _OnboardingSlide {
  const _OnboardingSlide(this.icon, this.title, this.body);
  final IconData icon;
  final String title;
  final String body;
}
