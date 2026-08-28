# AgentOps Copilot — Task Spec

**Day:** D4 (Backlog — completing 28 Aug) · Thu 27 Aug 2026
**Owner:** Suraj
**Task (from Section 14, Day-by-Day Plan):** Signup/login endpoints — `POST /auth/signup`, `POST /auth/login`
**Depends on:** D3 (FastAPI scaffold + Supabase connection) — complete. Auth design decision (JWT session + OAuth2 for MCP, documented) — complete.
**Blocks:** D5 (JWT middleware + protected routes), D6 (CI running pytest on every PR)

---

## 1. Objective

Build the two public auth endpoints that let a user create an account and log in, delegating identity to Supabase Auth per the documented auth design. This is the first real write path in the backend and the foundation every protected route sits on from D5 onward.

## 2. Scope

| In scope | Out of scope (later days) |
| :-- | :-- |
| `POST /auth/signup` | JWT verification middleware (D5) |
| `POST /auth/login` | Password reset endpoint (documented in Section 10, not built until needed) |
| Basic input validation | OAuth consent/callback for Google Calendar/Gmail (D7) |
| Test suite for these two routes | Full sign-in/sign-up test suite (D28, per Section 15) |

## 3. Files to Create / Modify

| File | Purpose |
| :-- | :-- |
| `backend/app/api/auth.py` | Signup and login route handlers |
| `backend/app/db/supabase_client.py` | Reuse existing client from D3 — no changes expected unless auth helper methods are needed |
| `backend/app/main.py` | Register the `auth` router |
| `backend/app/tests/test_signup_signin.py` | **New/updated** — test cases for both endpoints (see Section 6) |
| `.github/workflows/ci.yml` | **Update if needed** — confirm the new test file is picked up by the existing pytest step; do not skip or exclude it |

## 4. Endpoint Spec

| Method | Path | Auth | Request body | Response |
| :-- | :-- | :-- | :-- | :-- |
| POST | `/auth/signup` | Public | `{"email": str, "password": str}` | `201` with user id + session, or `400` on validation/duplicate-email error |
| POST | `/auth/login` | Public | `{"email": str, "password": str}` | `200` with `{"access_token": str, "refresh_token": str}`, or `401` on invalid credentials |

### Behavior notes

- Both routes delegate the actual account creation/verification to **Supabase Auth** — do not hand-roll password hashing or storage. FastAPI is a thin wrapper here.
- `signup` should return a clear `400` error (not a `500`) on duplicate email or weak password, per the existing design ("Continue with Google" is a separate flow — Supabase's Google provider — and is out of scope for this specific task; only email/password needs implementing today).
- `login` returns the JWT access + refresh token pair issued by Supabase Auth, matching the session model already documented (~1 hour access token lifetime).
- Neither route requires the JWT-verification dependency — they're explicitly public, since a token doesn't exist yet at this point in the flow.

## 5. Definition of Done (per Section 16.3 of the manual)

- [ ] Code merged to `main` via a reviewed PR — not just "works on my machine"
- [ ] `POST /auth/signup` creates a real Supabase Auth user and returns `201`
- [ ] `POST /auth/login` returns a valid JWT access + refresh token pair for correct credentials
- [ ] Duplicate email and invalid-credential cases return clean `400`/`401` errors, not `500`s
- [ ] **Test suite updated and passing** — see Section 6, this is required for the CI/CD pipeline to stay green
- [ ] No secrets or passwords logged in plaintext anywhere
- [ ] One paragraph of docs written same day (README or module docstring)

## 6. Required Test Suite Update (CI/CD Gate)

This is explicitly called out because CI blocks merge on any failing test (Acceptance Criterion A9) — the endpoints are not "done" until these pass in the pipeline, not just locally.

**Update `backend/app/tests/test_signup_signin.py`** to include, at minimum, the tests already named against this feature in Section 15.4 of the manual:

| Test name | What it checks |
| :-- | :-- |
| `test_signup_valid_credentials_creates_account` | Valid email/password → `201`, account exists in Supabase |
| `test_signup_duplicate_email_rejected` | Re-signing up with an existing email → `400`, not `500` |
| `test_signup_weak_password_rejected` | Password below Supabase's minimum policy → `400` |
| `test_login_correct_credentials_succeeds` | Valid credentials → `200` with both tokens present |
| `test_login_incorrect_password_rejected` | Wrong password → `401`, no token issued |

**CI pipeline requirements:**
- The agent should confirm `backend/app/tests/test_signup_signin.py` is actually discovered and run by the existing `pytest` step in `.github/workflows/ci.yml` — check the test path glob/pattern isn't excluding it.
- Tests must run against a Supabase **test** project or a mocked Supabase client — never against production data.
- All five tests above must pass locally (`pytest backend/app/tests/test_signup_signin.py -v`) before the PR is opened, and must stay green in the CI run on the PR itself.
- If the CI workflow doesn't yet install/cache backend test dependencies correctly, fix that as part of this task rather than leaving it as a separate follow-up — a red pipeline blocks D5 and D6 downstream.

## 7. Acceptance Check

```bash
# Local run
uvicorn app.main:app --reload

# Signup
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"SecurePass123"}'
# Expect: 201, user id present

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"SecurePass123"}'
# Expect: 200, {"access_token": "...", "refresh_token": "..."}

# Test suite
pytest backend/app/tests/test_signup_signin.py -v
# Expect: all 5 tests pass
```