import re

with open('backend/app/notifications/banner_model.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("import logging\nfrom app.llm.router import route_llm_call\n\n_logger = logging.getLogger(__name__)\n\nasync def", "async def")

content = content.replace("from __future__ import annotations", "from __future__ import annotations\n\nimport logging\nfrom app.llm.router import route_llm_call\n\n_logger = logging.getLogger(__name__)")

with open('backend/app/notifications/banner_model.py', 'w', encoding='utf-8') as f:
    f.write(content)
