import re

with open('test/plan_view_screen_test.dart', 'r') as f:
    content = f.read()

# Add pumpAndSettle to planView pumps
content = re.sub(
    r"(await tester\.pumpWidget\(planView\([\s\S]*?\)\);)",
    r"\1\n    await tester.pumpAndSettle();",
    content
)

content = content.replace("    await tester.pumpAndSettle();\n    await tester.pumpAndSettle();", "    await tester.pumpAndSettle();")

with open('test/plan_view_screen_test.dart', 'w') as f:
    f.write(content)
