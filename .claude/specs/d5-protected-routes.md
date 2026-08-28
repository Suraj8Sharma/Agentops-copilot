# AgentOps Copilot — Task Spec

**Day:** D5 · Fri 28 Aug 2026 (+ pulled-forward Google sign-in item)
**Owner:** Suraj
**Tasks (from Section 14, Day-by-Day Plan, plus one pulled forward from later scope):**
1. JWT middleware (verify/refresh) + protected routes
2. Draft RLS policies
3. "Continue with Google" login (Supabase Auth Google provider)

**Depends on:** D4 (auth design documented, signup/login endpoints built) — complete. `auth.users` → `profiles` creation trigger — **already implemented, do not rebuild.**
**Blocks:** D6 (CI running pytest on every PR; Week-1 PR merge — repo + auth skeleton frozen)

---

## 1. Objective

Lock down the backend so every route except the public auth endpoints requires a valid session, start enforcing row-level data isolation at the database level, and add Google as a second login method — all before tomorrow's Week-1 freeze.

## 2. Scope

| In scope | Out of scope |
| :-- | :-- |
| JWT verification dependency | `profiles` auto-creation trigger — **already done, do not touch** |
| Applying auth to all non-public routes | Google Calendar/Gmail OAuth (that's D7 — a separate, unrelated Google OAuth app for MCP tool permissions) |
| Draft RLS policies on `profiles`, `tasks`, `oauth_connections` | Full RLS across all 17 tables (later, as tables are added) |
| Supabase Auth Google provider config + Sign In button wiring | Password reset endpoint |
| Test suite updates for all of the above | — |

## 3. Files to Create / Modify

| File | Purpose |
| :-- | :-- |
| `backend/app/core/security.py` | JWT verification/refresh dependency (`get_current_user`), checked against Supabase JWKS |
| `backend/app/main.py` | Apply the dependency globally to all routers except `/health`, `/auth/signup`, `/auth/login` |
| `backend/migrations/xxxx_draft_rls_policies.sql` | Draft RLS policies for `profiles`, `tasks`, `oauth_connections` |
| `backend/app/core/config.py` | Add Google OAuth client ID/secret env vars if not already present |
| `backend/app/api/auth.py` | Add a route or redirect handler for Google sign-in if a custom entry point is needed beyond Supabase's hosted flow |
| `backend/app/tests/test_jwt.py` | **New/updated** — JWT middleware test cases |
| `backend/app/tests/test_oauth.py` | **New/updated** — Google sign-in test cases |
| `backend/app/tests/test_rls_security.py` | **New/updated** — draft RLS isolation test cases |

## 4. Task Details

### 4.1 JWT Middleware — verify/refresh + protected routes

- Build a FastAPI dependency that validates the JWT in the `Authorization` header against Supabase's JWKS endpoint.
- Apply it to every route except `/health`, `/auth/signup`, `/auth/login` (and the Google sign-in entry point from 4.3, since a token doesn't exist yet at that point either).
- Distinguish clearly between:
  - **Invalid/tampered token** → reject with `401`
  - **Expired access token** → reject with `401` but with a response the client can recognize as "refresh and retry," not a hard failure
- No plaintext token values in logs at any point.

### 4.2 Draft RLS Policies

- Enable RLS on `profiles`, `tasks`, `oauth_connections` (the tables live so far).
- Standard pattern per the manual:
  ```sql
  alter table <table_name> enable row level security;

  create policy "<table_name>_owner_select" on <table_name>
    for select using (user_id = auth.uid());

  create policy "<table_name>_owner_write" on <table_name>
    for insert, update, delete using (user_id = auth.uid());
  ```
- These are drafts — full coverage across all 17 tables comes as each table is added in later days. Today's goal is that the tables already in use are not wide open.

### 4.3 "Continue with Google" Login

- Enable Google as an OAuth provider in the Supabase Auth dashboard (Google Cloud OAuth client ID/secret registered, redirect URI set to Supabase's callback).
- This is primarily configuration, not custom backend logic — Supabase handles the OAuth exchange and issues the same JWT session shape as email/password login.
- **Do not** request Calendar/Gmail scopes as part of this flow — identity only. Calendar/Gmail permissions stay scoped to D7's separate OAuth Connections flow, per the auth design decision already documented.
- The `profiles` row for a Google-signed-in user is handled by the trigger you've already implemented — no additional insert logic needed here.
- Confirm end-to-end: a brand-new user signing in with Google gets a valid session AND a `profiles` row, with zero manual steps.

## 5. Definition of Done

- [ ] Code merged to `main` via a reviewed PR
- [ ] Every route except `/health`, `/auth/signup`, `/auth/login`, and the Google sign-in entry point rejects requests with no/invalid/expired token
- [ ] Draft RLS policies live on `profiles`, `tasks`, `oauth_connections`; a manual cross-user query confirms isolation
- [ ] Google sign-in works end-to-end locally: new user → session issued → `profiles` row exists (via the existing trigger, unmodified)
- [ ] **Test suite updated and passing** — see Section 6, required for CI/CD to stay green
- [ ] No secrets or tokens logged in plaintext
- [ ] One paragraph of docs written same day

## 6. Required Test Suite Updates (CI/CD Gate)

CI blocks merge on any failing test (Acceptance Criterion A9). None of today's three tasks are "done" until these pass in the pipeline, not just locally.

**`backend/app/tests/test_jwt.py`** — add/update:
| Test name | What it checks |
| :-- | :-- |
| `test_jwt_valid_token_accepted` | Valid token on a protected route → `200` |
| `test_jwt_expired_token_rejected` | Expired token → `401`, distinguishable as "needs refresh" |
| `test_jwt_tampered_signature_rejected` | Tampered/invalid token → `401` |
| `test_jwt_refresh_issues_new_access_token` | Refresh flow issues a valid new access token |

**`backend/app/tests/test_oauth.py`** — add/update:
| Test name | What it checks |
| :-- | :-- |
| `test_google_signin_new_user_creates_session` | First-time Google sign-in returns a valid JWT session |
| `test_google_signin_creates_profile_row` | Confirms the existing trigger fires correctly for a Google-signed-in user (verifies the trigger, does not reimplement it) |
| `test_google_signin_no_calendar_gmail_scopes_requested` | Confirms the consent request is identity-only, not bundled with MCP scopes |

**`backend/app/tests/test_rls_security.py`** — add/update:
| Test name | What it checks |
| :-- | :-- |
| `test_rls_user_cannot_read_other_users_tasks` | Cross-user isolation on `tasks` |
| `test_rls_user_cannot_read_other_users_oauth_tokens` | Cross-user isolation on `oauth_connections` |
| `test_rls_user_cannot_read_other_users_profile` | Cross-user isolation on `profiles` |

**CI pipeline requirements:**
- Confirm all three test files are discovered by the existing `pytest` step in `.github/workflows/ci.yml` — check the test path glob isn't excluding new files.
- Tests run against a Supabase test project or mocked client — never production data.
- All tests above must pass locally before opening the PR, and stay green in the CI run on the PR itself. A red pipeline blocks tomorrow's D6 Week-1 merge.

## 7. Acceptance Check

```bash
# Protected route without token
curl http://localhost:8000/tasks
# Expect: 401

# Protected route with valid token
curl http://localhost:8000/tasks -H "Authorization: Bearer <valid_token>"
# Expect: 200

# RLS check (as two different users, confirm no cross-visibility)
# — run via Supabase SQL editor or test suite, not curl

# Google sign-in — manual check via Supabase-hosted flow
# Expect: new user gets session + profiles row with zero manual steps

# Test suite
pytest backend/app/tests/test_jwt.py backend/app/tests/test_oauth.py backend/app/tests/test_rls_security.py -v
# Expect: all tests pass
```