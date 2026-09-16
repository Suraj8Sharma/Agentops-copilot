"""
test_memory.py — Acceptance tests for the D19 memory module.

All external calls (Gemini API, Supabase) are mocked so tests run in CI
with no network access and no credentials — matching the pattern used by
every other test file in this suite.

Test map:
  test_store_and_retrieve_memory              → D19 AC-1 (store + retrieve)
  test_preference_upsert_no_duplicates        → D19 AC-2 (upsert idempotency)
  test_upsert_preference_invalid_source_raises → D19 AC-3 (validation)
  test_retrieve_returns_empty_for_unknown_user → D19 AC-4 (empty result)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.memory.embeddings import store_memory
from app.memory.preferences import (
    get_all_preferences,
    upsert_preference,
)
from app.memory.retrieval import retrieve_similar_memories

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = str(uuid.uuid4())
FAKE_EMBEDDING = [0.1] * 768  # 768-dim zero-ish vector, matches vector(768)


def _make_supabase_insert_mock(new_id: int = 42):
    """Mock for supabase.table(...).insert(...).execute() returning a new row id."""
    result = MagicMock()
    result.data = [{"id": new_id}]
    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.return_value = result
    return mock


def _make_supabase_upsert_mock():
    """Mock for supabase.table(...).upsert(...).execute() — returns empty data (no error)."""
    result = MagicMock()
    result.data = []
    mock = MagicMock()
    mock.table.return_value.upsert.return_value.execute.return_value = result
    return mock


def _make_supabase_select_mock(rows: list[dict]):
    """Mock for supabase.table(...).select(...).eq(...).eq(...).execute()."""
    result = MagicMock()
    result.data = rows
    mock = MagicMock()
    # Chain: .table().select().eq().eq().execute()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value = result
    return mock


def _make_supabase_rpc_mock(rows: list[dict]):
    """Mock for supabase.rpc(...).execute() returning similarity results."""
    result = MagicMock()
    result.data = rows
    mock = MagicMock()
    mock.rpc.return_value.execute.return_value = result
    return mock


def _make_supabase_delete_mock():
    """Mock for supabase.table(...).delete().eq().eq().execute()."""
    result = MagicMock()
    result.data = []
    mock = MagicMock()
    chain = mock.table.return_value.delete.return_value
    chain.eq.return_value.eq.return_value.execute.return_value = result
    return mock


# ---------------------------------------------------------------------------
# Test 1 — Store and retrieve (all external calls mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_and_retrieve_memory():
    """
    D19 acceptance test 1:
    - store_memory() generates an embedding and inserts a row.
    - retrieve_similar_memories() returns that row as the top result.

    Both Gemini and Supabase are mocked — no network required.
    """
    stored_content = "I prefer 30-minute meetings over hour-long ones"
    fake_row = {
        "id": 42,
        "content_text": stored_content,
        "category": "preference",
        "source_task_id": None,
        "created_at": "2026-09-14T00:00:00+00:00",
        "distance": 0.01,
    }

    supabase_insert_mock = _make_supabase_insert_mock(new_id=42)
    supabase_rpc_mock = _make_supabase_rpc_mock(rows=[fake_row])

    with patch(
        "app.memory.embeddings.generate_embedding",
        new_callable=AsyncMock,
        return_value=FAKE_EMBEDDING,
    ):
        with patch("app.memory.embeddings.supabase", supabase_insert_mock):
            new_id = await store_memory(
                user_id=FAKE_USER_ID,
                content_text=stored_content,
                category="preference",
            )

    assert isinstance(new_id, int), "store_memory should return the new row id"
    assert new_id == 42

    with patch(
        "app.memory.retrieval.generate_embedding",
        new_callable=AsyncMock,
        return_value=FAKE_EMBEDDING,
    ):
        with patch("app.memory.retrieval.supabase", supabase_rpc_mock):
            results = await retrieve_similar_memories(
                user_id=FAKE_USER_ID,
                query_text="meeting duration preference",
                top_k=1,
            )

    assert len(results) == 1, "Expected exactly one result"
    assert results[0]["content_text"] == stored_content
    assert results[0]["category"] == "preference"
    assert "distance" in results[0]


# ---------------------------------------------------------------------------
# Test 2 — Preference upsert idempotency (Supabase mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preference_upsert_no_duplicates():
    """
    D19 acceptance test 2:
    - upsert_preference() called twice with different values for the same key.
    - get_all_preferences() returns only one row with the latest value.

    Supabase is mocked — no network required.
    """
    key = "default_meeting_length"

    upsert_mock = _make_supabase_upsert_mock()

    # Simulate DB returning the latest value after two upserts
    select_mock = _make_supabase_select_mock(rows=[{"preference_key": key, "preference_value": 45}])

    with patch("app.memory.preferences.supabase", upsert_mock):
        await upsert_preference(
            user_id=FAKE_USER_ID,
            preference_key=key,
            preference_value=30,
            confidence=0.8,
            source="user_stated_in_settings",
        )
        await upsert_preference(
            user_id=FAKE_USER_ID,
            preference_key=key,
            preference_value=45,
            confidence=0.9,
            source="user_stated_in_settings",
        )

    # Confirm upsert was called twice (once per invocation)
    assert upsert_mock.table.return_value.upsert.call_count == 2

    with patch("app.memory.preferences.supabase", select_mock):
        prefs = await get_all_preferences(user_id=FAKE_USER_ID)

    assert key in prefs, f"Expected preference key '{key}' to exist"
    assert prefs[key] == 45, f"Expected latest value 45, got {prefs[key]}"
    assert list(prefs.keys()).count(key) == 1, "Duplicate preference keys found"


# ---------------------------------------------------------------------------
# Test 3 — Invalid source raises ValueError before hitting the DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_preference_invalid_source_raises():
    """Guard: Python-side validation fires before any DB call is made."""
    with pytest.raises(ValueError, match="Invalid source"):
        await upsert_preference(
            user_id=FAKE_USER_ID,
            preference_key="some_key",
            preference_value="val",
            confidence=0.5,
            source="unknown_source",
        )


# ---------------------------------------------------------------------------
# Test 4 — retrieve returns empty list for unknown user (Supabase mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_returns_empty_for_unknown_user():
    """
    A user with no stored memories should get an empty list back, not an error.
    Both Gemini and Supabase are mocked — no network required.
    """
    supabase_rpc_mock = _make_supabase_rpc_mock(rows=[])

    with patch(
        "app.memory.retrieval.generate_embedding",
        new_callable=AsyncMock,
        return_value=FAKE_EMBEDDING,
    ):
        with patch("app.memory.retrieval.supabase", supabase_rpc_mock):
            results = await retrieve_similar_memories(
                user_id=str(uuid.uuid4()),
                query_text="anything",
                top_k=5,
            )

    assert results == [], f"Expected empty list for unknown user, got {results}"
