import re

with open('mobile/test/plan_view_screen_test.dart', 'r') as f:
    content = f.read()

# Add pumpAndSettle to planView pumps
content = re.sub(
    r"(await tester\.pumpWidget\(planView\([^)]*\)\);)",
    r"\1\n    await tester.pumpAndSettle();",
    content
)

with open('mobile/test/plan_view_screen_test.dart', 'w') as f:
    f.write(content)
