import re

with open('backend/app/tests/test_banner_model.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the sys.modules mock
content = re.sub(r"import sys\nfrom unittest\.mock import AsyncMock, MagicMock, patch\n\nsys\.modules\[\"google\"\] = MagicMock\(\)\nsys\.modules\[\"google\.genai\"\] = MagicMock\(\)", "from unittest.mock import AsyncMock, patch", content)

with open('backend/app/tests/test_banner_model.py', 'w', encoding='utf-8') as f:
    f.write(content)
