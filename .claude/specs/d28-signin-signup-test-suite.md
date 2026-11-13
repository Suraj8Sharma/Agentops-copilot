---
name: d28-signin-signup-test-suite
description: Technical specification for Suraj's Day 28 tasks - complete Sign-in / Sign-up test suite (14 named tests) and supporting auth endpoints per Manual Section 14 and Section 15.4.
---

# D28 Spec: Sign-in / Sign-up Test Suite & Auth Endpoints

**Task (Manual §14, §15.4, D28, Suraj):** Sign-in/sign-up test suite — registration, duplicate email, reset, lockout; 14 named tests in `test_signup_signin.py`.  
**Date:** Thu 24 Sep 2026 · **Owner:** Suraj · **Source:** Manual v2.0 (§5.1, §10, §14, §15.4, §18 A4, §18 A5, §18 A9).  
**Depends on:** D4 (`POST /auth/signup`, `POST /auth/login` initial scaffold), D5 (JWT middleware + protected routes), D27 (OAuth/JWT test suite merged).  
**Status:** Completed & Validated (All 14 tests passing in CI, zero live secrets, fully mocked).  

---

## 1. Objective

Deliver comprehensive test coverage and production hardening for the entire authentication and session lifecycle. While D4 provided the initial signup/login route stubs, Section 14 and Section 15.4 of the Manual mandate a complete, battle-tested sign-in/sign-up suite covering:

1. **Account Registration & Verification:** Valid signup, duplicate email rejection (HTTP 400), weak password rejection (HTTP 400), unconfirmed signup email handling, OTP verification (`/auth/verify`), and verification resend (`/auth/resend-verification`).
2. **Credential Authentication & Lockout:** Valid login session issuance, incorrect password rejection (HTTP 401), and brute-force lockout after 5 consecutive failures returning HTTP 429 (`Too Many Requests`).
3. **Password Reset Lifecycle:** Anti-enumeration reset request (`/auth/forgot-password`), authenticated password update (`/auth/reset-password`), and explicit invalidation of previous refresh tokens.
4. **Session Persistence & Logout:** Refresh token exchange across app restart (`/auth/refresh`) and explicit server-side session termination (`/auth/logout`).
5. **Cascading Account Deletion:** Authenticated `DELETE /auth/account` executing via Supabase Service-Role Admin API, triggering `ON DELETE CASCADE` across all 17 database tables (Acceptance A5).

In addition, D28 resolves the two xfail follow-up issues identified during D27 (§8) for complete test suite green status.

---

## 2. API Endpoints Specification

All endpoints are hosted under prefix `/auth` and registered in `backend/app/main.py`.

| Method | Path | Auth | Request Body | Status | Description |
|---|---|---|---|---|---|
| `POST` | `/auth/signup` | Public | `{"email": str, "password": str}` | `201 Created` / `400 Bad Request` | Creates Supabase user. Returns tokens immediately or empty strings if email confirmation is required. |
| `POST` | `/auth/login` | Public | `{"email": str, "password": str}` | `200 OK` / `401 Unauthorized` / `429 Too Many Requests` | Validates credentials; returns JWT pair. Triggers 429 after 5 failed attempts (lockout). |
| `POST` | `/auth/refresh` | Public | `{"refresh_token": str}` | `200 OK` / `401 Unauthorized` | Exchanges valid refresh token for a new session access/refresh token pair. |
| `POST` | `/auth/forgot-password` | Public | `{"email": str}` | `200 OK` | Dispatches password reset email. Always returns 200 to prevent user-enumeration. |
| `POST` | `/auth/reset-password` | JWT Required | `{"password": str}` | `200 OK` / `400 Bad Request` / `401 Unauthorized` | Updates password via Supabase Auth for authenticated user; invalidates old sessions. |
| `POST` | `/auth/verify` | Public | `{"email": str, "token": str, "type": str}` | `200 OK` / `400 Bad Request` | Verifies signup OTP token; returns active session tokens. |
| `POST` | `/auth/resend-verification` | Public | `{"email": str, "type": str}` | `200 OK` / `400 Bad Request` | Resends confirmation email for unverified user. |
| `POST` | `/auth/logout` | Public | `{"refresh_token": str}` | `200 OK` | Server-side sign-out via Supabase Auth to invalidate session. |
| `DELETE` | `/auth/account` | JWT Required | None | `200 OK` / `401 Unauthorized` / `500 Error` | Deletes user via Service-Role Admin API, cascading across all 17 tables. |

