-- D19 fix: Keep vector(768) column — no ALTER needed.
-- gemini-embedding-001 supports output_dimensionality=768 truncation,
-- so we truncate at the API call level in embeddings.py rather than
-- storing 3072-dim vectors (which would exceed the HNSW/IVFFlat 2000-dim limit).
-- The column, HNSW index, and RPC function created in migrations 12–14 remain valid.
-- This migration is intentionally a no-op to record the decision.
SELECT 1; -- no schema changes needed
