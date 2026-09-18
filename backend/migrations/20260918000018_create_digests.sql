-- Migration: 20260918000018_create_digests
-- Creates the digests table for daily/weekly task summaries.
-- D23: digests table + Digest Generation Job
-- Idempotent: yes  Destructive: no

-- ---------------------------------------------
-- 1. Table
-- ---------------------------------------------

create table if not exists public.digests (
    id            uuid         not null default gen_random_uuid(),
    user_id       uuid         not null,
    period_type   text         not null,
    summary_text  text         not null,
    tasks_included jsonb,                           -- JSON array of task_id strings that fed this digest
    generated_at  timestamptz  not null default now(),

    constraint digests_pkey primary key (id),
    constraint digests_user_id_fkey
        foreign key (user_id) references public.profiles (user_id) on delete cascade,
    constraint digests_period_type_check
        check (period_type in ('daily', 'weekly'))
);

-- ---------------------------------------------
-- 2. Indexes
-- ---------------------------------------------

-- User-scoped reads: all digest queries filter by user_id first.
create index if not exists digests_user_id_idx
    on public.digests (user_id);

-- Newest-first ordering + date-range queries (Trust Dashboard pattern).
create index if not exists digests_generated_at_idx
    on public.digests (generated_at desc);

-- ---------------------------------------------
-- 3. Row Level Security
-- ---------------------------------------------

alter table public.digests enable row level security;

-- SELECT: users see only their own digest rows.
drop policy if exists "digests_owner_select" on public.digests;
create policy "digests_owner_select" on public.digests
    for select
    using (user_id = auth.uid());

-- INSERT: WITH CHECK (not USING) — USING only applies to existing rows.
-- The backend digest job uses the service-role key and bypasses RLS for inserts.
-- This policy is a safety net if a user-scoped client ever attempts an insert.
drop policy if exists "digests_owner_insert" on public.digests;
create policy "digests_owner_insert" on public.digests
    for insert
    with check (user_id = auth.uid());

-- UPDATE: users can only update their own rows.
drop policy if exists "digests_owner_update" on public.digests;
create policy "digests_owner_update" on public.digests
    for update
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- DELETE: users can only delete their own rows.
drop policy if exists "digests_owner_delete" on public.digests;
create policy "digests_owner_delete" on public.digests
    for delete
    using (user_id = auth.uid());
