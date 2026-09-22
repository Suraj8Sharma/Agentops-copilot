import re

with open('mobile/lib/core/router.dart', 'r') as f:
    content = f.read()

replacement = """      case AppRoutes.planView:
        final taskId = settings.arguments as String?;
        return _page(PlanViewScreen(taskId: taskId ?? ''), settings);"""

content = re.sub(
    r"      case AppRoutes\.planView:\s*return _page\(const PlanViewScreen\(\), settings\);",
    replacement,
    content
)

with open('mobile/lib/core/router.dart', 'w') as f:
    f.write(content)
