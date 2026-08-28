-- Migration: 20260828000005_create_profile_trigger
-- Idempotent: yes  Destructive: no
--
-- Creates a PostgreSQL trigger that automatically inserts a row into
-- public.profiles whenever a new user is created in auth.users.

-- 1. Trigger function
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (user_id, email, created_at)
    values (
        new.id,
        new.email,
        now()
    )
    on conflict (user_id) do nothing;
    return new;
end;
$$;

-- 2. Trigger
drop trigger if exists on_auth_user_created on auth.users;

create trigger on_auth_user_created
    after insert on auth.users
    for each row
    execute function public.handle_new_user();