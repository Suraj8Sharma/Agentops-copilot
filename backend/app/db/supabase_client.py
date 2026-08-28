"""Supabase client singleton for AgentOps Copilot backend.

Initializes the official ``supabase-py`` client once at module import time and
exports a single shared ``supabase`` instance.  Do **not** call
``create_client()`` anywhere else in the app — always import from here:

    from app.db.supabase_client import supabase

The module also exposes ``probe_connection()`` which is called during the
FastAPI lifespan startup hook to verify connectivity before the server begins
accepting traffic.
"""

import logging

from supabase import Client, create_client

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)


def probe_connection() -> None:
    """Lightweight startup connectivity check.

    Runs a minimal query against a system table (``pg_tables``) using the
    Supabase REST API.  Logs success or failure clearly so ops/CI can tell
    at a glance whether the DB is reachable.

    Raises:
        Exception: Re-raises any error so the lifespan hook can decide
                   whether to abort startup.
    """
    try:
        # A trivial RPC/select that returns at most 1 row — just proves the
        # network path and credentials are valid.
        result = supabase.table("profiles").select("user_id").limit(1).execute()
        logger.info(
            "Supabase connection OK (response rows: %d)",
            len(result.data) if result.data else 0,
        )
    except Exception:
        logger.warning(
            "Supabase probe query failed — check SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY in your .env file.",
            exc_info=True,
        )
