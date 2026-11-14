import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/theme.dart';
import 'trust_dashboard_service.dart';

class TrustDashboardScreen extends StatefulWidget {
  const TrustDashboardScreen({
    super.key,
    this.metrics,
  });

  final TrustDashboardMetrics? metrics;

  @override
  State<TrustDashboardScreen> createState() => _TrustDashboardScreenState();
}

class _TrustDashboardScreenState extends State<TrustDashboardScreen> {
  TrustDashboardMetrics? _metrics;
  bool _isLoading = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _metrics = widget.metrics;
    if (_metrics == null) {
      _refresh();
    }
  }

  Future<void> _refresh() async {
    if (!mounted) return;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final metrics = await TrustDashboardService.fetchMetrics();
      if (!mounted) return;
      setState(() {
        _metrics = metrics;
        _isLoading = false;
      });
    } on TrustDashboardException catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.message;
        _isLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Could not load dashboard metrics. Please try again.';
        _isLoading = false;
      });
    }
  }

  TrustDashboardMetrics get metrics => _metrics ?? const TrustDashboardMetrics(
        latency: [],
        cost: [],
        accuracy: [],
      );

  @override
  Widget build(BuildContext context) {
    final safeMetrics = metrics;

    if (_isLoading && _metrics == null) {
      return const Scaffold(
        key: Key('trust-dashboard-screen'),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: AppSpacing.md),
              Text('Loading metrics...'),
            ],
          ),
        ),
      );
    }

    if (_errorMessage != null) {
      return Scaffold(
        key: const Key('trust-dashboard-screen'),
        appBar: AppBar(title: const Text('Trust Dashboard')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.screenPadding),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(_errorMessage!, textAlign: TextAlign.center),
                const SizedBox(height: AppSpacing.md),
                OutlinedButton(
                  onPressed: _refresh,
                  child: const Text('Retry'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Scaffold(
      key: const Key('trust-dashboard-screen'),
      appBar: AppBar(title: const Text('Trust Dashboard')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.screenPadding),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Agent performance at a glance',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              safeMetrics.generatedAt == null
                  ? 'Live metrics from the dashboard endpoint.'
                  : 'Updated ${_formatTime(safeMetrics.generatedAt!)}',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.lg),
            _MetricCard(
              key: const Key('latency-metric-card'),
              title: 'Latency',
              subtitle: 'p95 response time',
              value: _formatLatencyValue(safeMetrics.latency),
              detail: 'Target: under 8s for simple tasks',
              color: AppColors.primary,
              points: safeMetrics.latency,
              chartType: _ChartType.line,
            ),
            const SizedBox(height: AppSpacing.md),
            _MetricCard(
              key: const Key('cost-metric-card'),
              title: 'Cost',
              subtitle: 'LLM spend',
              value: _formatCostValue(safeMetrics.cost),
              detail: 'Groq and Gemini usage',
              color: AppColors.secondary,
              points: safeMetrics.cost,
              chartType: _ChartType.bar,
            ),
            const SizedBox(height: AppSpacing.md),
            _MetricCard(
              key: const Key('accuracy-metric-card'),
              title: 'Accuracy',
              subtitle: 'Eval suite pass rate',
              value: _formatAccuracyValue(safeMetrics.accuracy),
              detail: 'Based on the latest eval runs',
              color: AppColors.success,
              points: safeMetrics.accuracy,
              chartType: _ChartType.line,
            ),
            const SizedBox(height: AppSpacing.md),
            _Legend(
              key: const Key('dashboard-legend'),
              color: AppColors.warning,
              label: 'Fallback event',
              description: safeMetrics.fallbackEvents > 0
                  ? '${safeMetrics.fallbackEvents} rate-limit fallback${safeMetrics.fallbackEvents == 1 ? '' : 's'} tracked.'
                  : 'No fallback events in the current window.',
            ),
          ],
        ),
      ),
    );
  }

  static String _formatTime(DateTime value) {
    return value.toLocal().toString().replaceFirst('.000', '').replaceFirst(':00', '');
  }

  static String _formatLatencyValue(List<DashboardMetricPoint> points) {
    if (points.isEmpty) return 'No data yet';
    final p95 = _p95(points);
    return '${p95.toStringAsFixed(1)}s';
  }

  static String _formatCostValue(List<DashboardMetricPoint> points) {
    if (points.isEmpty) return 'No data yet';
    final total = points.fold<double>(0, (sum, point) => sum + point.value);
    return '\$${total.toStringAsFixed(2)}';
  }

  static String _formatAccuracyValue(List<DashboardMetricPoint> points) {
    if (points.isEmpty) return 'No data yet';
    final avg = _average(points);
    return '${avg.toStringAsFixed(0)}%';
  }

  static double _average(List<DashboardMetricPoint> points) {
    if (points.isEmpty) return 0;
    return points.fold<double>(0, (sum, point) => sum + point.value) /
        points.length;
  }

  static double _p95(List<DashboardMetricPoint> points) {
    if (points.isEmpty) return 0;
    final values = points.map((point) => point.value).toList()..sort();
    final index = math.min(
      values.length - 1,
      (values.length * 0.95).ceil() - 1,
    );
    return values[index];
  }
}

