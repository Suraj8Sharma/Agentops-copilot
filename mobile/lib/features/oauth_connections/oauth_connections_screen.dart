import 'package:flutter/material.dart';
import '../../core/theme.dart';
import 'oauth_connection_service.dart';

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

enum OAuthProvider {
  googleCalendar,
  gmail,
  github,
  slack;

  String get displayName {
    switch (this) {
      case OAuthProvider.googleCalendar:
        return 'Google Calendar';
      case OAuthProvider.gmail:
        return 'Gmail';
      case OAuthProvider.github:
        return 'GitHub';
      case OAuthProvider.slack:
        return 'Slack';
    }
  }

  IconData get iconData {
    switch (this) {
      case OAuthProvider.googleCalendar:
        return Icons.calendar_today;
      case OAuthProvider.gmail:
        return Icons.email;
      case OAuthProvider.github:
        return Icons.code;
      case OAuthProvider.slack:
        return Icons.forum;
    }
  }

  String get key {
    switch (this) {
      case OAuthProvider.googleCalendar:
        return 'google_calendar';
      case OAuthProvider.gmail:
        return 'gmail';
      case OAuthProvider.github:
        return 'github';
      case OAuthProvider.slack:
        return 'slack';
    }
  }
}

enum OAuthStatus {
  active,
  expired,
  revoked,
  scopeMismatch;

  /// On Day 9 only 'active' counts as connected.
  bool get isConnected => this == OAuthStatus.active;
}

// ---------------------------------------------------------------------------
// Model — mirrors the oauth_connections DB row shape
// ---------------------------------------------------------------------------

class OAuthConnectionModel {
  const OAuthConnectionModel({
    required this.provider,
    this.status,
    this.scopes = const [],
    this.expiresAt,
    this.connectedAt,
    this.reauthReason,
    this.failedOperation,
  });

  final OAuthProvider provider;

  /// null means no DB row exists (not connected).
  final OAuthStatus? status;
  final List<String> scopes;
  final DateTime? expiresAt;
  final DateTime? connectedAt;
  final String? reauthReason;
  final String? failedOperation;

  bool get isConnected => status?.isConnected ?? false;

  OAuthConnectionModel copyWith({
    OAuthStatus? status,
    List<String>? scopes,
    DateTime? expiresAt,
    DateTime? connectedAt,
    bool clearStatus = false,
    bool clearConnectedAt = false,
    String? reauthReason,
    String? failedOperation,
    bool clearFailure = false,
  }) {
    return OAuthConnectionModel(
      provider: provider,
      status: clearStatus ? null : (status ?? this.status),
      scopes: scopes ?? this.scopes,
      expiresAt: expiresAt ?? this.expiresAt,
      connectedAt:
          clearConnectedAt ? null : (connectedAt ?? this.connectedAt),
      reauthReason: clearFailure ? null : (reauthReason ?? this.reauthReason),
      failedOperation:
          clearFailure ? null : (failedOperation ?? this.failedOperation),
    );
  }
}

// ---------------------------------------------------------------------------
// Scope label mapping
// ---------------------------------------------------------------------------

String _scopesDisplayLabel(OAuthProvider provider, List<String> scopes) {
  switch (provider) {
    case OAuthProvider.googleCalendar:
      if (scopes.contains('calendar.events')) {
        return 'Can view and create calendar events';
      }
    case OAuthProvider.gmail:
      if (scopes.contains('gmail.send') || scopes.contains('gmail.compose')) {
        return 'Can draft and send email on your behalf';
      }
    case OAuthProvider.github:
      if (scopes.contains('repo')) {
        return 'Can create issues and comments on your repos';
      }
    case OAuthProvider.slack:
      if (scopes.contains('chat:write') || scopes.contains('channels:read')) {
        return 'Can post messages in one connected workspace';
      }
  }
  return '';
}

// ---------------------------------------------------------------------------
// Date formatting helper
// ---------------------------------------------------------------------------

String _formatConnectedAt(DateTime dt) {
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  return 'Connected since ${months[dt.month - 1]} ${dt.day}, ${dt.year}';
}

// ---------------------------------------------------------------------------
// Initial mock data (mirrors DB state)
// ---------------------------------------------------------------------------



// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

class OAuthConnectionsScreen extends StatefulWidget {
  const OAuthConnectionsScreen({super.key});

  @override
  State<OAuthConnectionsScreen> createState() => _OAuthConnectionsScreenState();
}

class _OAuthConnectionsScreenState extends State<OAuthConnectionsScreen> {
  late List<OAuthConnectionModel> _connections;

  /// Tracks in-flight state per provider to debounce/disable the button.
  final Map<OAuthProvider, bool> _loading = {};

  bool _isLoadingAll = true;
  String? _loadError;

