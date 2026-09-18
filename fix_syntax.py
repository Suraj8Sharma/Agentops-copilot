import re

with open('backend/app/notifications/banner_model.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('f"System: {BANNER_SYSTEM_PROMPT}\n\nUser: {user_prompt}"', 
                          'f"System: {BANNER_SYSTEM_PROMPT}\\n\\nUser: {user_prompt}"')

with open('backend/app/notifications/banner_model.py', 'w', encoding='utf-8') as f:
    f.write(content)
