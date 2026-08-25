-- Migration: 20260825000002_create_profiles
-- Idempotent: yes  Destructive: no

create table if not exists public.profiles (
    user_id              uuid        not null,
    display_name         text,
    email                text        not null,
    avatar_url           text,
    onboarding_completed boolean     not null default false,
    created_at           timestamptz not null default now(),
    constraint profiles_pkey primary key (user_id),
    constraint profiles_user_id_fkey
        foreign key (user_id) references auth.users (id) on delete cascade
);

alter table public.profiles enable row level security;

drop policy if exists "profiles_owner_select" on public.profiles;
create policy "profiles_owner_select" on public.profiles
    for select using (user_id = auth.uid());

drop policy if exists "profiles_owner_insert" on public.profiles;
create policy "profiles_owner_insert" on public.profiles
    for insert with check (user_id = auth.uid());

drop policy if exists "profiles_owner_update" on public.profiles;
create policy "profiles_owner_update" on public.profiles
    for update using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "profiles_owner_delete" on public.profiles;
create policy "profiles_owner_delete" on public.profiles
    for delete using (user_id = auth.uid());
