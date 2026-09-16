-- Migration: Create llm_usage_logs table
-- D21 task: llm_usage_logs + rate-limit backoff handling

CREATE TABLE IF NOT EXISTS public.llm_usage_logs (
    id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    provider text NOT NULL,
    model text NOT NULL,
    tokens_in int NOT NULL,
    tokens_out int NOT NULL,
    latency_ms int NOT NULL,
    request_type text NOT NULL,
    rate_limit_hit boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_provider CHECK (provider IN ('groq', 'gemini')),
    CONSTRAINT chk_request_type CHECK (request_type IN ('planning', 'routing', 'risk_explanation', 'banner', 'memory_extraction'))
);

-- Index for Trust Dashboard aggregations
CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_created_at ON public.llm_usage_logs (created_at);

-- Enable Row Level Security
ALTER TABLE public.llm_usage_logs ENABLE ROW LEVEL SECURITY;

-- No RLS policies are created. This ensures default deny for all authenticated users.
-- The backend will insert records using the Supabase service-role key, which bypasses RLS.