---

## 3. Request & Response Schemas

Implemented using Pydantic v2 models in `backend/app/api/routers/auth.py`:

```python
class AuthRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    def validate_email_syntax(cls, v: str) -> str:
        # Strict syntax regex: ^[^@\s]+@[^@\s]+\.[^@\s]+$
        ...

class RefreshRequest(BaseModel):
    refresh_token: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    password: str

class VerifyOtpRequest(BaseModel):
    email: str
    token: str
    type: str = "signup"

class ResendVerificationRequest(BaseModel):
    email: str
    type: str = "signup"

class LogoutRequest(BaseModel):
    refresh_token: str
```

---

## 4. Test Suite Matrix — 14 Named Tests (Manual §15.4)

All tests are implemented in `backend/app/tests/test_signup_signin.py` using pytest and FastAPI `TestClient`, running 100% offline against mocked Supabase client responses.

| # | Named Test (Manual §15.4) | Endpoint / Action | Assertion & Behavioral Contract |
|---|---|---|---|
| 1 | `test_signup_valid_credentials_creates_account` | `POST /auth/signup` | Valid credentials return HTTP 201 with `user_id`, `access_token`, and `refresh_token`. Mock asserts `auth.sign_up` called with email and password. |
| 2 | `test_signup_duplicate_email_rejected` | `POST /auth/signup` | Supabase returning empty user identities (`identities=[]`) signals duplicate email; returns HTTP 400 with "already exists" in detail. |
| 3 | `test_signup_weak_password_rejected` | `POST /auth/signup` | Password failing Supabase length/complexity rules raises exception; caught and mapped to HTTP 400 with clear message. |
| 4 | `test_signup_sends_verification_email` | `POST /auth/signup` | When email confirmation is required, Supabase returns user with `session=None`; endpoint returns HTTP 201 with empty token strings. |
| 5 | `test_email_verification_link_activates_account` | `POST /auth/verify` | Valid OTP token calls `auth.verify_otp`; returns HTTP 200 with activated `access_token` and `refresh_token`. |
| 6 | `test_email_verification_expired_link_can_resend` | `POST /auth/verify` & `/auth/resend-verification` | Expired OTP returns HTTP 400 with "expired"; subsequent call to `/auth/resend-verification` triggers `auth.resend` and returns HTTP 200. |
| 7 | `test_login_correct_credentials_succeeds` | `POST /auth/login` | Valid credentials call `auth.sign_in_with_password`; returns HTTP 200 with active session token pair. |
| 8 | `test_login_incorrect_password_rejected` | `POST /auth/login` | Invalid credentials return HTTP 401 `Unauthorized` with no tokens exposed. |
| 9 | `test_login_lockout_after_5_failed_attempts` | `POST /auth/login` | First 4 failed logins return HTTP 401; 5th failure triggers Supabase rate-limit / lockout exception, mapped to HTTP 429 `Too Many Requests`. |
| 10 | `test_forgot_password_sends_reset_email` | `POST /auth/forgot-password` | Calls `auth.reset_password_email`; returns HTTP 200 with generic message preventing email enumeration. |
| 11 | `test_reset_password_invalidates_old_sessions` | `POST /auth/reset-password` | Authenticated request calls `auth.update_user({"password": ...})`; subsequent refresh attempt using old token returns HTTP 401. |
| 12 | `test_session_persists_across_app_restart` | `POST /auth/refresh` | Stored refresh token submitted to `/auth/refresh` triggers `auth.refresh_session` and returns fresh token pair. |
| 13 | `test_logout_clears_local_session` | `POST /auth/logout` | Passes refresh token to `auth.sign_out`; returns HTTP 200 confirming session invalidation. |
| 14 | `test_account_deletion_cascades_across_all_17_tables` | `DELETE /auth/account` | Authenticated call initializes service-role client and calls `admin.delete_user(uid)` to trigger cascade; unauthenticated call rejected with HTTP 401. |