enum _ChartType { line, bar }

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    super.key,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.detail,
    required this.color,
    required this.points,
    required this.chartType,
  });

  final String title;
  final String subtitle;
  final String value;
  final String detail;
  final Color color;
  final List<DashboardMetricPoint> points;
  final _ChartType chartType;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              key: Key('$title-metric-title'),
              style: textTheme.titleMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(subtitle, style: textTheme.bodySmall),
            const SizedBox(height: AppSpacing.sm),
            Text(
              value,
              key: Key('$title-metric-value'),
              style: textTheme.headlineMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(detail, style: textTheme.bodySmall),
            const SizedBox(height: AppSpacing.md),
            SizedBox(
              key: Key('$title-metric-chart'),
              height: AppSpacing.xxl,
              width: double.infinity,
              child: CustomPaint(
                painter: _MetricChartPainter(
                  points: points,
                  color: color,
                  type: chartType,
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: points
                  .map((point) => Text(point.label, style: textTheme.bodySmall))
                  .toList(),
            ),
          ],
        ),
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend({
    super.key,
    required this.color,
    required this.label,
    required this.description,
  });

  final Color color;
  final String label;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: AppSpacing.xs),
          child: Icon(Icons.circle, color: color, size: AppSpacing.sm),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.labelMedium),
              Text(description, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ],
    );
  }
}

class _MetricChartPainter extends CustomPainter {
  _MetricChartPainter({
    required this.points,
    required this.color,
    required this.type,
  });

  final List<DashboardMetricPoint> points;
  final Color color;
  final _ChartType type;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.isEmpty) return;
    final maxValue = points
        .map((point) => point.value)
        .reduce((first, second) => first > second ? first : second);
    final range = maxValue == 0 ? 1 : maxValue;
    final paint = Paint()..color = color;
    if (type == _ChartType.bar) {
      final barWidth = size.width / (points.length * 2);
      for (var index = 0; index < points.length; index++) {
        final height = size.height * points[index].value / range;
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(
              index * size.width / points.length + barWidth / 2,
              size.height - height,
              barWidth,
              height,
            ),
            const Radius.circular(AppSpacing.xs),
          ),
          paint,
        );
      }
      return;
    }
    final path = Path();
    for (var index = 0; index < points.length; index++) {
      final x = points.length == 1
          ? size.width / 2
          : index * size.width / (points.length - 1);
      final y = size.height - size.height * points[index].value / range;
      if (index == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
      canvas.drawCircle(Offset(x, y), AppSpacing.xs, paint);
    }
    canvas.drawPath(
      path,
      paint
        ..style = PaintingStyle.stroke
        ..strokeWidth = AppSpacing.xs,
    );
  }

  @override
  bool shouldRepaint(covariant _MetricChartPainter oldDelegate) =>
      oldDelegate.points != points ||
      oldDelegate.color != color ||
      oldDelegate.type != type;
}
