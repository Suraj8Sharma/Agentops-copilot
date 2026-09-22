import 'package:flutter/material.dart';

import '../../core/theme.dart';
import 'activity_log_models.dart';
import 'activity_log_service.dart';

class ActivityLogScreen extends StatefulWidget {
  const ActivityLogScreen({super.key});

  @override
  State<ActivityLogScreen> createState() => _ActivityLogScreenState();
}

class _ActivityLogScreenState extends State<ActivityLogScreen> {
  // null means "All" is selected.
  LogEventType? _activeFilter;
  String _searchQuery = '';
  final TextEditingController _searchCtrl = TextEditingController();

  // Async state.
  late Future<List<ActivityLogEntry>> _logFuture;

  @override
  void initState() {
    super.initState();
    _fetchData();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  void _fetchData() {
    setState(() {
      _logFuture = ActivityLogService.fetchActivityLog(limit: 200);
    });
  }

  void _setFilter(LogEventType? type) {
    setState(() => _activeFilter = type);
  }

  List<ActivityLogEntry> _applyFilters(List<ActivityLogEntry> all) {
    var entries = all;

    // Event-type filter.
    if (_activeFilter != null) {
      entries = entries.where((e) => e.eventType == _activeFilter).toList();
    }

    // Search query — case-insensitive match on title, description, integration.
    final q = _searchQuery.trim().toLowerCase();
    if (q.isNotEmpty) {
      entries = entries.where((e) {
        return e.title.toLowerCase().contains(q) ||
            e.description.toLowerCase().contains(q) ||
            (e.integration?.toLowerCase().contains(q) ?? false);
      }).toList();
    }

    // Already newest-first from the service; preserve that order.
    return entries;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Activity Log'),
        actions: <Widget>[
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: _fetchData,
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            // ── Search bar ──────────────────────────────────────────────────
            Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.screenPadding,
                AppSpacing.md,
                AppSpacing.screenPadding,
                AppSpacing.xs,
              ),
              child: TextField(
                key: const Key('activity-search'),
                controller: _searchCtrl,
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  hintText: 'Search actions, integrations…',
                  prefixIcon: const Icon(Icons.search, size: AppSpacing.md),
                  suffixIcon: _searchQuery.isNotEmpty
                      ? IconButton(
                          tooltip: 'Clear search',
                          icon: const Icon(Icons.close, size: AppSpacing.md),
                          onPressed: () {
                            _searchCtrl.clear();
                            setState(() => _searchQuery = '');
                          },
                        )
                      : null,
                ),
                onChanged: (v) => setState(() => _searchQuery = v),
              ),
            ),

            // ── Filter chips ────────────────────────────────────────────────
            SizedBox(
              height: 44,
              child: ListView(
                key: const Key('activity-filter-chips'),
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.screenPadding),
                children: <Widget>[
                  _FilterChip(
                    label: 'All',
                    isSelected: _activeFilter == null,
                    onTap: () => _setFilter(null),
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  for (final type in LogEventType.values) ...<Widget>[
                    _FilterChip(
                      label: type.chipLabel,
                      isSelected: _activeFilter == type,
                      activeColor: type.color,
                      activeBgColor: type.backgroundColor,
                      onTap: () => _setFilter(type),
                    ),
                    const SizedBox(width: AppSpacing.xs),
                  ],
                ],
              ),
            ),

            const SizedBox(height: AppSpacing.xs),

            // ── Main content driven by FutureBuilder ────────────────────────
            Expanded(
              child: FutureBuilder<List<ActivityLogEntry>>(
                future: _logFuture,
                builder: (context, snapshot) {
                  // Loading state.
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return const _LoadingState();
                  }

                  // Auth error — propagate so the user can sign in.
                  if (snapshot.hasError &&
                      snapshot.error is ActivityLogException) {
                    final err = snapshot.error! as ActivityLogException;
                    if (err.requiresSignIn) {
                      return _ErrorState(
                        message: err.message,
                        onRetry: _fetchData,
                      );
                    }
                  }

                  // Service returns mock on network errors so hasData is
                  // almost always true. Show an error state only on 401.
                  final allEntries = snapshot.data ?? <ActivityLogEntry>[];
                  final filtered = _applyFilters(allEntries);

                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      // Event count label.
                      Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.screenPadding,
                          vertical: AppSpacing.xs,
                        ),
                        child: Text(
                          '${filtered.length} event${filtered.length == 1 ? '' : 's'}',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),

                      // List with pull-to-refresh.
                      Expanded(
                        child: filtered.isEmpty
                            ? const _EmptyState()
                            : RefreshIndicator(
                                onRefresh: () async => _fetchData(),
                                child: ListView.separated(
                                  key: const Key('activity-log-list'),
                                  physics:
                                      const AlwaysScrollableScrollPhysics(),
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: AppSpacing.screenPadding,
                                    vertical: AppSpacing.sm,
                                  ),
                                  itemCount: filtered.length,
                                  separatorBuilder: (_, __) =>
                                      const SizedBox(height: AppSpacing.xs),
                                  itemBuilder: (context, index) =>
                                      _LogEntryCard(entry: filtered[index]),
                                ),
                              ),
                      ),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) => const Center(
        key: Key('activity-loading'),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            CircularProgressIndicator(),
            SizedBox(height: AppSpacing.md),
            Text('Loading activity…'),
          ],
        ),
      );
}

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
        key: const Key('activity-error'),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Icon(Icons.error_outline,
                  size: AppSpacing.xxl, color: AppColors.error),
              const SizedBox(height: AppSpacing.md),
              Text('Could not load activity',
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: AppSpacing.xs),
              Text(message,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium),
              const SizedBox(height: AppSpacing.md),
              ElevatedButton(
                  onPressed: onRetry, child: const Text('Retry')),
            ],
          ),
        ),
      );
}

