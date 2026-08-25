# Database Migrations

All migrations live here as `.sql` files, named `YYYYMMDDHHMMSS_description.sql`.

## Files (in execution order)

| # | File | Purpose |
|---|------|---------|
| 1 | `20260825000001_enable_pgcrypto.sql` | Enable `pgcrypto` extension (`gen_random_uuid()`) |
| 2 | `20260825000002_create_profiles.sql` | `profiles` table + 4 RLS policies |
| 3 | `20260825000003_create_tasks.sql` | `tasks` table + index + 4 RLS policies |
| 4 | `20260825000004_create_oauth_connections.sql` | `oauth_connections` table + index + 3 RLS policies (no insert) |

## How to apply

### Option A — Supabase SQL Editor (quickest, no CLI needed)
1. Open https://supabase.com/dashboard ? your project.
2. Go to **SQL Editor** ? **New query**.
3. Paste each file''s content **in order** (00001 ? 00002 ? 00003 ? 00004) and click **Run**.

### Option B — Supabase CLI (`db push`)
```bash
# From repo root
supabase login
supabase link --project-ref wjagpgnwhayvnugzbxns
supabase db push
```

### Option C — psql (direct connection)
```bash
# Obtain the connection string from Supabase Dashboard ? Settings ? Database
PGURI="postgresql://postgres.[ref]:[password]@[host]:6543/postgres"

psql "$PGURI" -f migrations/20260825000001_enable_pgcrypto.sql
psql "$PGURI" -f migrations/20260825000002_create_profiles.sql
psql "$PGURI" -f migrations/20260825000003_create_tasks.sql
psql "$PGURI" -f migrations/20260825000004_create_oauth_connections.sql
```

## Verify

After applying, run `verify_schema.sql` in the Supabase SQL Editor.  
Expected results:
- **RLS enabled:** `rls_enabled = true` for all 3 tables  
- **Policy counts:** `profiles=4`, `tasks=4`, `oauth_connections=3`  
- **Indexes present:** `tasks_user_id_idx`, `oauth_connections_user_id_idx`

## Notes
- All files are **idempotent** — safe to re-run against a project that already has them applied.
- `access_token` / `refresh_token` in `oauth_connections` are **plaintext placeholders** — Vault encryption is a D8 task.
- `oauth_connections` has **no insert policy** for authenticated role — INSERT is service-role only (OAuth callback server).
