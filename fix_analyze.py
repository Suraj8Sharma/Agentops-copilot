import re

with open('mobile/lib/features/oauth_connections/oauth_connections_screen.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix unused element _initialConnections
content = re.sub(r'final List<OAuthConnectionModel> _initialConnections = \[.*?\];', '', content, flags=re.DOTALL)

with open('mobile/lib/features/oauth_connections/oauth_connections_screen.dart', 'w', encoding='utf-8') as f:
    f.write(content)
