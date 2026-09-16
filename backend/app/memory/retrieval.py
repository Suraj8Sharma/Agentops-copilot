"""
memory/retrieval.py — pgvector similarity retrieval for long-term memory.

D19: Embeds a query string and returns the top-K closest memory_embeddings
     rows for a given user, ordered by cosine distance (ascending = most
     similar first).

Design decisions:
- No hard similarity threshold applied here. The caller (planner node) decides
  what distance is "relevant enough" — the retrieval function just ranks.
- category filter is optional: None = search across all categories.
- Results are plain dicts (not ORM objects) so callers have zero schema dependency.
- We use supabase.rpc() with a Postgres function for the <=> operator, since
  the supabase-py ORM does not expose pgvector operators natively.
"""

import logging

from app.db.supabase_client import supabase
from app.memory.embeddings import generate_embedding

logger = logging.getLogger(__name__)


async def retrieve_similar_memories(
    user_id: str,
    query_text: str,
    top_k: int = 5,
    category: str | None = None,
) -> list[dict]:
    """
    Embed query_text and return the top_k closest memory_embeddings rows
    for the given user, ordered by cosine distance (most similar first).

    Args:
        user_id:    UUID of the user whose memories to search.
        query_text: The natural-language query to embed and match against.
        top_k:      Number of results to return (default: 5).
        category:   Optional filter — 'preference' | 'outcome' | 'correction'.
                    None returns results across all categories.

    Returns:
        List of dicts, each containing:
            id, content_text, category, source_task_id, created_at, distance
        Ordered by distance ASC (index 0 = most similar).

    Raises:
        Exception: Gemini embedding errors or DB errors propagate unchanged.
    """
    query_embedding = await generate_embedding(query_text)

    # Convert to the "[x, y, z, ...]" string format pgvector expects
    embedding_str = str(query_embedding)

    # Call the Postgres RPC function (migration 14).
    # The <=> cosine distance operator and ORDER BY live in SQL,
    # not in Python string interpolation.
    result = supabase.rpc(
        "retrieve_similar_memories",
        {
            "p_user_id": user_id,
            "p_embedding": embedding_str,
            "p_category": category,
            "p_top_k": top_k,
        },
    ).execute()

    rows: list[dict] = result.data or []

    logger.info(
        "Memory retrieval | user_id=%s query_len=%d top_k=%d category=%s results=%d",
        user_id,
        len(query_text),
        top_k,
        category,
        len(rows),
    )
    return rows
