-- Migration: 20260909000009_create_execution_logs
-- Creates the execution_logs audit table.
-- Every node transition, tool call, and approval decision writes a row here
-- BEFORE it has any external effect (auditability by construction, Section 4.2).
-- Idempotent: yes  Destructive: no
-- Unplanned pull-forward from D22: required by D13/D14/D15 logging calls.

-- ---------------------------------------------
-- 1. Table
-- ---------------------------------------------

create table if not exists public.execution_logs (
    id             bigint       not null generated always as identity,
    task_id        uuid         not null,
    step_id        uuid,                        -- nullable: planner-level events have no step yet
    agent_name     text         not null,
    event_type     text         not null,
    payload        jsonb        not null,
    latency_ms     int,
    model_used     text,                        -- e.g. "groq:llama3-8b" | "gemini:flash", null for non-LLM events
    tokens_used    int,
    cost_estimate  numeric(10, 6),
    created_at     timestamptz  not null default now(),
    constraint execution_logs_pkey primary key (id),
    constraint execution_logs_task_id_fkey
        foreign key (task_id) references public.tasks (id) on delete cascade,
    constraint execution_logs_step_id_fkey
        foreign key (step_id) references public.plan_steps (id),
    constraint execution_logs_agent_name_check
        check (agent_name in (
            'planner', 'risk_gate', 'executor',
            'mcp_calendar', 'mcp_gmail', 'mcp_github', 'mcp_slack',
            'llm_router', 'banner_model'
        )),
    constraint execution_logs_event_type_check
        check (event_type in (
            'plan_created', 'risk_tagged',
            'approval_requested', 'approval_decided',
            'tool_called', 'tool_result',
            'step_started', 'step_completed', 'step_failed', 'step_awaiting_approval',
            'error'
        ))
);

-- ---------------------------------------------
-- 2. Indexes
-- ---------------------------------------------

-- RLS join path: every SELECT by the client resolves via task_id -> tasks.user_id.
create index if not exists execution_logs_task_id_idx
    on public.execution_logs (task_id);

-- Activity Log screen needs fast date-range + type filtering (Section 6).
create index if not exists execution_logs_created_at_idx
    on public.execution_logs (created_at desc);

-- ---------------------------------------------
-- 3. Row Level Security
-- ---------------------------------------------

alter table public.execution_logs enable row level security;

-- Authenticated users may SELECT only their own logs (via task ownership).
drop policy if exists "execution_logs_owner_select" on public.execution_logs;
create policy "execution_logs_owner_select" on public.execution_logs
    for select
    using (
        task_id in (
            select id from public.tasks where user_id = auth.uid()
        )
    );

-- INSERT is service-role only (no client-facing insert policy).
-- The backend uses the SUPABASE_SERVICE_ROLE_KEY to write audit rows.
