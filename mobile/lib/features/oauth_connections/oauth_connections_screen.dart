import 'package:flutter/material.dart';
import '../../core/theme.dart';

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
  });

  final OAuthProvider provider;

  /// null means no DB row exists (not connected).
  final OAuthStatus? status;
  final List<String> scopes;
  final DateTime? expiresAt;
  final DateTime? connectedAt;

  bool get isConnected => status?.isConnected ?? false;

  OAuthConnectionModel copyWith({
    OAuthStatus? status,
    List<String>? scopes,
    DateTime? expiresAt,
    DateTime? connectedAt,
    bool clearStatus = false,
    bool clearConnectedAt = false,
  }) {
    return OAuthConnectionModel(
      provider: provider,
      status: clearStatus ? null : (status ?? this.status),
      scopes: scopes ?? this.scopes,
      expiresAt: expiresAt ?? this.expiresAt,
      connectedAt:
          clearConnectedAt ? null : (connectedAt ?? this.connectedAt),
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

final List<OAuthConnectionModel> _initialConnections = [
  OAuthConnectionModel(
    provider: OAuthProvider.googleCalendar,
    status: OAuthStatus.active,
    scopes: const ['calendar.events'],
    connectedAt: DateTime(2026, 8, 20),
  ),
  const OAuthConnectionModel(
    provider: OAuthProvider.gmail,
  ),
  OAuthConnectionModel(
    provider: OAuthProvider.github,
    status: OAuthStatus.active,
    scopes: const ['repo'],
    connectedAt: DateTime(2026, 8, 22),
  ),
  const OAuthConnectionModel(
    provider: OAuthProvider.slack,
  ),
];

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

  @override
  void initState() {
    super.initState();
    _connections = List<OAuthConnectionModel>.from(_initialConnections);
  }

  bool _isLoading(OAuthProvider provider) => _loading[provider] ?? false;

  Future<void> _handleAction(OAuthProvider provider) async {
    if (_isLoading(provider)) return;

    setState(() => _loading[provider] = true);

    try {
      // D9: local mock toggle — no network call.
      // D21: replace the body of this try block with a real API call.
      await Future<void>.delayed(const Duration(milliseconds: 300));

      final index =
          _connections.indexWhere((c) => c.provider == provider);
      if (index == -1) return;

      final current = _connections[index];
      OAuthConnectionModel updated;

      if (current.isConnected) {
        // Disconnect: clear status & connectedAt
        updated = current.copyWith(clearStatus: true, clearConnectedAt: true);
      } else {
        // Connect: set active + mock scopes + now as connectedAt
        final mockScopes = _mockScopesFor(provider);
        updated = OAuthConnectionModel(
          provider: provider,
          status: OAuthStatus.active,
          scopes: mockScopes,
          connectedAt: DateTime.now(),
        );
      }

      setState(() {
        _connections[index] = updated;
      });
    } catch (e) {
      // Structural error path — unreachable on D9, but ready for D21.
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

  List<String> _mockScopesFor(OAuthProvider provider) {
    switch (provider) {
      case OAuthProvider.googleCalendar:
        return const ['calendar.events'];
      case OAuthProvider.gmail:
        return const ['gmail.send', 'gmail.compose'];
      case OAuthProvider.github:
        return const ['repo'];
      case OAuthProvider.slack:
        return const ['chat:write', 'channels:read'];
    }
  }

  @override
  Widget build(BuildContext context) {
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
                    connected: connected,
                  ),

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
    required this.connected,
  });

  final String providerKey;
  final bool connected;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

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
        connected ? 'Connected' : 'Not Connected',
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
    required this.isLoading,
    required this.onPressed,
  });

  final String providerKey;
  final bool connected;
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
      child: const Text('Connect'),
    );
  }
}
