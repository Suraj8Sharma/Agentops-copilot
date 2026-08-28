-- Migration: 20260828000006_draft_rls_policies
-- Idempotent: yes  Destructive: no

-- Profiles
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

-- Tasks
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

-- OAuth Connections
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