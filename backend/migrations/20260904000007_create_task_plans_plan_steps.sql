-- Migration: 20260904000007_create_task_plans_plan_steps
-- Creates task_plans and plan_steps tables.
-- task_plans and plan_steps are WRITTEN by the service-role (planner).
-- Users can SELECT via join-based RLS through the tasks table.
-- Idempotent: yes  Destructive: no

-- ─────────────────────────────────────────────
-- 1. task_plans
-- ─────────────────────────────────────────────

create table if not exists public.task_plans (
    id               uuid        not null default gen_random_uuid(),
    task_id          uuid        not null,
    planner_version  text,
    plan_json        jsonb       not null,
    status           text        not null default 'draft',
    created_at       timestamptz not null default now(),
    constraint task_plans_pkey primary key (id),
    constraint task_plans_task_id_fkey
        foreign key (task_id) references public.tasks (id) on delete cascade,
    constraint task_plans_status_check
        check (status in ('draft', 'active', 'superseded'))
);

create index if not exists task_plans_task_id_idx on public.task_plans (task_id);

alter table public.task_plans enable row level security;

-- Users may read their own task_plans (via tasks.user_id).
-- No INSERT/UPDATE/DELETE policy for the authenticated role — service-role only.
drop policy if exists "task_plans_owner_select" on public.task_plans;
create policy "task_plans_owner_select" on public.task_plans
    for select
    using (
        exists (
            select 1
            from public.tasks t
            where t.id = task_plans.task_id
              and t.user_id = auth.uid()
        )
    );

-- ─────────────────────────────────────────────
-- 2. plan_steps
-- ─────────────────────────────────────────────

create table if not exists public.plan_steps (
    id                 uuid        not null default gen_random_uuid(),
    plan_id            uuid        not null,
    step_index         int         not null,
    tool_name          text        not null,
    mcp_server         text        not null,
    input_params       jsonb       not null,
    risk_tier          text        not null,
    requires_approval  boolean     not null,
    status             text        not null default 'pending',
    output             jsonb,
    executed_at        timestamptz,
    constraint plan_steps_pkey primary key (id),
    constraint plan_steps_plan_id_fkey
        foreign key (plan_id) references public.task_plans (id) on delete cascade,
    constraint plan_steps_mcp_server_check
        check (mcp_server in ('calendar', 'gmail', 'github', 'slack')),
    constraint plan_steps_risk_tier_check
        check (risk_tier in ('low', 'medium', 'high')),
    constraint plan_steps_status_check
        check (status in ('pending', 'awaiting_approval', 'approved', 'rejected',
                          'executing', 'done', 'failed'))
);

create index if not exists plan_steps_plan_id_idx on public.plan_steps (plan_id);

alter table public.plan_steps enable row level security;

-- Users may read their own plan_steps (via task_plans → tasks.user_id).
-- No INSERT/UPDATE/DELETE policy for the authenticated role — service-role only.
drop policy if exists "plan_steps_owner_select" on public.plan_steps;
create policy "plan_steps_owner_select" on public.plan_steps
    for select
    using (
        exists (
            select 1
            from public.task_plans tp
            join public.tasks t on t.id = tp.task_id
            where tp.id = plan_steps.plan_id
              and t.user_id = auth.uid()
        )
    );
