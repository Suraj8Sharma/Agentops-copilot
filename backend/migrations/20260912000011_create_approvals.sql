CREATE TABLE IF NOT EXISTS public.approvals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    step_id uuid NOT NULL REFERENCES public.plan_steps(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES public.profiles(user_id) ON DELETE CASCADE,
    decision text, -- 'approved' | 'rejected', null while pending
    explanation_text text,
    decided_at timestamptz,
    response_time_ms integer,
    created_at timestamptz DEFAULT now()
);

-- RLS: user_id = auth.uid() for SELECT/UPDATE. INSERT restricted to backend (service role).
ALTER TABLE public.approvals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own approvals"
    ON public.approvals
    FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can update their own approvals"
    ON public.approvals
    FOR UPDATE
    USING (user_id = auth.uid());

-- Index step_id
CREATE INDEX idx_approvals_step_id ON public.approvals(step_id);
