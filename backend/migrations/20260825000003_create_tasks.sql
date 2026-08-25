-- Migration: 20260825000003_create_tasks
-- Idempotent: yes  Destructive: no

create table if not exists public.tasks (
    id                 uuid        not null default gen_random_uuid(),
    user_id            uuid        not null,
    input_type         text        not null,
    raw_input          text,
    transcription_text text,
    status             text        not null default 'submitted',
    created_at         timestamptz not null default now(),
    completed_at       timestamptz,
    constraint tasks_pkey primary key (id),
    constraint tasks_user_id_fkey
        foreign key (user_id) references public.profiles (user_id) on delete cascade,
    constraint tasks_input_type_check check (input_type in ('text', 'voice')),
    constraint tasks_status_check
        check (status in ('submitted','planning','awaiting_approval','executing','completed','failed','cancelled'))
);

create index if not exists tasks_user_id_idx on public.tasks (user_id);

alter table public.tasks enable row level security;

drop policy if exists "tasks_owner_select" on public.tasks;
create policy "tasks_owner_select" on public.tasks
    for select using (user_id = auth.uid());

drop policy if exists "tasks_owner_insert" on public.tasks;
create policy "tasks_owner_insert" on public.tasks
    for insert with check (user_id = auth.uid());

drop policy if exists "tasks_owner_update" on public.tasks;
create policy "tasks_owner_update" on public.tasks
    for update using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "tasks_owner_delete" on public.tasks;
create policy "tasks_owner_delete" on public.tasks
    for delete using (user_id = auth.uid());
