import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/router.dart';
import '../../core/theme.dart';
import 'digest_models.dart';
import 'digest_service.dart';

// ---------------------------------------------------------------------------
// Filter tab options
// ---------------------------------------------------------------------------

enum _DigestFilter { all, daily, weekly }

extension _DigestFilterLabel on _DigestFilter {
  String get label {
    switch (this) {
      case _DigestFilter.all:
        return 'All';
      case _DigestFilter.daily:
        return 'Daily';
      case _DigestFilter.weekly:
        return 'Weekly';
    }
  }

  String? get apiValue {
    switch (this) {
      case _DigestFilter.all:
        return null;
      case _DigestFilter.daily:
        return 'daily';
      case _DigestFilter.weekly:
        return 'weekly';
    }
  }
}

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

class DigestScreen extends StatefulWidget {
  const DigestScreen({super.key});

  @override
  State<DigestScreen> createState() => _DigestScreenState();
}

class _DigestScreenState extends State<DigestScreen> {
  static const int _pageSize = 20;

  _DigestFilter _filter = _DigestFilter.all;
  bool _isLoading = true;
  bool _isLoadingMore = false;
  String? _errorMessage;
  List<DigestItem> _digests = [];
  bool _hasMore = false;
  int _offset = 0;

  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _load(reset: true);
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >=
            _scrollController.position.maxScrollExtent - 200 &&
        _hasMore &&
        !_isLoadingMore) {
      _loadMore();
    }
  }

  Future<void> _load({required bool reset}) async {
    if (reset) {
      setState(() {
        _isLoading = true;
        _errorMessage = null;
        _digests = [];
        _offset = 0;
        _hasMore = false;
      });
    }

    try {
      final result = await DigestService.fetchDigests(
        periodType: _filter.apiValue,
        limit: _pageSize,
        offset: _offset,
      );
      if (!mounted) return;
      setState(() {
        _digests = result.digests;
        _hasMore = result.hasMore;
        _offset = _pageSize;
        _isLoading = false;
      });
    } on DigestServiceException catch (e) {
      if (!mounted) return;
      if (e.requiresSignIn) {
        Navigator.of(context).pushReplacementNamed(AppRoutes.signIn);
        return;
      }
      setState(() {
        _errorMessage = e.message;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _loadMore() async {
    setState(() => _isLoadingMore = true);
    try {
      final result = await DigestService.fetchDigests(
        periodType: _filter.apiValue,
        limit: _pageSize,
        offset: _offset,
      );
      if (!mounted) return;
      setState(() {
        _digests.addAll(result.digests);
        _hasMore = result.hasMore;
        _offset += _pageSize;
        _isLoadingMore = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _isLoadingMore = false);
    }
  }

  void _onFilterChanged(_DigestFilter filter) {
    if (filter == _filter) return;
    setState(() => _filter = filter);
    _load(reset: true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Daily / Weekly Digest'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
            onPressed: () => _load(reset: true),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _FilterBar(
              selected: _filter,
              onChanged: _onFilterChanged,
            ),
            Expanded(child: _buildBody()),
          ],
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null) {
      return _ErrorState(
        message: _errorMessage!,
        onRetry: () => _load(reset: true),
      );
    }

    if (_digests.isEmpty) {
      return const _EmptyState();
    }

    return RefreshIndicator(
      onRefresh: () => _load(reset: true),
      child: ListView.separated(
        controller: _scrollController,
        padding: const EdgeInsets.all(AppSpacing.screenPadding),
        itemCount: _digests.length + (_isLoadingMore ? 1 : 0),
        separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.md),
        itemBuilder: (context, index) {
          if (index == _digests.length) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(AppSpacing.md),
                child: CircularProgressIndicator(),
              ),
            );
          }
          return _DigestCard(digest: _digests[index]);
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

class _FilterBar extends StatelessWidget {
  const _FilterBar({required this.selected, required this.onChanged});

  final _DigestFilter selected;
  final ValueChanged<_DigestFilter> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.screenPadding,
        AppSpacing.sm,
        AppSpacing.screenPadding,
        0,
      ),
      child: Row(
        children: _DigestFilter.values.map((filter) {
          final isSelected = filter == selected;
          return Padding(
            padding: const EdgeInsets.only(right: AppSpacing.sm),
            child: ChoiceChip(
              key: Key('digest-filter-${filter.name}'),
              label: Text(filter.label),
              selected: isSelected,
              onSelected: (_) => onChanged(filter),
              selectedColor: AppColors.primaryLight,
              labelStyle: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: isSelected ? AppColors.primary : AppColors.neutral500,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Digest Card
// ---------------------------------------------------------------------------

class _DigestCard extends StatelessWidget {
  const _DigestCard({required this.digest});

  final DigestItem digest;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final isWeekly = digest.isWeekly;
    final color = isWeekly ? AppColors.secondary : AppColors.primary;
    final bgColor = isWeekly ? const Color(0xFFEDE7F6) : AppColors.primaryLight;
    final icon = isWeekly ? Icons.calendar_view_week : Icons.today;
    final label = isWeekly ? 'WEEKLY' : 'DAILY';
    final dateStr = DateFormat('EEE, MMM d • h:mm a').format(
      digest.generatedAt.toLocal(),
    );

    return Card(
      key: Key('digest-${digest.id}'),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: AppSpacing.xs,
                  ),
                  decoration: BoxDecoration(
                    color: bgColor,
                    borderRadius: BorderRadius.circular(AppSpacing.buttonRadius),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(icon, size: AppSpacing.md, color: color),
                      const SizedBox(width: AppSpacing.xs),
                      Text(
                        label,
                        style: textTheme.labelMedium?.copyWith(
                          color: color,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
                const Spacer(),
                Text(
                  dateStr,
                  style: textTheme.bodySmall?.copyWith(
                    color: AppColors.neutral500,
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            const Divider(height: 1),
            const SizedBox(height: AppSpacing.sm),
            Text(
              digest.summaryText,
              style: textTheme.bodyMedium,
            ),
            if (digest.tasksIncluded.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.sm),
              const Divider(height: 1),
              const SizedBox(height: AppSpacing.xs),
              Text(
                '${digest.tasksIncluded.length} task${digest.tasksIncluded.length == 1 ? '' : 's'} included',
                style: textTheme.bodySmall?.copyWith(
                  color: AppColors.neutral500,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Empty / Error states
// ---------------------------------------------------------------------------

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.summarize_outlined,
              size: AppSpacing.xxl,
              color: AppColors.neutral500,
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'No digests yet',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Your first daily digest will appear here tomorrow morning.\nWeekly digests arrive every Monday.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.error_outline,
              size: AppSpacing.xxl,
              color: AppColors.error,
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              'Could not load digests',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              message,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.lg),
            ElevatedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}