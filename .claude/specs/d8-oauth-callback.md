# OAuth Callback Endpoint — Technical Spec

**Project:** AgentOps Copilot
**Plan reference:** D8 — "OAuth callback endpoint (exchange code for tokens, save to pg_sodium)"
**Owner / track:** Suraj — backend
**File:** `backend/app/api/oauth.py`
**Status going into this spec:** The D7 connect endpoint (`/oauth/{provider}/connect`) is built and returning valid Google authorization URLs. This spec covers the return journey: receiving the authorization code, exchanging it for tokens, and securely storing them.

---

## 1. Objective

Complete the OAuth flow by handling the callback. Since the client is a Flutter mobile app, the app will intercept the custom URL redirect from Google and manually call this backend endpoint, passing the authorization code along with the user's existing JWT. The backend will exchange this code for tokens with Google and store them securely encrypted at rest.

## 2. Endpoint

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/oauth/{provider}/callback` |
| **Auth** | JWT required (The Flutter app passes the user's auth header along with the callback parameters) |
| **Purpose** | Exchange auth code for tokens and save them |

## 3. Request

- **Path param:** `provider` — string (`google` for now).
- **Query params:** 
  - `code`: The authorization code from Google.
  - `state`: The CSRF token generated during the connect step.
  - (Optional) `scope`: The scopes Google granted (can also be verified in the token response).
  - (Optional) `error`: If the user denied consent.

## 4. Behavior

1. **Verify Authentication:** Extract the `user_id` from the JWT.
2. **Verify State:** Validate the `state` parameter matches what was generated in D7 for this user/provider. This prevents CSRF attacks where an attacker links their own Google account to the victim's session.
3. **Token Exchange:** Make a server-to-server `POST` request to Google's token endpoint (`https://oauth2.googleapis.com/token`) with:
   - `client_id`
   - `client_secret`
   - `code`
   - `redirect_uri` (must match exactly what was sent in D7)
   - `grant_type=authorization_code`
4. **Encrypt Tokens:** Encrypt the received `access_token` and `refresh_token`. 
   - *Design Choice:* App-level encryption using a symmetric key (e.g., `cryptography.Fernet`) driven by a backend secret (`ENCRYPTION_KEY`). This keeps the encryption key out of the database and is simpler to implement in FastAPI than calling Postgres RPCs for Supabase Vault.
5. **Database Insertion (Service Role):** 
   - Insert the connection records into the `oauth_connections` table.
   - **Crucial:** The RLS policy restricts `INSERT` to the backend. You must use a Supabase client instantiated with `SUPABASE_SERVICE_ROLE_KEY` to bypass the user-facing RLS policy.
6. **Data Mapping:**
   - D7 requested scopes for both Calendar and Gmail in one consent screen.
   - The schema defines `provider` as a `CHECK IN ('google_calendar','gmail',...)`.
   - **Decision:** Write **two** rows (duplicate the token pair), one with `provider='google_calendar'` and one with `provider='gmail'`. This allows per-provider disconnection later (`DELETE /oauth/gmail`) without dropping Calendar access.
   - Set `status='active'`, calculate `expires_at` from `expires_in`, and store the actual granted `scopes`.

## 5. Config / Env

Needed for this endpoint:
- `SUPABASE_SERVICE_ROLE_KEY` — to bypass RLS for inserting into `oauth_connections`.
- `ENCRYPTION_KEY` — symmetric key for encrypting tokens at rest (if using app-level encryption).
- Existing Google OAuth credentials (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`).

## 6. Security notes

- **State Validation:** Do not skip the `state` check. It is the only defense against CSRF account-linking.
- **Service Role:** Only use the `SUPABASE_SERVICE_ROLE_KEY` for this specific `INSERT` operation. Do not use it for general querying.
- **Encryption:** Tokens must never be stored in plain text. The `test_oauth_token_encrypted_at_rest` test will enforce this.

## 7. Error handling

| Case | Response |
|---|---|
| Unauthenticated (no/invalid JWT) | 401 |
| Missing or invalid `state` | 400 Bad Request |
| Google token exchange fails | 400 (or 502 Bad Gateway) with error details |
| User denied consent (`error` param present) | 400 Bad Request (or a specific redirect to the frontend) |

## 8. Out of scope for D8

- Token refresh logic (D9)
- 7-day Testing-mode expiry detector (D9)

## 9. Acceptance / test criteria

- `test_oauth_callback_exchanges_code_for_token`: Mocks the Google token endpoint and verifies the correct parameters are sent.
- `test_oauth_token_encrypted_at_rest`: Queries the database directly to ensure the raw token string is not present in the `access_token` or `refresh_token` columns.

## 10. Dependencies

- D7 connect endpoint (must pass the correct redirect URI and state).
- Supabase Python client (for service-role inserts).
