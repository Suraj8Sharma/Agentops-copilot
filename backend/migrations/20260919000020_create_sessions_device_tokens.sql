-- Migration: 20260919000020_create_sessions_device_tokens
-- Creates the sessions_device_tokens table for FCM push targets.
-- D24: notifications table + push endpoint (FCM integration)
-- Idempotent: yes  Destructive: no

create table if not exists public.sessions_device_tokens (
    id           uuid        not null default gen_random_uuid(),
    user_id      uuid        not null,
    fcm_token    text        not null,
    device_type  text,
    created_at   timestamptz not null default now(),
    last_active  timestamptz,

    constraint sessions_device_tokens_pkey primary key (id),
    constraint sessions_device_tokens_user_id_fkey
        foreign key (user_id) references public.profiles (user_id) on delete cascade,
    constraint sessions_device_tokens_device_type_check
        check (device_type in ('ios', 'android')),
    constraint sessions_device_tokens_user_token_unique
        unique (user_id, fcm_token)
);

create index if not exists sessions_device_tokens_user_id_idx
    on public.sessions_device_tokens (user_id);

alter table public.sessions_device_tokens enable row level security;

-- SELECT: users can see their own device tokens
drop policy if exists "device_tokens_owner_select" on public.sessions_device_tokens;
create policy "device_tokens_owner_select" on public.sessions_device_tokens
    for select
    using (user_id = auth.uid());

-- INSERT: users can register their own tokens
drop policy if exists "device_tokens_owner_insert" on public.sessions_device_tokens;
create policy "device_tokens_owner_insert" on public.sessions_device_tokens
    for insert
    with check (user_id = auth.uid());

-- UPDATE: users can update their own tokens (e.g. last_active)
drop policy if exists "device_tokens_owner_update" on public.sessions_device_tokens;
create policy "device_tokens_owner_update" on public.sessions_device_tokens
    for update
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- DELETE: users can revoke their own tokens (on logout/uninstall)
drop policy if exists "device_tokens_owner_delete" on public.sessions_device_tokens;
create policy "device_tokens_owner_delete" on public.sessions_device_tokens
    for delete
    using (user_id = auth.uid());
