# D19 — Memory Embeddings + User Preferences (pgvector Retrieval)

**Manual reference:** Section 7 (Group D — Memory & Personalization), D19 day-plan cell
**Date:** Mon 14 Sep 2026
**Owner:** Suraj (backend/orchestration track)
**Depends on:** D18 (LLM router live — needed for embedding generation calls via Gemini), D12 (profiles table exists as FK target)

---

## 1. Why This Exists (plain language)

The planner today has no memory of past tasks — it starts from scratch every time. D19 lays the foundation for long-term personalization: a `memory_embeddings` table that stores embedded text from task outcomes and stated preferences, and a `user_preferences` table that holds structured, distilled preferences the planner can query on every call without running a similarity search.

The retrieval function built today (`retrieve_similar_memories`) is the one call site the planner nodes will use on D20+ to inject relevant past context into planning prompts. Building it as a standalone, independently testable function is the pattern established by D18's router — keep the infrastructure testable in isolation before it is wired into the agent.

Nothing about the planner's node logic changes today. This task is purely: schema + migrations + one Python retrieval function.

---

## 2. Scope

### In Scope
- Migration: `memory_embeddings` table with `vector(768)` column and HNSW index (cosine ops)
- Migration: `user_preferences` table with confidence scoring
- RLS policies for both tables (`user_id = auth.uid()`)
- `backend/app/memory/embeddings.py` — async function to generate and store an embedding
- `backend/app/memory/retrieval.py` — async function for pgvector similarity retrieval
- `backend/app/memory/preferences.py` — helpers to read/write structured `user_preferences` rows
- `.env` additions: none (GEMINI_API_KEY already set from D18; pgvector is a Supabase built-in)
- A minimal pytest file (`backend/app/tests/test_memory.py`) with two cases

### Out of Scope (explicitly deferred)
- **Wiring `nodes.py` to call the retrieval function.** Today's work builds memory as a self-contained, independently testable unit. Injecting retrieved context into planning prompts is a future task — do not touch `backend/app/agents/nodes.py` today.
- **Automatic memory extraction from task outcomes.** The write path (who calls `store_memory`) is not wired to the agent loop yet; the function must exist and be tested, but the trigger that fires it after task completion is deferred.
- **`memory_extraction` LLM call.** Determining which parts of a task outcome are worth storing as an embedding requires an LLM call with `request_type="memory_extraction"`. This call path is defined in the D18 router signature but not exercised today — only test with a hand-crafted content_text string.
- **`user_preferences` UI wiring.** Sanskriti's Memory/Preferences screen is wired to the real table on D21 (per the day plan). Today is backend-only.
- **Pagination / cursor support** for large embedding sets. Not needed at capstone scale.

---

## 3. Design Decisions (stated up front)

1. **768-dimension embeddings.** The schema pins `vector(768)` to match Gemini's `text-embedding-004` output dimension. If the model is swapped, the column must be re-created (new migration) — this is acceptable for a capstone build. Do not make the dimension a runtime variable.
2. **HNSW index, cosine ops.** Per Section 7.2 of the manual: `memory_embeddings.embedding` gets an HNSW index with `vector_cosine_ops`. This enables `<=>` cosine similarity queries at Supabase free-tier connection counts without an exact-scan fallback.
3. **Retrieval returns top-K rows ordered by cosine distance.** The retrieval function does not apply a hard similarity threshold — it returns the closest K results and lets the caller decide relevance. Threshold filtering is the planner node's concern, not the retrieval function's.
4. **Embeddings are generated via Gemini only.** `text-embedding-004` is a Gemini-specific model; the router is not used for embedding calls because Groq does not offer a text-embedding endpoint. Call `google-genai` directly in `embeddings.py` using the same async client pattern established in D18's `gemini_client.py`.
5. **`user_preferences` is a flat key-value store.** `preference_key` is a plain text key (e.g. `default_meeting_length`). The planner reads the full preference set for a user in one query, not per-key. No hierarchical namespacing needed at this scale.
6. **`source` column on `user_preferences` is controlled vocabulary.** Only two values: `extracted_from_memory` (written by future memory-extraction LLM pipeline) and `user_stated_in_settings` (written directly from the settings UI on D21). The migration adds a CHECK constraint enforcing this.

