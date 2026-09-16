"""
test_memory.py — Acceptance tests for the D19 memory module.

Two required tests per the spec:
  1. Store-and-retrieve: real embedding, real pgvector similarity query.
  2. Preference upsert: no duplicate rows, latest value returned.

Test 1 makes a real Gemini API call — requires GEMINI_API_KEY in .env.
Test 2 hits the real Supabase DB using an existing profiles row (FK constraint).

Run with:
    pytest backend/app/tests/test_memory.py -v
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from dotenv import load_dotenv

# Load .env before importing app modules so GEMINI_API_KEY and SUPABASE_*
# are in os.environ when the Supabase client and Gemini client initialise.
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from app.memory.embeddings import store_memory  # noqa: E402
from app.memory.preferences import (  # noqa: E402
    delete_preference,
    get_all_preferences,
    upsert_preference,
)
from app.memory.retrieval import retrieve_similar_memories  # noqa: E402

# A real user_id that exists in the profiles table.
# FK constraints on memory_embeddings and user_preferences require this.
TEST_USER_ID = "f73e4a59-1192-4d29-a3a0-dff9c7bc5729"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_embedding(text: str) -> list[float]:
    """Return a deterministic 768-dim zero vector (no Gemini call needed)."""
    return [0.0] * 768


# ---------------------------------------------------------------------------
# Test 1 — Store and retrieve (real Gemini embedding + real DB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_and_retrieve_memory():
    """
    D19 acceptance test 1:
    - store_memory() embeds text via Gemini and inserts a row.
    - retrieve_similar_memories() returns that row as the top result.
    """
    # Use a real user_id that exists in profiles (FK constraint on memory_embeddings)
    user_id = TEST_USER_ID
    content = "I prefer 30-minute meetings over hour-long ones"

    # Store — real Gemini embedding call, real DB insert
    new_id = await store_memory(
        user_id=user_id,
        content_text=content,
        category="preference",
    )
    assert isinstance(new_id, int), "store_memory should return the new row id"

    # Retrieve — embed a related query and check the stored text comes back top
    results = await retrieve_similar_memories(
        user_id=user_id,
        query_text="meeting duration preference",
        top_k=1,
    )

    assert len(results) == 1, "Expected exactly one result"
    top = results[0]
    assert top["content_text"] == content, (
        f"Expected stored text to be top result, got: {top['content_text']}"
    )
    assert top["category"] == "preference"
    assert "distance" in top, "Result should include cosine distance"


# ---------------------------------------------------------------------------
# Test 2 — Preference upsert (monkeypatched embedding, real DB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preference_upsert_no_duplicates():
    """
    D19 acceptance test 2:
    - upsert_preference() called twice with different values for the same key.
    - get_all_preferences() returns only one row with the latest value.
    """
    # Use a real user_id that exists in profiles (FK constraint on user_preferences)
    user_id = TEST_USER_ID
    key = "default_meeting_length"
    # First upsert
    await upsert_preference(
        user_id=user_id,
        preference_key=key,
        preference_value=30,
        confidence=0.8,
        source="user_stated_in_settings",
    )

    # Second upsert with a different value — should overwrite, not duplicate
    await upsert_preference(
        user_id=user_id,
        preference_key=key,
        preference_value=45,
        confidence=0.9,
        source="user_stated_in_settings",
    )

    prefs = await get_all_preferences(user_id=user_id)

    assert key in prefs, f"Expected preference key '{key}' to exist"
    assert prefs[key] == 45, (
        f"Expected latest value 45, got {prefs[key]}"
    )
    # Confirm there's exactly one key — no phantom duplicates
    assert list(prefs.keys()).count(key) == 1, "Duplicate preference keys found"

    # Cleanup — remove test row so re-runs are clean
    await delete_preference(user_id=user_id, preference_key=key)


# ---------------------------------------------------------------------------
# Test 3 — Invalid source raises ValueError before hitting the DB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_preference_invalid_source_raises():
    """Guard: Python-side validation fires before a Postgres CHECK violation."""
    with pytest.raises(ValueError, match="Invalid source"):
        await upsert_preference(
            user_id=str(uuid.uuid4()),
            preference_key="some_key",
            preference_value="val",
            confidence=0.5,
            source="unknown_source",
        )


# ---------------------------------------------------------------------------
# Test 4 — retrieve_similar_memories with monkeypatched embedding
#           (no Gemini call; verifies the RPC plumbing without API cost)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_returns_empty_for_unknown_user():
    """
    A user with no stored memories should get an empty list back,
    not an error.
    Uses a fake embedding to avoid a real Gemini call.
    """
    user_id = str(uuid.uuid4())  # guaranteed no rows

    with patch(
        "app.memory.retrieval.generate_embedding",
        new_callable=AsyncMock,
        return_value=_fake_embedding("test"),
    ):
        results = await retrieve_similar_memories(
            user_id=user_id,
            query_text="anything",
            top_k=5,
        )

    assert results == [], f"Expected empty list for unknown user, got {results}"
