import 'package:flutter/material.dart';

import '../../core/router.dart';
import '../../core/theme.dart';
import 'auth_service.dart';
import 'auth_widgets.dart';

class SignUpScreen extends StatefulWidget {
  const SignUpScreen({super.key});

  @override
  State<SignUpScreen> createState() => _SignUpScreenState();
}

class _SignUpScreenState extends State<SignUpScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _confirmCtrl = TextEditingController();
  bool _obscurePassword = true;
  bool _obscureConfirm = true;
  bool _isLoading = false;
  String? _errorMessage;

  // Tracks whether sign-up succeeded but email confirmation is required
  // (Supabase may return empty tokens in that case).
  bool _awaitingEmailConfirmation = false;

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    _confirmCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      await AuthService.signup(
        email: _emailCtrl.text.trim(),
        password: _passwordCtrl.text,
      );

      // Check token before using context across async gap.
      final token = await AuthService.getAccessToken();

      if (!mounted) return;

      // If Supabase returned a real token → go straight to home.
      // Empty token = email confirmation required → show notice.
      if (token != null && token.isNotEmpty) {
        Navigator.of(context).pushNamedAndRemoveUntil(
          AppRoutes.home,
          (_) => false,
        );
      } else {
        setState(() => _awaitingEmailConfirmation = true);
      }
    } on AuthException catch (e) {
      if (mounted) setState(() => _errorMessage = e.message);
    } catch (_) {
      if (mounted) {
        setState(
            () => _errorMessage = 'Something went wrong. Please try again.');
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;

    // ── Email confirmation notice ─────────────────────────────────────────
    if (_awaitingEmailConfirmation) {
      return Scaffold(
        appBar: AppBar(
        title: const Text('Sign Up'),
        backgroundColor: AppColors.neutral0,
        foregroundColor: AppColors.neutral900,
        elevation: 0,
      ),
      body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.screenPadding),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                const SizedBox(height: AppSpacing.xxl),
                const AuthHeader(
                  icon: Icons.mark_email_read_outlined,
                  title: 'Check your inbox',
                  subtitle: 'We sent a confirmation link to your email address. '
                      'Open it to activate your account, then sign in.',
                ),
                const SizedBox(height: AppSpacing.xl),
                ElevatedButton(
                  onPressed: () => Navigator.of(context)
                      .pushReplacementNamed(AppRoutes.signIn),
                  child: const Text('Go to Sign In'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    // ── Sign-up form ──────────────────────────────────────────────────────
    return Scaffold(
      appBar: AppBar(
        title: const Text('Sign Up'),
        backgroundColor: AppColors.neutral0,
        foregroundColor: AppColors.neutral900,
        elevation: 0,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.screenPadding),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              const SizedBox(height: AppSpacing.xxl),

              const AuthHeader(
                icon: Icons.person_add_outlined,
                title: 'Create account',
                subtitle: 'Start automating with your personal copilot.',
              ),
              const SizedBox(height: AppSpacing.xxl),

              Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    // Email
                    TextFormField(
                      key: const Key('signup-email'),
                      controller: _emailCtrl,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.next,
                      autocorrect: false,
                      decoration: const InputDecoration(
                        labelText: 'Email address',
                        prefixIcon: Icon(Icons.email_outlined),
                      ),
                      validator: (v) {
                        if (v == null || v.trim().isEmpty) {
                          return 'Please enter your email.';
                        }
                        if (!v.contains('@')) return 'Enter a valid email.';
                        return null;
                      },
                    ),
                    const SizedBox(height: AppSpacing.md),

                    // Password
                    TextFormField(
                      key: const Key('signup-password'),
                      controller: _passwordCtrl,
                      obscureText: _obscurePassword,
                      textInputAction: TextInputAction.next,
                      decoration: InputDecoration(
                        labelText: 'Password',
                        helperText: 'Minimum 6 characters.',
                        prefixIcon: const Icon(Icons.lock_outlined),
                        suffixIcon: IconButton(
                          tooltip: _obscurePassword
                              ? 'Show password'
                              : 'Hide password',
                          icon: Icon(_obscurePassword
                              ? Icons.visibility_outlined
                              : Icons.visibility_off_outlined),
                          onPressed: () => setState(
                              () => _obscurePassword = !_obscurePassword),
                        ),
                      ),
                      validator: (v) {
                        if (v == null || v.isEmpty) {
                          return 'Please enter a password.';
                        }
                        if (v.length < 6) {
                          return 'Password must be at least 6 characters.';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: AppSpacing.md),

                    // Confirm password
                    TextFormField(
                      key: const Key('signup-confirm'),
                      controller: _confirmCtrl,
                      obscureText: _obscureConfirm,
                      textInputAction: TextInputAction.done,
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'Confirm password',
                        prefixIcon: const Icon(Icons.lock_outlined),
                        suffixIcon: IconButton(
                          tooltip: _obscureConfirm
                              ? 'Show password'
                              : 'Hide password',
                          icon: Icon(_obscureConfirm
                              ? Icons.visibility_outlined
                              : Icons.visibility_off_outlined),
                          onPressed: () => setState(
                              () => _obscureConfirm = !_obscureConfirm),
                        ),
                      ),
                      validator: (v) {
                        if (v != _passwordCtrl.text) {
                          return 'Passwords do not match.';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: AppSpacing.md),

                    // Error banner
                    if (_errorMessage != null) ...<Widget>[
                      AuthErrorBanner(message: _errorMessage!),
                      const SizedBox(height: AppSpacing.md),
                    ],

                    // Sign-up button
                    ElevatedButton(
                      key: const Key('signup-submit'),
                      onPressed: _isLoading ? null : _submit,
                      child: _isLoading
                          ? const AuthButtonSpinner()
                          : const Text('Create account'),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.xl),

              // Footer
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  Text('Already have an account?', style: tt.bodyMedium),
                  TextButton(
                    onPressed: () => Navigator.of(context)
                        .pushReplacementNamed(AppRoutes.signIn),
                    child: const Text('Sign in'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}