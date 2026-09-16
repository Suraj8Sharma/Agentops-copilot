"""
memory/preferences.py — Read and write structured user preferences.

D19: Provides helpers to read/write the user_preferences table.
     The planner calls get_all_preferences() to inject context into prompts
     without running a full vector similarity search on every task.

Design decisions:
- get_all_preferences() returns a flat {key: value} dict — the planner only
  needs the key-value pairs, not confidence/metadata.
- upsert_preference() uses ON CONFLICT (user_id, preference_key) DO UPDATE
  so duplicate keys are never created and last_reinforced_at stays current.
- source is validated in Python before hitting the DB CHECK constraint so
  callers get a clear ValueError rather than a cryptic Postgres error.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

VALID_SOURCES = {"extracted_from_memory", "user_stated_in_settings"}


async def get_all_preferences(user_id: str) -> dict[str, Any]:
    """
    Return all user_preferences rows for this user as a flat key-value dict.

    Args:
        user_id: UUID of the user.

    Returns:
        { preference_key: preference_value, ... }
        Empty dict if the user has no stored preferences.

    Raises:
        Exception: DB errors propagate unchanged.
    """
    result = (
        supabase.table("user_preferences")
        .select("preference_key, preference_value")
        .eq("user_id", user_id)
        .execute()
    )

    rows = result.data or []
    preferences = {row["preference_key"]: row["preference_value"] for row in rows}

    logger.debug(
        "Fetched preferences | user_id=%s count=%d",
        user_id,
        len(preferences),
    )
    return preferences


async def upsert_preference(
    user_id: str,
    preference_key: str,
    preference_value: Any,
    confidence: float,
    source: str,
) -> None:
    """
    Insert or update a single user preference row.

    ON CONFLICT (user_id, preference_key) updates preference_value,
    confidence, last_reinforced_at, and source in-place — no duplicate rows.

    Args:
        user_id:          UUID of the user.
        preference_key:   Plain text key, e.g. 'default_meeting_length'.
        preference_value: Any JSON-serialisable value.
        confidence:       Float between 0.00 and 1.00.
                          Enforced by Postgres CHECK constraint.
        source:           'extracted_from_memory' | 'user_stated_in_settings'.

    Raises:
        ValueError: If source is not a recognised value or confidence is out
                    of range (fast-fail before hitting the DB constraint).
        Exception:  DB errors propagate unchanged.
    """
    if source not in VALID_SOURCES:
        raise ValueError(
            f"Invalid source '{source}'. Must be one of: {VALID_SOURCES}"
        )
    if not (0.00 <= confidence <= 1.00):
        raise ValueError(
            f"confidence must be between 0.00 and 1.00, got {confidence}"
        )

    now = datetime.now(timezone.utc).isoformat()

    row = {
        "user_id": user_id,
        "preference_key": preference_key,
        "preference_value": preference_value,
        "confidence": confidence,
        "last_reinforced_at": now,
        "source": source,
    }

    supabase.table("user_preferences").upsert(
        row,
        on_conflict="user_id,preference_key",
    ).execute()

    logger.info(
        "Upserted preference | user_id=%s key=%s source=%s confidence=%.2f",
        user_id,
        preference_key,
        source,
        confidence,
    )


async def delete_preference(user_id: str, preference_key: str) -> None:
    """
    Delete a single preference by key.
    No-op if the key doesn't exist (idempotent).

    Args:
        user_id:        UUID of the user.
        preference_key: Key to remove.
    """
    supabase.table("user_preferences").delete().eq(
        "user_id", user_id
    ).eq("preference_key", preference_key).execute()

    logger.info(
        "Deleted preference | user_id=%s key=%s",
        user_id,
        preference_key,
    )
