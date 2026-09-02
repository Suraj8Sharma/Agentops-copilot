import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/theme.dart';

class DashboardMetricPoint {
  const DashboardMetricPoint({required this.label, required this.value});

  final String label;
  final double value;
}

class TrustDashboardMetrics {
  const TrustDashboardMetrics({
    required this.latency,
    required this.cost,
    required this.accuracy,
  });

  final List<DashboardMetricPoint> latency;
  final List<DashboardMetricPoint> cost;
  final List<DashboardMetricPoint> accuracy;
}

const mockTrustDashboardMetrics = TrustDashboardMetrics(
  latency: [
    DashboardMetricPoint(label: 'Mon', value: 1.8),
    DashboardMetricPoint(label: 'Tue', value: 2.4),
    DashboardMetricPoint(label: 'Wed', value: 2.1),
    DashboardMetricPoint(label: 'Thu', value: 3.0),
    DashboardMetricPoint(label: 'Fri', value: 2.6),
    DashboardMetricPoint(label: 'Sat', value: 2.2),
    DashboardMetricPoint(label: 'Sun', value: 2.0),
  ],
  cost: [
    DashboardMetricPoint(label: 'Mon', value: 0.08),
    DashboardMetricPoint(label: 'Tue', value: 0.12),
    DashboardMetricPoint(label: 'Wed', value: 0.09),
    DashboardMetricPoint(label: 'Thu', value: 0.15),
    DashboardMetricPoint(label: 'Fri', value: 0.11),
    DashboardMetricPoint(label: 'Sat', value: 0.07),
    DashboardMetricPoint(label: 'Sun', value: 0.10),
  ],
  accuracy: [
    DashboardMetricPoint(label: 'Mon', value: 94),
    DashboardMetricPoint(label: 'Tue', value: 96),
    DashboardMetricPoint(label: 'Wed', value: 95),
    DashboardMetricPoint(label: 'Thu', value: 97),
    DashboardMetricPoint(label: 'Fri', value: 96),
    DashboardMetricPoint(label: 'Sat', value: 98),
    DashboardMetricPoint(label: 'Sun', value: 97),
  ],
);

class TrustDashboardScreen extends StatelessWidget {
  const TrustDashboardScreen({super.key, this.metrics = mockTrustDashboardMetrics});

  final TrustDashboardMetrics metrics;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('trust-dashboard-screen'),
      appBar: AppBar(title: const Text('Trust Dashboard')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.screenPadding),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Agent performance at a glance',
                style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Mock data for the last 7 days. Live metrics will appear here later.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.lg),
            _MetricCard(
              key: const Key('latency-metric-card'),
              title: 'Latency',
              subtitle: 'p95 response time',
              value: '${_p95(metrics.latency).toStringAsFixed(1)}s',
              detail: 'Target: under 8s for simple tasks',
              color: AppColors.primary,
              points: metrics.latency,
              chartType: _ChartType.line,
            ),
            const SizedBox(height: AppSpacing.md),
            _MetricCard(
              key: const Key('cost-metric-card'),
              title: 'Cost',
              subtitle: 'LLM spend',
              value: '\$${metrics.cost.fold<double>(0, (sum, point) => sum + point.value).toStringAsFixed(2)}',
              detail: 'Groq and Gemini usage',
              color: AppColors.secondary,
              points: metrics.cost,
              chartType: _ChartType.bar,
            ),
            const SizedBox(height: AppSpacing.md),
            _MetricCard(
              key: const Key('accuracy-metric-card'),
              title: 'Accuracy',
              subtitle: 'Planner and router pass rate',
              value: '${_average(metrics.accuracy).toStringAsFixed(0)}%',
              detail: 'Based on mock evaluation runs',
              color: AppColors.success,
              points: metrics.accuracy,
              chartType: _ChartType.line,
            ),
            const SizedBox(height: AppSpacing.md),
            const _Legend(
              key: Key('dashboard-legend'),
              color: AppColors.warning,
              label: 'Fallback event',
              description: 'A rate-limit fallback will be visible when live data is connected.',
            ),
          ],
        ),
      ),
    );
  }

  static double _average(List<DashboardMetricPoint> points) {
    if (points.isEmpty) return 0;
    return points.fold<double>(0, (sum, point) => sum + point.value) / points.length;
  }

  static double _p95(List<DashboardMetricPoint> points) {
    if (points.isEmpty) return 0;
    final values = points.map((point) => point.value).toList()..sort();
    final index = math.min(values.length - 1, (values.length * 0.95).ceil() - 1);
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
            Text(title, key: Key('$title-metric-title'), style: textTheme.titleMedium),
            const SizedBox(height: AppSpacing.xs),
            Text(subtitle, style: textTheme.bodySmall),
            const SizedBox(height: AppSpacing.sm),
            Text(value, key: Key('$title-metric-value'), style: textTheme.headlineMedium),
            const SizedBox(height: AppSpacing.xs),
            Text(detail, style: textTheme.bodySmall),
            const SizedBox(height: AppSpacing.md),
            SizedBox(
              key: Key('$title-metric-chart'),
              height: AppSpacing.xxl,
              width: double.infinity,
              child: CustomPaint(
                painter: _MetricChartPainter(points: points, color: color, type: chartType),
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: points.map((point) => Text(point.label, style: textTheme.bodySmall)).toList(),
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
  _MetricChartPainter({required this.points, required this.color, required this.type});

  final List<DashboardMetricPoint> points;
  final Color color;
  final _ChartType type;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.isEmpty) return;
    final maxValue = points.map((point) => point.value).reduce(math.max);
    final range = maxValue == 0 ? 1 : maxValue;
    final paint = Paint()..color = color;
    if (type == _ChartType.bar) {
      final barWidth = size.width / (points.length * 2);
      for (var index = 0; index < points.length; index++) {
        final height = size.height * points[index].value / range;
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(index * size.width / points.length + barWidth / 2,
                size.height - height, barWidth, height),
            const Radius.circular(AppSpacing.xs),
          ),
          paint,
        );
      }
      return;
    }
    final path = Path();
    for (var index = 0; index < points.length; index++) {
      final x = points.length == 1 ? size.width / 2 : index * size.width / (points.length - 1);
      final y = size.height - size.height * points[index].value / range;
      if (index == 0) path.moveTo(x, y); else path.lineTo(x, y);
      canvas.drawCircle(Offset(x, y), AppSpacing.xs, paint);
    }
    canvas.drawPath(path, paint..style = PaintingStyle.stroke..strokeWidth = AppSpacing.xs);
  }

  @override
  bool shouldRepaint(covariant _MetricChartPainter oldDelegate) =>
      oldDelegate.points != points || oldDelegate.color != color || oldDelegate.type != type;
}