---

## 4. Environment Variables

No new variables. Verify the following are already present in `backend/.env`:

```
GEMINI_API_KEY=<already set from D18>
SUPABASE_URL=<already set>
SUPABASE_SERVICE_ROLE_KEY=<already set>
```

Also confirm `backend/.env.example` reflects these (no change needed if D18 was completed correctly).

---

## 5. Migrations

Two new migration files under `backend/migrations/`. Follow the existing naming convention: `YYYYMMDDNNNNNN_<description>.sql`.

### 5.1 `..._create_memory_embeddings.sql`

```sql
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
CREATE INDEX IF NOT EXISTS memory_embeddings_embedding_hnsw
    ON memory_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- RLS
ALTER TABLE memory_embeddings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read their own memory_embeddings"
    ON memory_embeddings FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Service role can insert memory_embeddings"
    ON memory_embeddings FOR INSERT
    WITH CHECK (true);  -- restricted to service-role key at client level
```

### 5.2 `..._create_user_preferences.sql`

```sql
CREATE TABLE IF NOT EXISTS user_preferences (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
    preference_key      TEXT NOT NULL,
    preference_value    JSONB NOT NULL,
    confidence          NUMERIC(3, 2) CHECK (confidence BETWEEN 0.00 AND 1.00),
    last_reinforced_at  TIMESTAMPTZ,
    source              TEXT NOT NULL CHECK (source IN ('extracted_from_memory', 'user_stated_in_settings')),

    UNIQUE (user_id, preference_key)
);

-- RLS
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read their own preferences"
    ON user_preferences FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can upsert their own preferences"
    ON user_preferences FOR INSERT
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update their own preferences"
    ON user_preferences FOR UPDATE
    USING (user_id = auth.uid());

CREATE POLICY "Users can delete their own preferences"
    ON user_preferences FOR DELETE
    USING (user_id = auth.uid());
```

---

## 6. File-by-File Specification

### 6.1 `backend/app/memory/embeddings.py`

```python
async def generate_embedding(text: str) -> list[float]:
    """
    Call Gemini text-embedding-004 to produce a 768-dim vector.
    Returns a plain list[float] ready to pass to pgvector.
    """
    ...

async def store_memory(
    user_id: str,
    content_text: str,
    category: str,                      # 'preference' | 'outcome' | 'correction'
    source_task_id: str | None = None,
) -> int:
    """
    Generate an embedding for content_text and INSERT a row into memory_embeddings.
    Returns the new row's id.
    """
    ...
```

- Use `genai.Client(api_key=os.environ["GEMINI_API_KEY"])` and `client.aio.models.embed_content(model="models/text-embedding-004", ...)` (the async path on `google-genai`).
- On a Gemini API error, let the exception propagate to the caller — do not swallow it.
- Use the `SUPABASE_SERVICE_ROLE_KEY` client for the INSERT (bypasses RLS safely for a backend-initiated write).

### 6.2 `backend/app/memory/retrieval.py`

```python
async def retrieve_similar_memories(
    user_id: str,
    query_text: str,
    top_k: int = 5,
    category: str | None = None,        # optional filter; None = all categories
) -> list[dict]:
    """
    Embed query_text, then return the top_k closest memory_embeddings rows
    for the given user, ordered by cosine distance (ascending, i.e. most similar first).
    Each dict contains: id, content_text, category, source_task_id, created_at, distance.
    """
    ...
```

- Generate the query embedding with `generate_embedding(query_text)` from `embeddings.py`.
- Issue a raw SQL query using Supabase's `.rpc()` or `.execute()` with the pgvector `<=>` operator:
  ```sql
  SELECT id, content_text, category, source_task_id, created_at,
         embedding <=> $1::vector AS distance
  FROM   memory_embeddings
  WHERE  user_id = $2
    AND  ($3::text IS NULL OR category = $3)
  ORDER  BY distance ASC
  LIMIT  $4;
  ```
- Return results as a list of plain dicts (not ORM objects) so callers have no dependency on a schema class.

### 6.3 `backend/app/memory/preferences.py`

