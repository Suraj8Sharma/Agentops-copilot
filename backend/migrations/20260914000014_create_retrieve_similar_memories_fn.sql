-- D19: Postgres helper function for pgvector cosine similarity retrieval.
-- Called by backend/app/memory/retrieval.py via supabase.rpc().
--
-- The <=> operator (cosine distance) is only available in raw SQL, not via
-- the supabase-py ORM. Wrapping it in a SECURITY DEFINER function lets us
-- call it through the RPC endpoint while keeping RLS enforcement via the
-- explicit user_id filter.

CREATE OR REPLACE FUNCTION retrieve_similar_memories(
    p_user_id   UUID,
    p_embedding VECTOR(768),
    p_category  TEXT DEFAULT NULL,
    p_top_k     INT  DEFAULT 5
)
RETURNS TABLE (
    id              BIGINT,
    content_text    TEXT,
    category        TEXT,
    source_task_id  UUID,
    created_at      TIMESTAMPTZ,
    distance        FLOAT
)
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
    SELECT
        id,
        content_text,
        category,
        source_task_id,
        created_at,
        embedding <=> p_embedding AS distance
    FROM memory_embeddings
    WHERE user_id = p_user_id
      AND (p_category IS NULL OR category = p_category)
    ORDER BY distance ASC
    LIMIT p_top_k;
$$;
