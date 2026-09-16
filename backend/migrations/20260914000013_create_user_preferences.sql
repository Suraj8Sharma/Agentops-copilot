-- D19: user_preferences table for structured, distilled preferences
-- Depends on: profiles table (already created)

CREATE TABLE IF NOT EXISTS user_preferences (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
    preference_key      TEXT NOT NULL,
    preference_value    JSONB NOT NULL,
    confidence          NUMERIC(3, 2) CHECK (confidence BETWEEN 0.00 AND 1.00),
    last_reinforced_at  TIMESTAMPTZ,
    source              TEXT NOT NULL CHECK (source IN ('extracted_from_memory', 'user_stated_in_settings')),

    -- One preference_key per user — upsert path relies on this
    UNIQUE (user_id, preference_key)
);

-- RLS: users manage their own preferences; service role can write on their behalf
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read their own preferences"
    ON user_preferences FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can insert their own preferences"
    ON user_preferences FOR INSERT
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update their own preferences"
    ON user_preferences FOR UPDATE
    USING (user_id = auth.uid());

CREATE POLICY "Users can delete their own preferences"
    ON user_preferences FOR DELETE
    USING (user_id = auth.uid());
