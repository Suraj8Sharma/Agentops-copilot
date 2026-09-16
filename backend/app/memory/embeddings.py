"""
memory/embeddings.py — Generate and store memory embeddings via Gemini.

D19: Uses Gemini text-embedding-004 (768-dim) to embed content_text and
     writes rows into the memory_embeddings table via the service-role client.

Note: Groq does not offer a text-embedding endpoint, so the LLM router is
      NOT used here. We call google-genai directly, matching the async pattern
      established in app/llm/gemini_client.py.

TODO(future): Wire store_memory() into the agent loop so it is called
              automatically after task completion (memory extraction step).
"""

import logging
import os
import time

from google import genai
from google.genai import types

from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

# Gemini embedding model — pinned to match the vector(3072) column dimension.
# text-embedding-004 is not available on v1beta; gemini-embedding-001 is the
# current supported model and outputs 3072-dim vectors.
# If this model is changed, a new migration re-creating the column is required.
EMBEDDING_MODEL = "models/gemini-embedding-001"


async def generate_embedding(text: str) -> list[float]:
    """
    Call Gemini text-embedding-004 to produce a 768-dimensional vector.

    Args:
        text: The content to embed.

    Returns:
        A plain list[float] of length 768, ready to pass to pgvector.

    Raises:
        ValueError: If GEMINI_API_KEY is not set.
        Exception:  Any Gemini API error propagates unchanged — do not swallow.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    client = genai.Client(api_key=api_key)

    start_time = time.time()
    response = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=768),
    )
    latency_ms = int((time.time() - start_time) * 1000)

    embedding = response.embeddings[0].values
    logger.debug(
        "Generated embedding | model=%s dim=%d latency_ms=%d",
        EMBEDDING_MODEL,
        len(embedding),
        latency_ms,
    )
    return list(embedding)


async def store_memory(
    user_id: str,
    content_text: str,
    category: str,
    source_task_id: str | None = None,
) -> int:
    """
    Generate an embedding for content_text and INSERT a row into memory_embeddings.

    Args:
        user_id:        UUID of the owning user.
        content_text:   The text to embed and store.
        category:       One of 'preference' | 'outcome' | 'correction'.
                        Enforced by a Postgres CHECK constraint.
        source_task_id: Optional FK to tasks(id) that produced this memory.

    Returns:
        The new row's id (bigint).

    Raises:
        ValueError:  If GEMINI_API_KEY is not set or category is invalid.
        Exception:   Gemini API errors or DB errors propagate unchanged.
    """
    valid_categories = {"preference", "outcome", "correction"}
    if category not in valid_categories:
        raise ValueError(f"Invalid category '{category}'. Must be one of: {valid_categories}")

    embedding = await generate_embedding(content_text)

    row = {
        "user_id": user_id,
        "content_text": content_text,
        # pgvector expects the vector as a string like "[0.1, 0.2, ...]"
        "embedding": str(embedding),
        "category": category,
    }
    if source_task_id is not None:
        row["source_task_id"] = source_task_id

    # Use service-role client — bypasses RLS for backend-initiated writes.
    result = supabase.table("memory_embeddings").insert(row).execute()

    new_id: int = result.data[0]["id"]
    logger.info(
        "Stored memory embedding | id=%d user_id=%s category=%s",
        new_id,
        user_id,
        category,
    )
    return new_id