```python
async def get_all_preferences(user_id: str) -> dict[str, Any]:
    """
    Return all user_preferences rows for this user as a flat dict:
    { preference_key: preference_value, ... }
    Ignores confidence and metadata — the planner only needs the key-value pairs.
    """
    ...

async def upsert_preference(
    user_id: str,
    preference_key: str,
    preference_value: Any,
    confidence: float,
    source: str,                        # 'extracted_from_memory' | 'user_stated_in_settings'
) -> None:
    """
    INSERT OR UPDATE (ON CONFLICT user_id, preference_key) a preference row.
    Updates preference_value, confidence, last_reinforced_at, and source.
    """
    ...
```

- Use the Supabase client's `.upsert()` method with `on_conflict="user_id,preference_key"`.
- `upsert_preference` should always update `last_reinforced_at = NOW()` in the same statement.

---

## 7. Error Handling Summary

| Scenario | Behavior |
|---|---|
| Gemini embedding call succeeds | Row inserted into `memory_embeddings`, return id |
| Gemini embedding call fails (API error / rate limit) | Propagate exception to caller — no silent swallow |
| pgvector retrieval query succeeds | Return list of result dicts |
| pgvector retrieval query fails (DB error) | Propagate exception; log error at call site |
| `upsert_preference` ON CONFLICT | Row updated in-place; no duplicate key error |
| Unknown `category` value passed | Postgres CHECK constraint rejects INSERT; caller receives DB error |
| Unknown `source` value passed | Postgres CHECK constraint rejects INSERT; caller receives DB error |

---

## 8. Testing Requirements for Today

Two minimum checks before calling D19 done — add to `backend/app/tests/test_memory.py`:

1. **Store and retrieve:** call `store_memory(user_id, "I prefer 30-minute meetings", category="preference")` with a real Gemini key, then call `retrieve_similar_memories(user_id, "meeting duration preference", top_k=1)` and assert the stored text appears as the top result.
2. **Preference upsert:** call `upsert_preference(user_id, "default_meeting_length", 30, confidence=0.9, source="user_stated_in_settings")` twice with different values, then call `get_all_preferences(user_id)` and assert only the latest value is returned (no duplicate rows).

A monkeypatched version of `generate_embedding` (returning a fake 768-dim vector of zeros) is acceptable for the second test to avoid a real Gemini call.

---

## 9. Open Items / Flags

- **`text-embedding-004` dimension:** Verify the output dimension is exactly 768 before running the migration. If Gemini changes the default output size for this model, the `vector(768)` column must match. Check with a one-off embedding call first.
- **pgvector on Supabase free tier:** The `vector` extension is pre-installed on Supabase. Just `CREATE EXTENSION IF NOT EXISTS vector;` — no extra configuration needed.
- **HNSW index build time:** HNSW index creation on an empty table is instant. For future reference: if the table is large, HNSW index creation can be slow. Not a concern today.
- **Service-role vs anon key:** `store_memory` must use the service-role key (bypasses RLS for backend writes). `retrieve_similar_memories` and preference helpers should use the JWT-scoped client where possible, or service-role with explicit `user_id` filtering — be consistent and document which is used and why.
- **`nodes.py` is untouched today** — as with D18, the infrastructure module is self-contained; wiring happens in a future task.

---

## 10. Acceptance for D19

- [ ] Migration `..._create_memory_embeddings.sql` applied; `memory_embeddings` table with `vector(768)` column and HNSW index visible in Supabase dashboard
- [ ] Migration `..._create_user_preferences.sql` applied; `user_preferences` table with UNIQUE `(user_id, preference_key)` constraint and CHECK constraints on `source` visible
- [ ] RLS enabled on both tables; policies match Section 5
- [ ] `backend/app/memory/embeddings.py` created with `generate_embedding` and `store_memory`
- [ ] `backend/app/memory/retrieval.py` created with `retrieve_similar_memories`
- [ ] `backend/app/memory/preferences.py` created with `get_all_preferences` and `upsert_preference`
- [ ] Store-and-retrieve test passes (real embedding, real similarity query)
- [ ] Preference upsert test passes (no duplicates, latest value returned)
- [ ] `nodes.py` is untouched
- [ ] `backend/app/memory/__init__.py` created (empty is fine)
