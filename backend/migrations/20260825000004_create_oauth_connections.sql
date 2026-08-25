-- Migration: 20260825000004_create_oauth_connections
-- access_token/refresh_token: PLAINTEXT PLACEHOLDERS pre-D8.
-- NO insert policy for authenticated role - INSERT is service-role only.
-- Idempotent: yes  Destructive: no

create table if not exists public.oauth_connections (
    id            uuid        not null default gen_random_uuid(),
    user_id       uuid        not null,
    provider      text        not null,
    access_token  text,
    refresh_token text,
    scopes        text[],
    expires_at    timestamptz,
    status        text        not null default 'active',
    connected_at  timestamptz not null default now(),
    constraint oauth_connections_pkey primary key (id),
    constraint oauth_connections_user_id_fkey
        foreign key (user_id) references public.profiles (user_id) on delete cascade,
    constraint oauth_connections_provider_check
        check (provider in ('google_calendar','gmail','github','slack')),
    constraint oauth_connections_status_check
        check (status in ('active','expired','revoked','scope_mismatch')),
    constraint oauth_connections_user_id_provider_key unique (user_id, provider)
);

create index if not exists oauth_connections_user_id_idx on public.oauth_connections (user_id);

alter table public.oauth_connections enable row level security;

drop policy if exists "oauth_connections_owner_select" on public.oauth_connections;
create policy "oauth_connections_owner_select" on public.oauth_connections
    for select using (user_id = auth.uid());

drop policy if exists "oauth_connections_owner_update" on public.oauth_connections;
create policy "oauth_connections_owner_update" on public.oauth_connections
    for update using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "oauth_connections_owner_delete" on public.oauth_connections;
create policy "oauth_connections_owner_delete" on public.oauth_connections
    for delete using (user_id = auth.uid());

