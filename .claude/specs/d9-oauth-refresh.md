# OAuth Token Refresh & Expiry Handling — Technical Spec

**Project:** AgentOps Copilot
**Plan reference:** D9 — "Token-refresh job + 7-day Testing-mode expiry detection/flagging"
**Owner / track:** Suraj — backend
**Files:** `backend/app/core/oauth_refresh.py` (new), `backend/app/api/routers/oauth.py` (update)
**Status going into this spec:** D8 successfully exchanges the authorization code for an access/refresh token pair and stores them encrypted in `oauth_connections`. However, Google access tokens expire in ~1 hour. Because the app is in GCP "Testing" status, the refresh tokens themselves will hard-expire 7 days after issuance.

---

## 1. Objective

1. **Token Refresh (Supabase JWT):** Make sure the user's Supabase login session (JWT) refreshes smoothly and automatically in the background so they never get logged out mid-task without warning.
2. **7-Day Expiry Detection (Google OAuth):** Keep track of when each user connected their Google account and flag it before the 7-day Testing-mode mark hits. This gives the user a heads-up ("please reconnect your Google account") instead of letting the connection silently break mid-task.

## 2. Scope

| In scope | Out of scope |
| :-- | :-- |
| Background mechanism/job to automatically renew Supabase login sessions | GitHub / Slack OAuth logic (D10) |
| Backend detector to find Google OAuth connections nearing 7 days old and flag them | |
| Graceful warnings to the user to reconnect Google before it breaks | |

## 3. Implementation Details

### 3.1 Supabase JWT Background Refresh
**Files:** Flutter Client / `backend/app/api/routers/auth.py`
- The backend already has a `POST /auth/refresh` endpoint (built in D5) to exchange an expired access token for a new one using the refresh token.
- **The Job:** Ensure that instead of waiting for a 401 error, the client (Flutter) or a background worker proactively tracks the Supabase JWT expiry time (e.g., refreshing 5 minutes before the 1-hour mark). 
- This guarantees the user's login session is renewed automatically in the background and they never get interrupted or logged out mid-task.

### 3.2 Google 7-Day Testing-Mode Expiry Detector
**File:** `backend/app/api/routers/oauth.py` (or a dedicated cron/task module)
Add a new internal sweep mechanism: `POST /oauth/internal/sweep-tokens`
- **Auth:** Secured by a static backend secret (e.g., `CRON_SECRET`) so an external scheduler can call it safely.
- **Behavior:** 
  - Query all `google_calendar` and `gmail` connections where `status = 'active'`.
  - Calculate `token_age = now() - connected_at`.
  - If `token_age` > 6 days and 12 hours (approaching the 7-day Google testing limit):
    - Update `status` to `expired_testing_mode` (or similar).
    - *Outcome:* The system flags this before the 7-day mark hits. The app will detect this status and prompt the user with a graceful "please reconnect your Google account" heads-up, preventing silent breakage mid-task.
  
## 4. Config / Env

Needed for the sweep endpoint:
- `SUPABASE_SERVICE_ROLE_KEY` — to bypass RLS for updating `oauth_connections`.
- `CRON_SECRET` — to secure the backend sweep endpoint.

## 5. Security notes

- **Service Role:** As in D8, updating OAuth tokens or statuses in bulk requires the service role key. Do not use it for general querying.

## 6. Error handling

| Case | Response |
|---|---|
| Supabase JWT refresh fails | Log the user out gracefully, clear local secure storage, redirect to Login. |
| Sweep job fails to query DB | Retry on the next cron schedule; throw a 502/transient error. |

## 7. Acceptance / test criteria

- `test_jwt_background_refresh`: The client/system successfully renews the Supabase JWT before it expires, without interrupting the user.
- `test_oauth_7day_testing_mode_expiry_is_flagged`: Inserts a connection with `connected_at` set to 6.9 days ago, runs the sweep, and verifies the status changes to flag the upcoming expiry.
- `test_oauth_sweep_requires_cron_secret`: Ensures the internal sweep endpoint rejects requests missing the correct auth secret.

## 8. Dependencies

- D5 complete (JWT verify/refresh backend).
- D8 complete (Google OAuth connection records exist).
