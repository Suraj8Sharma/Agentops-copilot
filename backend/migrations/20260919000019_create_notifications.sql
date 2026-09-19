-- Migration: 20260919000019_create_notifications
-- Creates the notifications table for in-app + push notification records.
-- D24: notifications table + push endpoint (FCM integration)
-- Idempotent: yes  Destructive: no

create table if not exists public.notifications (
    id               uuid        not null default gen_random_uuid(),
    user_id          uuid        not null,
    type             text        not null,
    title            text        not null,
    body             text        not null,
    banner_text      text,                           -- nullable: LLM-written advisory copy
    read             boolean     not null default false,
    related_task_id  uuid,
    created_at       timestamptz not null default now(),

    constraint notifications_pkey primary key (id),
    constraint notifications_user_id_fkey
        foreign key (user_id) references public.profiles (user_id) on delete cascade,
    constraint notifications_related_task_id_fkey
        foreign key (related_task_id) references public.tasks (id) on delete set null,
    constraint notifications_type_check
        check (type in ('approval_needed', 'task_completed', 'digest_ready', 'oauth_expiring'))
);

-- Indexes
create index if not exists notifications_user_id_idx
    on public.notifications (user_id);

create index if not exists notifications_created_at_idx
    on public.notifications (created_at desc);

create index if not exists notifications_user_read_idx
    on public.notifications (user_id, read);

-- RLS
alter table public.notifications enable row level security;

-- SELECT: users see only their own notifications
drop policy if exists "notifications_owner_select" on public.notifications;
create policy "notifications_owner_select" on public.notifications
    for select
    using (user_id = auth.uid());

-- UPDATE: users can mark their own notifications as read (no other mutation allowed client-side)
drop policy if exists "notifications_owner_update" on public.notifications;
create policy "notifications_owner_update" on public.notifications
    for update
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- INSERT: service-role only; no client policy (RLS default deny)
-- DELETE: service-role only; no client policy