// ---------------------------------------------------------------------------
// Filter chip
// ---------------------------------------------------------------------------

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.isSelected,
    required this.onTap,
    this.activeColor,
    this.activeBgColor,
  });

  final String label;
  final bool isSelected;
  final VoidCallback onTap;
  final Color? activeColor;
  final Color? activeBgColor;

  @override
  Widget build(BuildContext context) {
    final Color fg = isSelected
        ? (activeColor ?? AppColors.primary)
        : AppColors.neutral700;
    final Color bg = isSelected
        ? (activeBgColor ?? AppColors.primaryLight)
        : AppColors.neutral100;
    final Color border =
        isSelected ? (activeColor ?? AppColors.primary) : AppColors.neutral300;

    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md, vertical: AppSpacing.xs),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(AppSpacing.xxl),
          border: Border.all(color: border),
        ),
        child: Text(
          label,
          style:
              Theme.of(context).textTheme.labelMedium?.copyWith(color: fg),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Log entry card
// ---------------------------------------------------------------------------

class _LogEntryCard extends StatelessWidget {
  const _LogEntryCard({required this.entry});
  final ActivityLogEntry entry;

  @override
  Widget build(BuildContext context) {
    final tt = Theme.of(context).textTheme;
    final eventType = entry.eventType;

    return Card(
      key: Key('log-entry-${entry.id}'),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            // ── Left: icon in coloured circle ──────────────────────────────
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: eventType.backgroundColor,
                shape: BoxShape.circle,
              ),
              child: Icon(
                eventType.icon,
                size: 18,
                color: eventType.color,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),

            // ── Right: text content ─────────────────────────────────────────
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  // Title row + event-type chip.
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          entry.title,
                          style: tt.titleMedium,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      _EventTypeChip(eventType: eventType),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.xs),

                  // Description.
                  Text(
                    entry.description,
                    style: tt.bodyMedium,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: AppSpacing.sm),

                  // Footer row: integration badge + risk badge + timestamp.
                  Row(
                    children: <Widget>[
                      if (entry.integration != null) ...<Widget>[
                        _IntegrationBadge(name: entry.integration!),
                        const SizedBox(width: AppSpacing.sm),
                      ],
                      if (entry.riskTier != null) ...<Widget>[
                        _RiskBadge(tier: entry.riskTier!),
                        const SizedBox(width: AppSpacing.sm),
                      ],
                      const Spacer(),
                      Text(
                        _formatTimestamp(entry.timestamp),
                        style: tt.bodySmall,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  static String _formatTimestamp(DateTime dt) {
    final hour = dt.hour.toString().padLeft(2, '0');
    final min = dt.minute.toString().padLeft(2, '0');
    final day = dt.day.toString().padLeft(2, '0');
    final month = dt.month.toString().padLeft(2, '0');
    return '$day/$month  $hour:$min';
  }
}

// ---------------------------------------------------------------------------
// Small badge widgets
// ---------------------------------------------------------------------------

class _EventTypeChip extends StatelessWidget {
  const _EventTypeChip({required this.eventType});
  final LogEventType eventType;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
      decoration: BoxDecoration(
        color: eventType.backgroundColor,
        borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
      ),
      child: Text(
        eventType.label,
        style: Theme.of(context)
            .textTheme
            .labelMedium
            ?.copyWith(color: eventType.color),
      ),
    );
  }
}

class _IntegrationBadge extends StatelessWidget {
  const _IntegrationBadge({required this.name});
  final String name;

  static const Map<String, IconData> _icons = <String, IconData>{
    'gmail': Icons.email_outlined,
    'calendar': Icons.calendar_today_outlined,
    'github': Icons.code_outlined,
    'slack': Icons.chat_bubble_outline,
  };

  @override
  Widget build(BuildContext context) {
    final icon = _icons[name.toLowerCase()] ?? Icons.extension_outlined;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Icon(icon, size: 12, color: AppColors.neutral500),
        const SizedBox(width: 2),
        Text(
          name,
          style: Theme.of(context)
              .textTheme
              .bodySmall
              ?.copyWith(color: AppColors.neutral500),
        ),
      ],
    );
  }
}

class _RiskBadge extends StatelessWidget {
  const _RiskBadge({required this.tier});
  final RiskTier tier;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
      decoration: BoxDecoration(
        color: tier.background,
        borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
      ),
      child: Text(
        tier.label,
        style: Theme.of(context)
            .textTheme
            .labelMedium
            ?.copyWith(color: tier.color),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) => Center(
        key: const Key('activity-empty'),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Icon(Icons.history_toggle_off_outlined,
                  size: AppSpacing.xxl, color: AppColors.neutral500),
              const SizedBox(height: AppSpacing.md),
              Text('No matching events',
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Try a different filter or clear the search.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
          ),
        ),
      );
}