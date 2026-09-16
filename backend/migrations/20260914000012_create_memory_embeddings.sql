-- D19: memory_embeddings table with pgvector for long-term memory
-- Depends on: profiles, tasks tables (already created)

-- Enable pgvector extension (idempotent; safe to re-run)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memory_embeddings (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
    content_text    TEXT NOT NULL,
    embedding       VECTOR(768) NOT NULL,
    category        TEXT CHECK (category IN ('preference', 'outcome', 'correction')),
    source_task_id  UUID REFERENCES tasks(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW index: cosine similarity, matches the retrieval operator <=>
-- Per Section 7.2: HNSW with vector_cosine_ops for nearest-neighbour retrieval
CREATE INDEX IF NOT EXISTS memory_embeddings_embedding_hnsw
    ON memory_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- RLS
ALTER TABLE memory_embeddings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read their own memory_embeddings"
    ON memory_embeddings FOR SELECT
    USING (user_id = auth.uid());

-- INSERT is service-role only (backend writes on behalf of user)
CREATE POLICY "Service role can insert memory_embeddings"
    ON memory_embeddings FOR INSERT
    WITH CHECK (true);
