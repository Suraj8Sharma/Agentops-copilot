# Schema v1 Migrations — Technical Specification

**Project:** AgentOps Copilot
**Scope:** Day 2 (D2) — Supabase project + schema v1 + migrations
**Owner:** Suraj
**Source of truth:** AgentOps Implementation Manual v2.0, Section 7 (Groups A/B), Section 7.1 (RLS pattern), Section 7.2 (indexing), Appendix A (env vars)
**Target location:** `backend/migrations/`, one `.sql` file per logical change, named `YYYYMMDDHHMMSS_description.sql`

This document is the spec to implement against. Generate the migration files described below from scratch, matching every requirement in Sections 2 through 6 exactly. Where anything here is ambiguous or conflicts with the project brief, the project brief's Section 7 (schema) and Section 7.1 (RLS pattern) is the fallback authority — but note Section 4 of this spec already documents one specific correction to the brief's RLS shorthand (it isn't valid SQL as written); implement the corrected version here, not the literal text in the brief.

---

## 1. Problem Statement

The backend has no persistent storage yet. Before any other D2/D3 work can start (FastAPI scaffold connecting to a real DB, JWT middleware, OAuth callback), three foundational tables must exist in Supabase Postgres with correct constraints and correct row-level security: `profiles` (identity), `tasks` (the root of every user request), and `oauth_connections` (third-party token storage). Every later table in the schema (Sections 7 Groups B–F) foreign-keys into `profiles` or `tasks`, so an error here — a missing constraint, a wrong cascade rule, a broken RLS policy — propagates into every table built on top of it for the rest of the 41-day build. This is why it's D2, before any application code exists.

## 2. Functional Requirements

### 2.1 Extensions
- `pgcrypto` must be enabled (idempotently — `create extension if not exists`) to provide `gen_random_uuid()` for every UUID primary key in this and future migrations.

### 2.2 Table: `profiles`
One row per Supabase Auth user, created on first sign-in (D4 wires the actual insert).

| Column | Type | Constraint |
|---|---|---|
| user_id | uuid | PK, FK → `auth.users(id)` ON DELETE CASCADE |
| display_name | text | nullable |
| email | text | NOT NULL |
| avatar_url | text | nullable |
| onboarding_completed | boolean | NOT NULL, DEFAULT false |
| created_at | timestamptz | NOT NULL, DEFAULT now() |

### 2.3 Table: `tasks`
One row per user-submitted request (text or voice).

| Column | Type | Constraint |
|---|---|---|
| id | uuid | PK, DEFAULT gen_random_uuid() |
| user_id | uuid | NOT NULL, FK → `profiles(user_id)` ON DELETE CASCADE |
| input_type | text | NOT NULL, CHECK IN ('text','voice') |
| raw_input | text | nullable |
| transcription_text | text | nullable |
| status | text | NOT NULL, DEFAULT 'submitted', CHECK IN ('submitted','planning','awaiting_approval','executing','completed','failed','cancelled') |
| created_at | timestamptz | NOT NULL, DEFAULT now() |
| completed_at | timestamptz | nullable |

### 2.4 Table: `oauth_connections`
One row per (user, provider). Real tokens don't land until D8 — this table only needs to exist and be correctly locked down today.

| Column | Type | Constraint |
|---|---|---|
| id | uuid | PK, DEFAULT gen_random_uuid() |
| user_id | uuid | NOT NULL, FK → `profiles(user_id)` ON DELETE CASCADE |
| provider | text | NOT NULL, CHECK IN ('google_calendar','gmail','github','slack') |
| access_token | text | nullable (plaintext placeholder pre-D8; must migrate to Vault encryption before real tokens are written) |
| refresh_token | text | nullable (GitHub classic tokens may not rotate) |
| scopes | text[] | nullable |
| expires_at | timestamptz | nullable |
| status | text | NOT NULL, DEFAULT 'active', CHECK IN ('active','expired','revoked','scope_mismatch') |
| connected_at | timestamptz | NOT NULL, DEFAULT now() |
| — | — | UNIQUE (user_id, provider) |

### 2.5 Row-Level Security (cross-cutting, applies to all three tables)

The manual's Section 7.1 shorthand — a single `_owner_write` policy covering `insert, update, delete` in one `FOR` clause — is not valid PostgreSQL syntax (`FOR` accepts exactly one of `ALL | SELECT | INSERT | UPDATE | DELETE`; a comma list is rejected at migration time). The corrected pattern, required on every user-scoped table:

- `<table>_owner_select` — `FOR SELECT USING (user_id = auth.uid())`
- `<table>_owner_insert` — `FOR INSERT WITH CHECK (user_id = auth.uid())`
- `<table>_owner_update` — `FOR UPDATE USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())`
- `<table>_owner_delete` — `FOR DELETE USING (user_id = auth.uid())`

**Exception:** `oauth_connections` must NOT have an owner_insert policy. INSERT is service-role-only (the OAuth callback), enforced by omission — no client-facing insert policy at all, since `service_role` bypasses RLS by default in Supabase.

## 3. API Contract

Supabase auto-exposes every table via PostgREST unless explicitly restricted, so the RLS policy set above **is** the API contract. Define it explicitly per role:

| Table | Role | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|---|
| profiles | authenticated (own row) | ✅ | ✅ | ✅ | ✅ |
| profiles | authenticated (other user's row) | ❌ | ❌ | ❌ | ❌ |
| profiles | anon | ❌ | ❌ | ❌ | ❌ |
| tasks | authenticated (own row) | ✅ | ✅ | ✅ | ✅ |
| tasks | authenticated (other user's row) | ❌ | ❌ | ❌ | ❌ |
| oauth_connections | authenticated (own row) | ✅ | ❌ | ✅ | ✅ |
| oauth_connections | service_role | ✅ | ✅ | ✅ | ✅ |
| any table | service_role | ✅ | ✅ | ✅ | ✅ |

Any deviation from this table (e.g., a table left publicly readable, or an insert policy accidentally added to `oauth_connections`) is a contract violation, not a minor detail.

## 4. Constraints

- Every dependency runs on Supabase's free tier (Manual Section 2.3) — no assumption of a paid-tier feature (e.g., point-in-time recovery, dedicated compute) anywhere in these migrations.
- Migrations must be idempotent — `create table if not exists`, `create index if not exists`, `create extension if not exists` — since they may be re-run against a project that already has them applied.
- No migration may be destructive (no `drop table`, no `truncate`) without a separate, explicitly reviewed down-migration — none is in scope today.
- `access_token` / `refresh_token` stay as plain `text` columns for now (encryption via Supabase Vault/pgsodium is explicitly a D8 task, not today's) — but the column comment must say so, so nobody mistakes today's schema for the encrypted-at-rest final state.
- File naming: `YYYYMMDDHHMMSS_description.sql`, one file per logical change, under `backend/migrations/` — matches the CLI link already set up.
- Every FK used in an RLS join path must be indexed (Section 7.2) — `profiles.user_id` is covered automatically (it's the PK); `tasks.user_id` and `oauth_connections.user_id` are not automatic and must be explicitly indexed.

## 5. Edge Cases & Error Handling

| Case | Required behavior |
|---|---|
| A `tasks` or `oauth_connections` insert arrives before the user's `profiles` row exists | FK violation, rejected by Postgres — this is correct; the app layer must guarantee `profiles` insert happens at signup before anything else, not the schema's job to work around it |
| Duplicate `oauth_connections` insert for the same (user, provider) | Rejected by the UNIQUE constraint — caller must UPSERT (`on conflict (user_id, provider) do update`), not blind-insert, once the OAuth callback is built |
| A user attempts to set `user_id` on insert/update to someone else's id | Blocked by the `WITH CHECK (user_id = auth.uid())` clause on insert/update policies — this is the exact mechanism, not just RLS in the abstract |
| An invalid `status` or `provider` or `input_type` value is submitted | Rejected by the CHECK constraint at the DB layer — this must hold even if application-layer validation is bypassed or buggy, since the DB is the last line of defense |
| Migrations re-run against a project that already has these objects | No error — every `create` statement is idempotent per the Constraints section |
| A client (anon or authenticated, non-service-role) attempts to INSERT into `oauth_connections` directly via the PostGREST API | Rejected — no insert policy exists for that role, so RLS default-denies |
| `profiles.user_id` row deleted from `auth.users` | Cascades to delete the `profiles` row, which cascades to `tasks` and `oauth_connections` — full cleanup, no orphaned rows, per every FK's `ON DELETE CASCADE` |

## 6. Acceptance Criteria

- [ ] All three tables (`profiles`, `tasks`, `oauth_connections`) exist with every column, type, and constraint exactly as specified in Section 2.
- [ ] RLS is enabled on all three tables (verified via Table Editor shield icon or `pg_tables`/`pg_policies` query — not assumed from the migration file alone).
- [ ] Each table has exactly the policies specified in Section 2.5 — no more, no fewer. In particular: `oauth_connections` has zero insert policies for non-service-role.
- [ ] `tasks.user_id` and `oauth_connections.user_id` are indexed.
- [ ] `oauth_connections` rejects a second insert for an existing (user_id, provider) pair.
- [ ] Inserting a `tasks` or `oauth_connections` row with a non-existent `user_id` fails with a foreign-key violation.
- [ ] Inserting an invalid `status`, `provider`, or `input_type` value fails with a check-constraint violation.
- [ ] Running the full migration set twice against the same fresh project produces no errors on the second run.
- [ ] A test authenticated as User A cannot SELECT, UPDATE, or DELETE any row belonging to User B in any of the three tables (this is the direct precursor to Acceptance Criterion A5 in the manual — zero cross-user leakage).
- [ ] Deleting a row from `auth.users` cascades correctly through `profiles → tasks` and `profiles → oauth_connections` with no orphaned rows left behind.