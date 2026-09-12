"""Configuration loader for AgentOps Copilot backend.

Reads environment variables using pydantic-settings and validates that all
required values are present at startup. Import the singleton ``settings``
object wherever config values are needed:

    from app.core.config import settings

No secret values are ever logged or printed — only keys are referenced in
error messages.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application settings.

    Required fields (no default) will raise a ``ValidationError`` at startup
    if the corresponding environment variable is missing or empty.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Extra env vars (future days) are ignored rather than raising an error.
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Supabase — required from D3
    # -------------------------------------------------------------------------
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # -------------------------------------------------------------------------
    # Supabase JWT — required from D5 (placeholder today)
    # -------------------------------------------------------------------------
    SUPABASE_JWT_SECRET: str = ""
    LANGGRAPH_CHECKPOINTER_DB_URI: str = ""

    # -------------------------------------------------------------------------
    # LLM APIs — required from D18 (placeholders today)
    # -------------------------------------------------------------------------
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # -------------------------------------------------------------------------
    # OAuth — required from D7 / D10 (placeholders today)
    # -------------------------------------------------------------------------
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = ""
    GITHUB_OAUTH_CLIENT_ID: str = ""
    GITHUB_OAUTH_CLIENT_SECRET: str = ""
    SLACK_CLIENT_ID: str = ""
    SLACK_CLIENT_SECRET: str = ""
    ENCRYPTION_KEY: str = ""

    # -------------------------------------------------------------------------
    # Cron / Internal jobs — required from D9
    # -------------------------------------------------------------------------
    # Secret used to authenticate calls to internal cron endpoints (e.g. sweep-tokens).
    # Set to any long random string; pass it as the Authorization header from your scheduler.
    CRON_SECRET: str = ""

    # -------------------------------------------------------------------------
    # Firebase / Render — required from D24 / D34 (placeholders today)
    # -------------------------------------------------------------------------
    FCM_SERVER_KEY: str = ""
    RENDER_DEPLOY_HOOK_URL: str = ""

    # -------------------------------------------------------------------------
    # D15 note: gmail.send_message routes through the Gmail REST API using the
    # user's own OAuth token (oauth_connections, provider='gmail').
    # No additional env vars are required for Gmail sending.
    # -------------------------------------------------------------------------


# Single shared instance — import this everywhere.
settings = Settings()
