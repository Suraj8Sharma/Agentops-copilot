import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/router.dart';
import '../../core/theme.dart';

/// Static onboarding flow for D3. The completion flag is deliberately an
/// input so a persisted profiles.onboarding_completed value can be connected
/// later without changing the flow itself.
class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, this.onboardingCompleted = false});

  final bool onboardingCompleted;

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
      _splashTimer = Timer(Duration.zero, _goToSignIn);
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

  void _goToSignIn() {
    if (!mounted || _hasNavigated) return;
    _hasNavigated = true;
    Navigator.of(context).pushReplacementNamed(AppRoutes.signIn);
  }

  void _next() {
    if (_pageIndex == _slides.length - 1) return _goToSignIn();
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
        backgroundColor: AppColors.neutral900,
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.lg),
                child: Image.asset(
                  'assets/logo/app_logo.png',
                  width: 96,
                  height: 96,
                  fit: BoxFit.contain,
                  errorBuilder: (context, error, stackTrace) => Container(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    decoration: BoxDecoration(
                      color: AppColors.primaryLight,
                      borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
                    ),
                    child: const Icon(Icons.auto_awesome,
                        color: AppColors.primary, size: AppSpacing.xl),
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.lg),
              Text(
                'AgentOps Copilot',
                style: AppTypography.textTheme.headlineMedium!
                    .copyWith(color: AppColors.neutral0, fontWeight: FontWeight.bold),
              ),
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
