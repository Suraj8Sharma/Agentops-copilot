-- ============================================================
-- verify_schema.sql
-- Run this in the Supabase SQL Editor (or via psql) AFTER
-- applying all four migrations to confirm every acceptance
-- criterion from the spec is satisfied.
-- ============================================================

-- -- AC1: All three tables exist with correct columns -------------------------
select
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
from information_schema.columns
where table_schema = 'public'
  and table_name   in ('profiles', 'tasks', 'oauth_connections')
order by table_name, ordinal_position;

-- -- AC2: RLS is enabled on all three tables ----------------------------------
select
    tablename,
    rowsecurity as rls_enabled
from pg_tables
where schemaname = 'public'
  and tablename  in ('profiles', 'tasks', 'oauth_connections');

-- -- AC3: Exact policy set per table ------------------------------------------
-- Expected:
--   profiles          -> 4 policies (select, insert, update, delete)
--   tasks             -> 4 policies (select, insert, update, delete)
--   oauth_connections -> 3 policies (select, update, delete — NO insert)
select
    tablename,
    policyname,
    cmd          as "for",
    qual         as "using",
    with_check
from pg_policies
where schemaname = 'public'
  and tablename  in ('profiles', 'tasks', 'oauth_connections')
order by tablename, policyname;

-- -- AC4: Indexes on FK columns ------------------------------------------------
select
    indexname,
    tablename,
    indexdef
from pg_indexes
where schemaname = 'public'
  and tablename  in ('tasks', 'oauth_connections')
  and indexname  in ('tasks_user_id_idx', 'oauth_connections_user_id_idx');

-- -- AC6: Check constraints exist ----------------------------------------------
select
    tc.table_name,
    tc.constraint_name,
    cc.check_clause
from information_schema.table_constraints tc
join information_schema.check_constraints cc
    on tc.constraint_name = cc.constraint_name
where tc.table_schema = 'public'
  and tc.table_name   in ('tasks', 'oauth_connections')
  and tc.constraint_type = 'CHECK'
order by tc.table_name, tc.constraint_name;

-- -- AC5 (duplicate UNIQUE constraint): UNIQUE on (user_id, provider) ---------
select
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name
from information_schema.table_constraints tc
join information_schema.key_column_usage kcu
    on tc.constraint_name = kcu.constraint_name
where tc.table_schema   = 'public'
  and tc.table_name     = 'oauth_connections'
  and tc.constraint_type = 'UNIQUE'
order by kcu.ordinal_position;

-- -- Policy count summary (quick sanity check) ---------------------------------
select
    tablename,
    count(*) as policy_count
from pg_policies
where schemaname = 'public'
  and tablename  in ('profiles', 'tasks', 'oauth_connections')
group by tablename
order by tablename;