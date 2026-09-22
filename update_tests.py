import re

with open('mobile/test/plan_view_screen_test.dart', 'r') as f:
    content = f.read()

# Add plan_service import
if "plan_service.dart" not in content:
    content = content.replace(
        "import 'package:agentops_copilot/features/plan_view/plan_view_screen.dart';",
        "import 'package:agentops_copilot/features/plan_view/plan_view_screen.dart';\nimport 'package:agentops_copilot/features/plan_view/plan_service.dart';"
    )

# Replace the planView widget builder
old_builder = r"  Widget planView\(\{MockPlan plan = mockPlan\}\) => MaterialApp\([\s\S]*?home: PlanViewScreen\(plan: plan\),[\s\S]*?\);"
new_builder = """  Widget planView({MockPlan plan = mockPlan}) {
    PlanService.fetchPlanOverride = (_) async => plan;
    return MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    );
  }"""
content = re.sub(old_builder, new_builder, content)

# Need to fix the routing test at the bottom
old_routing = r"          return MaterialPageRoute<void>\([\s\S]*?builder: \(\_\) => const PlanViewScreen\(\),[\s\S]*?\);"
new_routing = """          final taskId = settings.arguments as String?;
          return MaterialPageRoute<void>(
            builder: (_) => PlanViewScreen(taskId: taskId ?? ''),
          );"""
content = re.sub(old_routing, new_routing, content)

# Also test error and loading state
test_additions = """
  testWidgets('shows loading state initially', (tester) async {
    import 'dart:async';
    final completer = Completer<MockPlan>();
    PlanService.fetchPlanOverride = (_) => completer.future;

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    ));

    expect(find.text('Waking up backend...'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('shows error state when fetching fails', (tester) async {
    PlanService.fetchPlanOverride = (_) async => throw Exception('Network error');

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Failed to load plan'), findsOneWidget);
    expect(find.text('Exception: Network error'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('shows waiting state when plan is not found', (tester) async {
    PlanService.fetchPlanOverride = (_) async => throw const PlanNotFoundException('Plan not ready yet');

    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.light,
      home: const PlanViewScreen(taskId: 'task-123'),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('empty-plan-state')), findsOneWidget);
    expect(find.text('No steps planned yet'), findsOneWidget);
  });
"""

content = content.replace("  testWidgets('home task tiles route to the plan view'", test_additions + "\n  testWidgets('home task tiles route to the plan view'")

# The test uses `import 'dart:async';` inside the function, let's just move it up
content = content.replace("    import 'dart:async';\n", "")
if "import 'dart:async';" not in content:
    content = "import 'dart:async';\n" + content

with open('mobile/test/plan_view_screen_test.dart', 'w') as f:
    f.write(content)