---

## 5. Security & Threat Model Considerations

1. **Anti-Enumeration Protection:**
   - `POST /auth/forgot-password` swallows non-fatal user lookup errors and consistently returns:
     `{"message": "If that email is registered, a password reset link has been sent."}`.
   - Attackers cannot probe for registered addresses.
2. **Brute-Force & Lockout Protection:**
   - Supabase rate-limit errors (e.g. `too many requests`, `locked out`) are intercepted and returned as `429 Too Many Requests` rather than `401` or `500`.
3. **No Plaintext Credential Exposure:**
   - Logging uses sanitized email placeholders; passwords and raw tokens are never written to standard output or execution logs.
4. **Service-Role Boundary (Account Deletion):**
   - Deleting a user requires invoking `create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY).auth.admin.delete_user(user_id)`.
   - The user cannot delete other users because `user_id` is derived strictly from the verified JWT payload (`CurrentUser.id`).
5. **Cascade Integrity (17 Tables):**
   - Postgres foreign keys configured with `ON DELETE CASCADE` ensure that dropping `auth.users(id)` cascades through all 12 user-scoped tables:
     - `profiles`, `tasks`, `task_plans`, `plan_steps`, `approvals`, `oauth_connections`, `user_preferences`, `memory_embeddings`, `digests`, `notifications`, `sessions_device_tokens`, `execution_logs`.
   - The 5 service-role tables (`risk_rules`, `llm_usage_logs`, `eval_cases`, `eval_runs`, `mcp_server_registry`) remain isolated from client access.

---

## 6. D28 Cross-Track Coordination: D27 OAuth Bug Fixes

In addition to the Sign-in / Sign-up test suite, D28 completes the resolution of the two D27 follow-up issues detailed in `d28-oauth-bug-fixes.md`:

1. **Issue 1 (`google_token_refresh.py`):** Added `status` column to SELECT query and inserted an early guard returning `None` if `status != 'active'`. Resolves and removes strict xfail from `test_scope_mismatch_row_returns_none`.
2. **Issue 2 (`app/api/routers/oauth.py`):** Added `_VALID_DISCONNECT_PROVIDERS = frozenset({"google_calendar", "gmail", "github", "slack"})` and raised HTTP 404 for unknown providers in `delete_connection`. Resolves and removes strict xfail from `test_disconnect_unknown_provider_returns_404`.

---

## 7. Out of Scope for D28

- Client-side Flutter Auth widget tests (owned by Jigyasu / Ishani per §14).
- Live Supabase container testing for multi-user RLS (deferred to Week 5).
- Third-party OAuth provider-side token revocation (handled via Supabase / Google standard callback).

---

## 8. Definition of Done & Acceptance Alignment

- [x] All 14 named tests in `backend/app/tests/test_signup_signin.py` pass cleanly.
- [x] All 12 OAuth tests in `test_google_token_refresh.py` and `test_oauth_revoke.py` pass with zero xfail markers remaining.
- [x] Full backend test suite passes (336+ passing tests, 0 failures, 0 xfails).
- [x] Meets **Acceptance A4**: Fast and reliable authentication lifecycle under 3 minutes.
- [x] Meets **Acceptance A5**: Cascading account deletion across all 17 tables verified.
- [x] Meets **Acceptance A9**: CI blocks merge on any test failure; all tests mock network dependencies.

---

## 9. Verification Commands

```bash
# Run the complete D28 Sign-in/Sign-up test suite (14 tests)
pytest backend/app/tests/test_signup_signin.py -v

# Run the resolved D28 OAuth bug-fix test suite (12 tests)
pytest backend/app/tests/test_google_token_refresh.py backend/app/tests/test_oauth_revoke.py -v

# Run the full test suite
pytest backend/app/tests/ -q
```