  @override
  void initState() {
    super.initState();
    _connections = [
      const OAuthConnectionModel(provider: OAuthProvider.googleCalendar),
      const OAuthConnectionModel(provider: OAuthProvider.gmail),
      const OAuthConnectionModel(provider: OAuthProvider.github),
      const OAuthConnectionModel(provider: OAuthProvider.slack),
    ];
    _fetchConnections();
  }

  Future<void> _fetchConnections() async {
    try {
      final dbConns = await OAuthConnectionService.fetchConnections();
      final byProvider = {
        for (final connection in dbConns) connection.provider: connection,
      };
      if (!mounted) return;
      setState(() {
        _connections = OAuthProvider.values
            .map((provider) => byProvider[provider] ??
                OAuthConnectionModel(provider: provider))
            .toList();
        _isLoadingAll = false;
        _loadError = null;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoadingAll = false;
          _loadError = 'Unable to load connections. Please try again.';
        });
      }
    }
  }

  bool _isLoading(OAuthProvider provider) => _loading[provider] ?? false;

  Future<void> _handleAction(OAuthProvider provider) async {
    if (_isLoading(provider)) return;

    setState(() => _loading[provider] = true);

    try {
      final index = _connections.indexWhere((c) => c.provider == provider);
      if (index == -1) return;
      final current = _connections[index];

      if (current.isConnected) {
        // Do not optimistically clear a connection before DELETE succeeds.
        await OAuthConnectionService.disconnect(provider);
        if (!mounted) return;
        setState(() {
          _connections[index] = OAuthConnectionModel(provider: provider);
        });
      } else {
        // Re-authentication deliberately re-enters the existing D21 flow.
        final authUrl = await OAuthConnectionService.connect(provider);
        if (authUrl != null && mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                '${provider.displayName} consent started. Complete it to reconnect.',
              ),
            ),
          );
        }
        // The callback may have completed while the consent page was open.
        await _fetchConnections();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Failed to update ${provider.displayName} connection. Please try again.',
            ),
            backgroundColor: AppColors.error,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _loading[provider] = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoadingAll) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    if (_loadError != null) {
      return Scaffold(
        key: const Key('oauth-connections-error'),
        appBar: AppBar(title: const Text('OAuth Connections')),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_loadError!, textAlign: TextAlign.center),
              const SizedBox(height: AppSpacing.md),
              OutlinedButton(
                onPressed: () {
                  setState(() {
                    _isLoadingAll = true;
                    _loadError = null;
                  });
                  _fetchConnections();
                },
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }
    return Scaffold(
      key: const Key('oauth-connections-screen'),
      appBar: AppBar(
        title: const Text('OAuth Connections'),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.screenPadding,
              vertical: AppSpacing.sm,
            ),
            child: Text(
              'Manage which services AgentOps can act on your behalf',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: AppColors.neutral500,
                  ),
            ),
          ),
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.all(AppSpacing.screenPadding),
              itemCount: _connections.length,
              separatorBuilder: (_, __) =>
                  const SizedBox(height: AppSpacing.md),
              itemBuilder: (context, index) {
                final model = _connections[index];
                return _OAuthConnectionCard(
                  model: model,
                  isLoading: _isLoading(model.provider),
                  onAction: () => _handleAction(model.provider),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Provider Card
// ---------------------------------------------------------------------------

class _OAuthConnectionCard extends StatelessWidget {
  const _OAuthConnectionCard({
    required this.model,
    required this.isLoading,
    required this.onAction,
  });

  final OAuthConnectionModel model;
  final bool isLoading;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final provider = model.provider;
    final connected = model.isConnected;

    return Card(
      key: Key('provider-card-${provider.key}'),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.cardRadius),
        side: const BorderSide(color: AppColors.neutral300),
      ),
      color: AppColors.neutral0,
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Provider icon container
            Container(
              width: AppSpacing.xl,
              height: AppSpacing.xl,
              decoration: BoxDecoration(
                color: AppColors.neutral100,
                borderRadius: BorderRadius.circular(AppSpacing.sm),
              ),
              child: Icon(
                provider.iconData,
                color: AppColors.neutral700,
                size: AppSpacing.iconSize,
              ),
            ),
            const SizedBox(width: AppSpacing.md),

            // Info column
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Provider name
                  Text(
                    provider.displayName,
                    style: textTheme.titleMedium,
                  ),
                  const SizedBox(height: AppSpacing.xs),

                  // Status chip
                  _StatusChip(
                    providerKey: provider.key,
                    status: model.status,
                  ),

                  if (model.status == OAuthStatus.scopeMismatch) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      key: Key('scope-mismatch-${provider.key}'),
                      _disabledFeatureText(provider),
                      style: textTheme.bodySmall?.copyWith(
                        color: AppColors.error,
                      ),
                    ),
                  ],

                  if (model.status == OAuthStatus.expired ||
                      model.status == OAuthStatus.revoked) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      key: Key('reauth-prompt-${provider.key}'),
                      model.reauthReason ??
                          'Reconnect ${provider.displayName} to continue using this feature.',
                      style: textTheme.bodySmall?.copyWith(
                        color: AppColors.error,
                      ),
                    ),
                  ],

                  if (provider == OAuthProvider.googleCalendar &&
                      _isTestingModeExpirySoon(model.expiresAt)) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      key: const Key('google-testing-mode-expiry-flag'),
                      'Google testing-mode access expires soon. Reconnect to keep Calendar active.',
                      style: textTheme.bodySmall?.copyWith(
                        color: AppColors.warning,
                      ),
                    ),
                  ],

                  if (model.failedOperation == 'gmail_send' &&
                      model.status != OAuthStatus.active) ...[
                    const SizedBox(height: AppSpacing.xs),
                    const Text('Re-authenticate before sending this email.'),
                  ],

                  if (model.failedOperation == 'gmail_draft') ...[
                    const SizedBox(height: AppSpacing.xs),
                    const Text(
                      key: Key('gmail-draft-fallback'),
                      'Saved, not sent',
                    ),
                  ],

                  // Scopes text — only when connected
                  if (connected) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      key: Key('scopes-text-${provider.key}'),
                      _scopesDisplayLabel(provider, model.scopes),
                      style: textTheme.bodySmall?.copyWith(
                        color: AppColors.neutral500,
                      ),
                    ),
                  ],

                  // Connected-since — only when connected
                  if (connected && model.connectedAt != null) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      _formatConnectedAt(model.connectedAt!),
                      style: textTheme.bodySmall?.copyWith(
                        color: AppColors.neutral500,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),

            // Action button
            _ActionButton(
              providerKey: provider.key,
              connected: connected,
              status: model.status,
              isLoading: isLoading,
              onPressed: isLoading ? null : onAction,
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Status Chip
// ---------------------------------------------------------------------------

class _StatusChip extends StatelessWidget {
  const _StatusChip({
    required this.providerKey,
    required this.status,
  });

  final String providerKey;
  final OAuthStatus? status;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    final label = switch (status) {
      OAuthStatus.active => 'Connected',
      OAuthStatus.expired => 'Expired - reconnect required',
      OAuthStatus.revoked => 'Revoked - reconnect required',
      OAuthStatus.scopeMismatch => 'Limited access',
      null => 'Not Connected',
    };
    final connected = status == OAuthStatus.active;

    return Container(
      key: Key('status-chip-$providerKey'),
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: connected ? AppColors.riskLowBg : AppColors.neutral100,
        borderRadius: BorderRadius.circular(AppSpacing.xs),
      ),
      child: Text(
        label,
        style: textTheme.labelSmall?.copyWith(
          color: connected ? AppColors.success : AppColors.neutral500,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Action Button
// ---------------------------------------------------------------------------

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.providerKey,
    required this.connected,
    required this.status,
    required this.isLoading,
    required this.onPressed,
  });

  final String providerKey;
  final bool connected;
  final OAuthStatus? status;
  final bool isLoading;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final buttonKey = Key('connect-btn-$providerKey');

    if (isLoading) {
      return SizedBox(
        key: buttonKey,
        width: AppSpacing.lg,
        height: AppSpacing.lg,
        child: const CircularProgressIndicator(
          strokeWidth: AppSpacing.progressStrokeWidth,
        ),
      );
    }

    if (connected) {
      // Disconnect — OutlinedButton with error red border + text
      return OutlinedButton(
        key: Key('disconnect-btn-$providerKey'),
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.error,
          side: const BorderSide(color: AppColors.error),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
          ),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm,
          ),
        ),
        child: const Text('Disconnect'),
      );
    }

    // Connect — ElevatedButton with primary blue
    return ElevatedButton(
      key: buttonKey,
      onPressed: onPressed,
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: AppColors.neutral0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
      ),
      child: Text(status == null ? 'Connect' : 'Re-authenticate'),
    );
  }
}

String _disabledFeatureText(OAuthProvider provider) {
  switch (provider) {
    case OAuthProvider.googleCalendar:
      return 'Calendar actions are unavailable until access is restored.';
    case OAuthProvider.gmail:
      return 'Gmail sending is unavailable until the required scope is restored.';
    case OAuthProvider.github:
      return 'Repository actions are unavailable until access is restored.';
    case OAuthProvider.slack:
      return 'Slack messaging is unavailable until access is restored.';
  }
}

bool _isTestingModeExpirySoon(DateTime? expiresAt) {
  if (expiresAt == null) return false;
  final now = DateTime.now().toUtc();
  final expiry = expiresAt.toUtc();
  return expiry.isAfter(now) &&
      !expiry.isAfter(now.add(const Duration(days: 7)));
}
