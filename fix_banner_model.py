import re

with open('backend/app/notifications/banner_model.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_func = """import logging
from app.llm.router import route_llm_call

_logger = logging.getLogger(__name__)

async def generate_banner(event: dict) -> str | None:
    \"\"\"
    Generate a short banner line for a notification event.

    Args:
        event: Notification event dict. See module docstring for full shape.

    Returns:
        A short banner string (<= 80 chars), or None if generation fails.
    \"\"\"
    event_type = event.get("type")
    if event_type not in BANNER_DEFAULTS:
        _logger.error(f"Unknown notification event type: {event_type}")
        return None
        
    user_prompt = build_banner_user_prompt(event)
    
    full_prompt = f"System: {BANNER_SYSTEM_PROMPT}\\n\\nUser: {user_prompt}"
    
    try:
        response = await route_llm_call(
            prompt=full_prompt,
            request_type="banner"
        )
        
        if not response or not response.text:
            return BANNER_DEFAULTS.get(event_type)
            
        banner_text = response.text.strip()
        
        if len(banner_text) > BANNER_MAX_CHARS:
            _logger.warning(f"Banner exceeded {BANNER_MAX_CHARS} chars, truncating.")
            banner_text = banner_text[:BANNER_MAX_CHARS - 3] + "..."
            
        return banner_text
    except Exception as e:
        _logger.error(f"Failed to generate banner: {e}", exc_info=True)
        return None
"""

content = re.sub(
    r"def generate_banner\(event: dict\) -> str \| None:[\s\S]*?raise NotImplementedError\([\s\S]*?\)",
    new_func,
    content
)

with open('backend/app/notifications/banner_model.py', 'w', encoding='utf-8') as f:
    f.write(content)
