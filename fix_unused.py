import re

with open('backend/app/tests/test_banner_model.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('patch("app.llm.router.log_llm_usage") as mock_log:', 'patch("app.llm.router.log_llm_usage"):')

with open('backend/app/tests/test_banner_model.py', 'w', encoding='utf-8') as f:
    f.write(content)
