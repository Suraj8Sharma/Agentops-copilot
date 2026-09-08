from backend.app.core.config import settings
assert settings.GOOGLE_OAUTH_CLIENT_ID != "", "Google client ID not loaded"
print(settings.GOOGLE_OAUTH_CLIENT_ID[:12])  # sanity check, never print the secret