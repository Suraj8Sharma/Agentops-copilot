import 'package:flutter/material.dart';

import '../../core/api_config.dart';
import '../../core/router.dart';
import '../../core/theme.dart';
import '../../core/tts_service.dart';
import '../auth/auth_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  // AI & Copilot settings
  String _selectedModel = 'gemini-3.7-flash';
  String _autonomyLevel = 'balanced';
  bool _voiceAutoListen = true;
  String _sttLanguage = 'en-US (Auto-detect)';

  // TTS & Voice Feedback
  bool _ttsEnabled = true;
  double _ttsSpeechRate = 1.0;
  bool _ttsAutoSpeakApprovals = false;

  // Notification preferences
  bool _notifyApprovals = true;
  bool _notifyTaskCompletion = true;
  bool _notifyDailyDigest = true;
  TimeOfDay _digestTime = const TimeOfDay(hour: 8, minute: 0);

  // App Theme & Appearance
  ThemeMode _themeMode = ThemeMode.system;

  @override
  void initState() {
    super.initState();
    _loadTtsSettings();
  }

  Future<void> _loadTtsSettings() async {
    final enabled = await TtsService.isTtsEnabled();
    final rate = await TtsService.getSpeechRate();
    final autoSpeak = await TtsService.isAutoSpeakApprovalsEnabled();
    final lang = await TtsService.getLanguage();
    if (mounted) {
      setState(() {
        _ttsEnabled = enabled;
        _ttsSpeechRate = rate;
        _ttsAutoSpeakApprovals = autoSpeak;
        _sttLanguage = lang;
      });
    }
  }

  void _showConfirmLogoutDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Sign Out'),
        content: const Text(
          'Are you sure you want to sign out of AgentOps Copilot? You will need to log in again to access your tasks.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.error),
            onPressed: () async {
              Navigator.pop(ctx);
              await AuthService.logout();
              if (mounted) {
                Navigator.of(context).pushNamedAndRemoveUntil(
                  AppRoutes.signIn,
                  (route) => false,
                );
              }
            },
            child: const Text('Sign Out', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  void _showClearCacheDialog() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Clear Local Cache'),
        content: const Text(
          'This will clear locally cached drafts, audio previews, and temporary logs.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Local cache cleared successfully.'),
                  backgroundColor: AppColors.success,
                ),
              );
            },
            child: const Text('Clear Cache'),
          ),
        ],
      ),
    );
  }

  void _showEditServerUrlDialog() {
    final controller = TextEditingController(text: ApiConfig.baseUrl);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Backend Server URL'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Specify the host and port of your FastAPI backend. '
              'For physical phones on the same Wi-Fi, use your computer LAN IP (e.g. http://10.19.173.243:8000).',
              style: TextStyle(fontSize: 13, color: AppColors.neutral700),
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: controller,
              decoration: const InputDecoration(
                labelText: 'Server URL',
                hintText: 'http://10.19.173.243:8000',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () async {
              Navigator.pop(ctx);
              await ApiConfig.resetToDefault();
              if (mounted) setState(() {});
            },
            child: const Text('Reset Default'),
          ),
          ElevatedButton(
            onPressed: () async {
              final newUrl = controller.text.trim();
              Navigator.pop(ctx);
              if (newUrl.isNotEmpty) {
                await ApiConfig.setBaseUrl(newUrl);
                if (mounted) setState(() {});
              }
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings & Preferences'),
        elevation: 0,
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.screenPadding,
            vertical: AppSpacing.md,
          ),
          children: [
            // -------------------------------------------------------------
            // Profile Card Header
            // -------------------------------------------------------------
            _buildProfileCard(theme),
            const SizedBox(height: AppSpacing.lg),

            // -------------------------------------------------------------
            // Section 1: AI Copilot & Autonomy
            // -------------------------------------------------------------
            _buildSectionHeader('AI Copilot & Planning', Icons.psychology_outlined),
            _buildCardWrapper([
              ListTile(
                leading: const Icon(Icons.smart_toy_outlined, color: AppColors.primary),
                title: const Text('Default LLM Model'),
                subtitle: Text(_getModelLabel(_selectedModel)),
                trailing: const Icon(Icons.arrow_drop_down),
                onTap: _showModelPicker,
              ),
              const Divider(height: 1),
              ListTile(
                leading: const Icon(Icons.shield_outlined, color: AppColors.riskMedium),
                title: const Text('Autonomy Level (HITL)'),
                subtitle: Text(_getAutonomyLabel(_autonomyLevel)),
                trailing: const Icon(Icons.arrow_drop_down),
                onTap: _showAutonomyPicker,
              ),
              const Divider(height: 1),
              ListTile(
                leading: const Icon(Icons.memory_outlined, color: AppColors.secondary),
                title: const Text('Agent Memory & Preferences'),
                subtitle: const Text('Custom persona & context rules'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.pushNamed(context, AppRoutes.memoryPrefs),
              ),
            ]),
            const SizedBox(height: AppSpacing.lg),

            // -------------------------------------------------------------
            // Section 2: Integrations & Connected Tools
            // -------------------------------------------------------------
            _buildSectionHeader('Integrations & Permissions', Icons.hub_outlined),
            _buildCardWrapper([
              ListTile(
                leading: const Icon(Icons.cable_outlined, color: AppColors.primary),
                title: const Text('Connected OAuth Services'),
                subtitle: const Text('Google, GitHub, Slack integration status'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.pushNamed(context, AppRoutes.oauthConnections),
              ),
            ]),
            const SizedBox(height: AppSpacing.lg),

            // -------------------------------------------------------------
            // Section 3: Speech & Voice Pipeline (STT & TTS)
            // -------------------------------------------------------------
            _buildSectionHeader('Speech & Voice Feedback', Icons.record_voice_over_outlined),
            _buildCardWrapper([
              SwitchListTile(
                secondary: const Icon(Icons.mic_outlined, color: AppColors.primary),
                title: const Text('Auto-listen on Voice Screen'),
                subtitle: const Text('Start recording immediately when opening voice modal'),
                value: _voiceAutoListen,
                onChanged: (val) => setState(() => _voiceAutoListen = val),
              ),
              const Divider(height: 1),
              SwitchListTile(
                key: const Key('settings-tts-enabled-switch'),
                secondary: const Icon(Icons.volume_up_outlined, color: AppColors.primary),
                title: const Text('Text-to-Speech (Voice Feedback)'),
                subtitle: const Text('Enable voice read aloud for plans and safety explanations'),
                value: _ttsEnabled,
                onChanged: (val) async {
                  setState(() => _ttsEnabled = val);
                  await TtsService.setTtsEnabled(val);
                },
              ),
              if (_ttsEnabled) ...[
                const Divider(height: 1),
                ListTile(
                  key: const Key('settings-tts-rate-tile'),
                  leading: const Icon(Icons.speed_outlined, color: AppColors.primary),
                  title: const Text('Speech Rate'),
                  subtitle: Text('${_ttsSpeechRate}x speed'),
                  trailing: const Icon(Icons.arrow_drop_down),
                  onTap: _showSpeechRatePicker,
                ),
                const Divider(height: 1),
                SwitchListTile(
                  key: const Key('settings-auto-speak-approvals-switch'),
                  secondary: const Icon(Icons.gavel_outlined, color: AppColors.riskMedium),
                  title: const Text('Auto-speak High-Risk Approvals'),
                  subtitle: const Text('Automatically read safety warnings when approval card appears'),
                  value: _ttsAutoSpeakApprovals,
                  onChanged: (val) async {
                    setState(() => _ttsAutoSpeakApprovals = val);
                    await TtsService.setAutoSpeakApprovals(val);
                  },
                ),
              ],
              const Divider(height: 1),
              ListTile(
                key: const Key('settings-stt-language-tile'),
                leading: const Icon(Icons.translate_outlined, color: AppColors.primary),
                title: const Text('Speech Recognition & Voice Language'),
                subtitle: Text(_sttLanguage),
                trailing: const Icon(Icons.arrow_drop_down),
                onTap: _showLanguagePicker,
              ),
            ]),
            const SizedBox(height: AppSpacing.lg),


            // -------------------------------------------------------------
            // Section 4: Notifications & Digest
            // -------------------------------------------------------------
            _buildSectionHeader('Alerts & Notifications', Icons.notifications_none_outlined),
            _buildCardWrapper([
              SwitchListTile(
                secondary: const Icon(Icons.gavel_outlined, color: AppColors.riskHigh),
                title: const Text('High-Risk Approval Alerts'),
                subtitle: const Text('Instant notification when copilot requires human approval'),
                value: _notifyApprovals,
                onChanged: (val) => setState(() => _notifyApprovals = val),
              ),
              const Divider(height: 1),
              SwitchListTile(
                secondary: const Icon(Icons.check_circle_outline, color: AppColors.success),
                title: const Text('Task Completed / Failed'),
                subtitle: const Text('Get notified when autonomous plan execution finishes'),
                value: _notifyTaskCompletion,
                onChanged: (val) => setState(() => _notifyTaskCompletion = val),
              ),
              const Divider(height: 1),
              SwitchListTile(
                secondary: const Icon(Icons.summarize_outlined, color: AppColors.primary),
                title: const Text('Daily Morning Digest'),
                subtitle: Text('Automated briefing at ${_digestTime.format(context)}'),
                value: _notifyDailyDigest,
                onChanged: (val) => setState(() => _notifyDailyDigest = val),
              ),
              const Divider(height: 1),
              ListTile(
                leading: const Icon(Icons.inbox_outlined, color: AppColors.neutral700),
                title: const Text('View Notifications Hub'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.pushNamed(context, AppRoutes.notifications),
              ),
            ]),
            const SizedBox(height: AppSpacing.lg),

            // -------------------------------------------------------------
            // Section 5: Diagnostics & Audit Trail
            // -------------------------------------------------------------
            _buildSectionHeader('Observability & Trust', Icons.analytics_outlined),
            _buildCardWrapper([
              ListTile(
                leading: const Icon(Icons.query_stats_outlined, color: AppColors.primary),
                title: const Text('Trust & Metrics Dashboard'),
                subtitle: const Text('Latency, accuracy, and token spend analytics'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.pushNamed(context, AppRoutes.trustDashboard),
              ),
              const Divider(height: 1),
              ListTile(
                leading: const Icon(Icons.receipt_long_outlined, color: AppColors.neutral700),
                title: const Text('Execution Activity Log'),
                subtitle: const Text('Inspect every step, tool call, and audit record'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.pushNamed(context, AppRoutes.activityLog),
              ),
              const Divider(height: 1),
              ListTile(
                leading: const Icon(Icons.dns_outlined, color: AppColors.neutral700),
                title: const Text('Backend Server URL'),
                subtitle: Text(ApiConfig.baseUrl),
                trailing: const Icon(Icons.edit_outlined),
                onTap: _showEditServerUrlDialog,
              ),
              const Divider(height: 1),
              ListTile(
                leading: const Icon(Icons.cleaning_services_outlined, color: AppColors.neutral700),
                title: const Text('Clear Local Cache'),
                subtitle: const Text('Free up temporary files and audio storage'),
                trailing: const Icon(Icons.chevron_right),
                onTap: _showClearCacheDialog,
              ),
            ]),
            const SizedBox(height: AppSpacing.xl),

            // -------------------------------------------------------------
            // Section 6: App Version & Sign Out
            // -------------------------------------------------------------
            Center(
              child: Column(
                children: [
                  const Text(
                    'AgentOps Copilot v0.1.0 (Build 2026.09)',
                    style: TextStyle(color: AppColors.neutral500, fontSize: 12),
                  ),
                  const SizedBox(height: AppSpacing.xs),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: const BoxDecoration(
                          color: AppColors.success,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: AppSpacing.xs),
                      Text(
                        'Backend: ${ApiConfig.baseUrl}',
                        style: const TextStyle(color: AppColors.neutral500, fontSize: 12),
                      ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.md),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.error,
                        side: const BorderSide(color: AppColors.error),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                      ),
                      onPressed: _showConfirmLogoutDialog,
                      icon: const Icon(Icons.logout_outlined),
                      label: const Text('Sign Out', style: TextStyle(fontWeight: FontWeight.w600)),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: AppSpacing.xl),
          ],
        ),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Helper Widgets
  // ---------------------------------------------------------------------------

  Widget _buildProfileCard(ThemeData theme) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.neutral0,
        borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
        border: Border.all(color: AppColors.neutral300),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.03),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 28,
            backgroundColor: AppColors.primary,
            child: const Text(
              'AO',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: 20,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'AgentOps Developer',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 2),
                const Text(
                  'new.test.user123@gmail.com',
                  style: TextStyle(color: AppColors.neutral700, fontSize: 13),
                ),
                const SizedBox(height: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppColors.primaryLight,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text(
                    'Workspace: Production Cluster',
                    style: TextStyle(
                      color: AppColors.primary,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title, IconData icon) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.xs, left: AppSpacing.xs),
      child: Row(
        children: [
          Icon(icon, size: 18, color: AppColors.neutral700),
          const SizedBox(width: AppSpacing.xs),
          Text(
            title,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.bold,
              color: AppColors.neutral700,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCardWrapper(List<Widget> children) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.neutral0,
        borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
        border: Border.all(color: AppColors.neutral300),
      ),
      child: Column(children: children),
    );
  }

  // ---------------------------------------------------------------------------
  // Dialog / Selector Helpers
  // ---------------------------------------------------------------------------

  String _getModelLabel(String modelKey) {
    switch (modelKey) {
      case 'gemini-3.7-flash':
        return 'Google Gemini 3.7 Flash (Fast)';
      case 'groq-gpt-oss':
        return 'Groq Llama / GPT-OSS 20B (Ultra Low Latency)';
      default:
        return modelKey;
    }
  }

  String _getAutonomyLabel(String levelKey) {
    switch (levelKey) {
      case 'high_security':
        return 'High Security (Approve Med & High risk)';
      case 'balanced':
        return 'Balanced (Approve High risk only)';
      case 'autonomous':
        return 'Autonomous (Auto-execute all safe steps)';
      default:
        return levelKey;
    }
  }

  void _showModelPicker() {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Select Planning LLM',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
              ),
              const SizedBox(height: AppSpacing.sm),
              RadioListTile<String>(
                title: const Text('Gemini 3.7 Flash'),
                subtitle: const Text('Deep reasoning, structured output, multi-tool'),
                value: 'gemini-3.7-flash',
                groupValue: _selectedModel,
                onChanged: (val) {
                  setState(() => _selectedModel = val!);
                  Navigator.pop(ctx);
                },
              ),
              RadioListTile<String>(
                title: const Text('Groq GPT-OSS 20B'),
                subtitle: const Text('Sub-second response, lightweight tasks'),
                value: 'groq-gpt-oss',
                groupValue: _selectedModel,
                onChanged: (val) {
                  setState(() => _selectedModel = val!);
                  Navigator.pop(ctx);
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showAutonomyPicker() {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Autonomy & Human-in-the-Loop',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
              ),
              const SizedBox(height: AppSpacing.sm),
              RadioListTile<String>(
                title: const Text('Balanced (Default)'),
                subtitle: const Text('Auto-run Low/Medium risk; Require approval for High risk'),
                value: 'balanced',
                groupValue: _autonomyLevel,
                onChanged: (val) {
                  setState(() => _autonomyLevel = val!);
                  Navigator.pop(ctx);
                },
              ),
              RadioListTile<String>(
                title: const Text('High Security'),
                subtitle: const Text('Require confirmation for Medium and High risk actions'),
                value: 'high_security',
                groupValue: _autonomyLevel,
                onChanged: (val) {
                  setState(() => _autonomyLevel = val!);
                  Navigator.pop(ctx);
                },
              ),
              RadioListTile<String>(
                title: const Text('Autonomous Mode'),
                subtitle: const Text('Minimize prompts; Auto-run all standard tool executions'),
                value: 'autonomous',
                groupValue: _autonomyLevel,
                onChanged: (val) {
                  setState(() => _autonomyLevel = val!);
                  Navigator.pop(ctx);
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showSpeechRatePicker() {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Select Speech Rate',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
              ),
              const SizedBox(height: AppSpacing.sm),
              for (final rate in [0.75, 1.0, 1.25, 1.5, 2.0])
                RadioListTile<double>(
                  title: Text('${rate}x speed'),
                  value: rate,
                  groupValue: _ttsSpeechRate,
                  onChanged: (val) async {
                    if (val != null) {
                      setState(() => _ttsSpeechRate = val);
                      await TtsService.setSpeechRate(val);
                      if (ctx.mounted) Navigator.pop(ctx);
                    }
                  },
                ),
            ],
          ),
        ),
      ),
    );
  }

  void _showLanguagePicker() {

    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Speech Recognition Language',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
              ),
              const SizedBox(height: AppSpacing.sm),
              RadioListTile<String>(
                title: const Text('English / Hinglish (Auto-detect)'),
                subtitle: const Text('Recommended for multilingual DevOps commands'),
                value: 'en-US (Auto-detect)',
                groupValue: _sttLanguage,
                onChanged: (val) {
                  setState(() => _sttLanguage = val!);
                  Navigator.pop(ctx);
                },
              ),
              RadioListTile<String>(
                title: const Text('English (US)'),
                value: 'en-US',
                groupValue: _sttLanguage,
                onChanged: (val) {
                  setState(() => _sttLanguage = val!);
                  Navigator.pop(ctx);
                },
              ),
              RadioListTile<String>(
                title: const Text('Hindi (हिन्दी)'),
                value: 'hi-IN',
                groupValue: _sttLanguage,
                onChanged: (val) {
                  setState(() => _sttLanguage = val!);
                  Navigator.pop(ctx);
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}