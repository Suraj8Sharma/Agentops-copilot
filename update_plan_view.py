import re

with open('mobile/lib/features/plan_view/plan_view_screen.dart', 'r') as f:
    content = f.read()

# Add import for plan_service
if "plan_service.dart" not in content:
    content = content.replace(
        "import '../../core/theme.dart';",
        "import '../../core/theme.dart';\nimport 'plan_service.dart';"
    )

# Replace PlanViewScreen class
old_screen = r"class PlanViewScreen extends StatelessWidget \{[\s\S]*?\n\}"

new_screen = """class PlanViewScreen extends StatefulWidget {
  const PlanViewScreen({super.key, required this.taskId});

  final String taskId;

  @override
  State<PlanViewScreen> createState() => _PlanViewScreenState();
}

class _PlanViewScreenState extends State<PlanViewScreen> {
  MockPlan? _plan;
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _fetchPlan();
  }

  Future<void> _fetchPlan() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final plan = await PlanService.fetchPlan(widget.taskId);
      if (!mounted) return;
      setState(() {
        _plan = plan;
        _isLoading = false;
      });
    } on PlanNotFoundException catch (_) {
      if (!mounted) return;
      setState(() {
        _plan = null;
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Agent Plan View')),
      body: SafeArea(
        child: _buildBody(context),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isLoading) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            CircularProgressIndicator(),
            SizedBox(height: AppSpacing.md),
            Text('Waking up backend...'),
          ],
        ),
      );
    }

    if (_errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              const Icon(Icons.error_outline, color: AppColors.error, size: AppSpacing.xxl),
              const SizedBox(height: AppSpacing.md),
              Text('Failed to load plan', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: AppSpacing.xs),
              Text(_errorMessage!, textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodyMedium),
              const SizedBox(height: AppSpacing.lg),
              ElevatedButton.icon(
                onPressed: _fetchPlan,
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    if (_plan == null) {
      return const Center(child: _EmptyPlanState());
    }

    final plan = _plan!;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.screenPadding),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Your copilot\\'s plan', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Review the sequence before any action runs.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: AppSpacing.md),
          _PlanSummary(plan: plan),
          const SizedBox(height: AppSpacing.lg),
          if (plan.steps.isEmpty)
            const _EmptyPlanState()
          else
            ...plan.steps.asMap().entries.map(
                  (entry) => _PlanStepCard(
                    step: entry.value,
                    isLast: entry.key == plan.steps.length - 1,
                  ),
                ),
        ],
      ),
    );
  }
}"""

content = re.sub(old_screen, new_screen, content)

with open('mobile/lib/features/plan_view/plan_view_screen.dart', 'w') as f:
    f.write(content)
