import re

with open('backend/app/tests/test_banner_model.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the one I broke
content = content.replace('with patch("app.llm.router.log_llm_usage"):\n                event = {"type": "digest_ready", "digest_period": "daily"}',
                          'with patch("app.llm.router.log_llm_usage") as mock_log:\n                event = {"type": "digest_ready", "digest_period": "daily"}')

with open('backend/app/tests/test_banner_model.py', 'w', encoding='utf-8') as f:
    f.write(content)
