import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/theme.dart';
import 'activity_log_models.dart';
import 'activity_log_service.dart';

class ActivityLogScreen extends StatefulWidget {
  const ActivityLogScreen({
    super.key,
    this.initialFrom,
    this.initialTo,
  });

  final DateTime? initialFrom;
  final DateTime? initialTo;

  @override
  State<ActivityLogScreen> createState() => _ActivityLogScreenState();
}

class _ActivityLogScreenState extends State<ActivityLogScreen> {
  final TextEditingController _searchController = TextEditingController();
  Timer? _searchDebounce;
  final List<ActivityLogEntry> _entries = <ActivityLogEntry>[];
  Set<LogEventType> _types = <LogEventType>{};
  DateTime? _from;
  DateTime? _to;
  String? _nextCursor;
  String _query = '';
  String? _error;
  bool _loading = true;
  bool _loadingMore = false;
  int _requestId = 0;

  bool get _hasFilters =>
      _types.isNotEmpty ||
      _from != null ||
      _to != null ||
      _query.trim().isNotEmpty;

  @override
  void initState() {
    super.initState();
    _from = widget.initialFrom;
    _to = widget.initialTo;
    _load(reset: true);
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load({required bool reset}) async {
    final request = ++_requestId;
    if (reset) {
      setState(() {
        _loading = true;
        _error = null;
        _nextCursor = null;
      });
    } else {
      setState(() => _loadingMore = true);
    }
    try {
      final page = await ActivityLogService.fetchPage(
        cursor: reset ? null : _nextCursor,
        eventTypes: _types,
        from: _from,
        to: _to,
        query: _query,
      );
      if (!mounted || request != _requestId) return;
      setState(() {
        if (reset) _entries.clear();
        final seen = _entries.map((entry) => entry.id).toSet();
        _entries.addAll(page.items.where((entry) => seen.add(entry.id)));
        _entries.sort((a, b) {
          final byDate = b.timestamp.compareTo(a.timestamp);
          return byDate == 0 ? b.id.compareTo(a.id) : byDate;
        });
        _nextCursor = page.nextCursor;
        _loading = false;
        _loadingMore = false;
        _error = null;
      });
    } on ActivityLogException catch (error) {
      if (!mounted || request != _requestId) return;
      setState(() {
        _loading = false;
        _loadingMore = false;
        _error = error.message;
      });
    }
  }

  void _clearFilters() {
    _searchController.clear();
    setState(() {
      _types = <LogEventType>{};
      _from = null;
      _to = null;
      _query = '';
    });
    _load(reset: true);
  }

  Future<void> _pickDateRange() async {
    final range = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2020),
      lastDate: DateTime(2035),
      initialDateRange: _from != null && _to != null
          ? DateTimeRange(start: _from!, end: _to!)
          : null,
    );
    if (!mounted || range == null) return;
    setState(() {
      _from = DateTime(range.start.year, range.start.month, range.start.day);
      _to =
          DateTime(range.end.year, range.end.month, range.end.day, 23, 59, 59);
    });
    _load(reset: true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Activity Log'),
        actions: <Widget>[
          IconButton(
            key: const Key('activity-refresh'),
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => _load(reset: true),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(AppSpacing.screenPadding,
                  AppSpacing.md, AppSpacing.screenPadding, AppSpacing.xs),
              child: TextField(
                key: const Key('activity-search'),
                controller: _searchController,
                decoration: InputDecoration(
                  hintText: 'Search activity',
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: _query.isEmpty
                      ? null
                      : IconButton(
                          key: const Key('activity-clear-search'),
                          icon: const Icon(Icons.close),
                          onPressed: () {
                            _searchController.clear();
                            setState(() => _query = '');
                            _load(reset: true);
                          },
                        ),
                ),
                onChanged: (value) {
                  setState(() => _query = value);
                  _searchDebounce?.cancel();
                  _searchDebounce =
                      Timer(const Duration(milliseconds: 250), () {
                    if (mounted) _load(reset: true);
                  });
                },
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.screenPadding),
              child: Wrap(
                key: const Key('activity-filter-chips'),
                spacing: AppSpacing.xs,
                runSpacing: AppSpacing.xs,
                children: <Widget>[
                  _chip('All', _types.isEmpty, () {
                    setState(() => _types = <LogEventType>{});
                    _load(reset: true);
                  }),
                  _chip('Date', _from != null, _pickDateRange),
                  for (final type in LogEventType.values) ...<Widget>[
                    _chip(type.chipLabel, _types.contains(type), () {
                      setState(() {
                        _types = <LogEventType>{..._types};
                        if (!_types.add(type)) _types.remove(type);
                      });
                      _load(reset: true);
                    }, color: type.color),
                  ],
                ],
              ),
            ),
            if (_hasFilters)
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  key: const Key('activity-clear-filters'),
                  onPressed: _clearFilters,
                  child: const Text('Clear filters'),
                ),
              ),
            Expanded(child: _body()),
          ],
        ),
      ),
    );
  }

  Widget _body() {
    if (_loading) {
      return const Center(
        key: Key('activity-loading'),
        child: Column(mainAxisSize: MainAxisSize.min, children: <Widget>[
          CircularProgressIndicator(),
          SizedBox(height: AppSpacing.md),
          Text('Loading activity...'),
        ]),
      );
    }
    if (_error != null && _entries.isEmpty) {
      return Center(
        key: const Key('activity-error'),
        child: Column(mainAxisSize: MainAxisSize.min, children: <Widget>[
          const Icon(Icons.error_outline, color: AppColors.error),
          const SizedBox(height: AppSpacing.sm),
          Text(_error!, textAlign: TextAlign.center),
          const SizedBox(height: AppSpacing.sm),
          ElevatedButton(
              onPressed: () => _load(reset: true), child: const Text('Retry')),
        ]),
      );
    }
    if (_entries.isEmpty) {
      return Center(
        key: const Key('activity-empty'),
        child: Column(mainAxisSize: MainAxisSize.min, children: <Widget>[
          const Icon(Icons.history_toggle_off_outlined, size: AppSpacing.xxl),
          const SizedBox(height: AppSpacing.sm),
          Text(
              _hasFilters ? 'No results for these filters' : 'No activity yet'),
          if (_hasFilters)
            TextButton(
                onPressed: _clearFilters, child: const Text('Clear filters')),
        ]),
      );
    }
    return Column(
      children: <Widget>[
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(AppSpacing.xs),
            child: Text(_error!, key: const Key('activity-inline-error')),
          ),
        Expanded(
          child: NotificationListener<ScrollNotification>(
            onNotification: (notification) {
              if (notification.metrics.extentAfter < 200 &&
                  _nextCursor != null &&
                  !_loadingMore) {
                _load(reset: false);
              }
              return false;
            },
            child: RefreshIndicator(
              onRefresh: () => _load(reset: true),
              child: ListView.builder(
                key: const Key('activity-log-list'),
                itemCount: _entries.length + (_loadingMore ? 1 : 0),
                itemBuilder: (context, index) => index == _entries.length
                    ? const Padding(
                        padding: EdgeInsets.all(AppSpacing.md),
                        child: Center(child: CircularProgressIndicator()),
                      )
                    : _EntryCard(entry: _entries[index]),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _chip(String label, bool selected, VoidCallback onTap,
      {Color? color}) {
    final normalizedLabel = label.trim();
    final foreground =
        selected ? (color ?? AppColors.primary) : AppColors.neutral700;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        key: Key('activity-filter-$normalizedLabel'),
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md, vertical: AppSpacing.xs),
        decoration: BoxDecoration(
          color: selected
              ? (color?.withValues(alpha: .12) ?? AppColors.primaryLight)
              : AppColors.neutral100,
          border:
              Border.all(color: selected ? foreground : AppColors.neutral300),
          borderRadius: BorderRadius.circular(AppSpacing.xxl),
        ),
        child: Text(normalizedLabel, style: TextStyle(color: foreground)),
      ),
    );
  }
}

class _EntryCard extends StatelessWidget {
  const _EntryCard({required this.entry});
  final ActivityLogEntry entry;

  @override
  Widget build(BuildContext context) {
    return Card(
      key: Key('log-entry-${entry.id}'),
      margin: const EdgeInsets.fromLTRB(
          AppSpacing.screenPadding, AppSpacing.xs, AppSpacing.screenPadding, 0),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Icon(entry.eventType.icon, color: entry.eventType.color),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Row(children: <Widget>[
                        Expanded(
                            child: Text(entry.title,
                                style:
                                    Theme.of(context).textTheme.titleMedium)),
                        Text(entry.eventType.label,
                            key: Key('event-type-${entry.id}'),
                            style: TextStyle(color: entry.eventType.color)),
                      ]),
                      const SizedBox(height: AppSpacing.xs),
                      Text(entry.description,
                          maxLines: 3, overflow: TextOverflow.ellipsis),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                          '${entry.timestamp.day.toString().padLeft(2, '0')}/${entry.timestamp.month.toString().padLeft(2, '0')} ${entry.timestamp.hour.toString().padLeft(2, '0')}:${entry.timestamp.minute.toString().padLeft(2, '0')}',
                          style: Theme.of(context).textTheme.bodySmall),
                      if (entry.decision != null)
                        Text('Decision: ${entry.decision}',
                            key: Key('decision-${entry.id}')),
                    ]),
              ),
            ]),
      ),
    );
  }
}
