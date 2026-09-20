import 'package:flutter/material.dart';

import '../../core/router.dart';
import '../../core/theme.dart';
import 'auth_widgets.dart';

/// Forgot-password screen.
///
/// The backend `/auth/reset-password` endpoint is not yet implemented,
/// so this screen captures the email and shows a "check your email"
/// confirmation view. The API call will be wired in a future sprint.
class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  bool _isLoading = false;
  bool _submitted = false;
  String? _errorMessage;

  @override
  void dispose() {
    _emailCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    // TODO: wire to POST /auth/reset-password when the backend endpoint lands.
    // Simulating a short delay to mimic a network call.
    await Future<void>.delayed(const Duration(milliseconds: 600));

    if (mounted) {
      setState(() {
        _isLoading = false;
        _submitted = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;

    // ── Confirmation view ────────────────────────────────────────────────
    if (_submitted) {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Forgot Password / OTP'),
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
                  subtitle: "If an account exists for that email address, we've "
                      'sent a reset link. Check your spam folder too.',
                ),
                const SizedBox(height: AppSpacing.xl),
                ElevatedButton(
                  onPressed: () => Navigator.of(context)
                      .pushReplacementNamed(AppRoutes.signIn),
                  child: const Text('Back to Sign In'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    // ── Email entry form ─────────────────────────────────────────────────
    return Scaffold(
      appBar: AppBar(
        title: const Text('Forgot Password / OTP'),
        backgroundColor: AppColors.neutral0,
        foregroundColor: AppColors.neutral900,
        elevation: 0,
        leading: const BackButton(),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.screenPadding),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              const SizedBox(height: AppSpacing.lg),
              Text(
                "Enter the email address associated with your account "
                "and we'll send you a reset link.",
                style: tt.bodyMedium,
              ),
              const SizedBox(height: AppSpacing.xl),

              Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    TextFormField(
                      key: const Key('forgot-email'),
                      controller: _emailCtrl,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.done,
                      autocorrect: false,
                      onFieldSubmitted: (_) => _submit(),
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

                    if (_errorMessage != null) ...<Widget>[
                      AuthErrorBanner(message: _errorMessage!),
                      const SizedBox(height: AppSpacing.md),
                    ],

                    ElevatedButton(
                      key: const Key('forgot-submit'),
                      onPressed: _isLoading ? null : _submit,
                      child: _isLoading
                          ? const AuthButtonSpinner()
                          : const Text('Send reset link'),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}