# OAuth Consent-Flow Endpoint — Technical Spec

**Project:** AgentOps Copilot
**Plan reference:** D7, Mon 31 Aug — "Google OAuth2 app registered (Calendar+Gmail scopes); consent-flow endpoint"
**Owner / track:** Suraj — backend
**File:** `backend/app/api/oauth.py`
**Status going into this spec:** Google Cloud project created; `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` loaded into config. This spec covers the remaining piece — the consent-flow endpoint itself.

---

## 1. Objective

Give the Flutter client a way to kick off Google's OAuth consent flow for a signed-in user, so they can grant Calendar + Gmail access. This endpoint only *starts* the flow — it builds and hands back the Google authorization URL. It does not exchange the code or store tokens; that's the callback endpoint (D8).

## 2. Endpoint

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/oauth/{provider}/connect` |
| **Auth** | JWT required (standard verification dependency, Section 5.1) |
| **Purpose** | Start the OAuth consent redirect for a provider |

For D7, `provider` is effectively `google` — Calendar and Gmail share one Google Cloud app and one consent screen, so a single connect call covers both scopes. `github` / `slack` come later (D10) and can reuse this same route shape.

## 3. Request

- **Path param:** `provider` — string, one of `google` (only valid value for now; others return 404 until D10).
- **No query params or body.** The user is identified from the JWT.

## 4. Behavior

1. Verify the JWT, extract `user_id`.
2. Build the Google authorization URL:
   - Base: `https://accounts.google.com/o/oauth2/v2/auth`
   - `client_id` — from config (`GOOGLE_OAUTH_CLIENT_ID`)
   - `redirect_uri` — the backend's `/oauth/google/callback` URL (add `GOOGLE_OAUTH_REDIRECT_URI` to config now, even though the callback logic itself lands on D8 — the URL needs to exist to build today's request)
   - `response_type=code`
   - `scope` — space-separated, see Section 5
   - `access_type=offline` (required to get a refresh token, not just a short-lived access token)
   - `prompt=consent` (forces the refresh token to be reissued even on repeat consent)
   - `state` — a signed, unguessable value binding `user_id` + `provider`, used as CSRF protection and to route the callback back to the right user
3. Return the URL — recommended as JSON (`{"authorization_url": "..."}`) rather than a raw 302 redirect, so the Flutter client can open it in an external browser / custom tab. A server-side redirect is awkward for a mobile client that isn't itself sitting behind a browser session.

## 5. Scopes (per Section 5.2 of the manual)

| Provider | Scope | Notes |
|---|---|---|
| Google Calendar | `calendar.events` | Read/write on events only — not full calendar admin |
| Gmail | `gmail.send`, `gmail.compose` | Read scope only if a read-type step gets added later |

Full scope string for this endpoint:
`https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.compose`

## 6. Config / Env

Already set:
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`

Needed for this endpoint:
- `GOOGLE_OAUTH_REDIRECT_URI` — backend callback URL, so the authorization request built today points somewhere valid once D8 lands

## 7. Security notes

- `state` must be unguessable and tied to the requesting user — don't skip this even though it feels premature ahead of the callback work.
- Never log `client_secret` or the built authorization URL in full (it carries `client_id` and `state`).
- The Google Cloud app will start in **Testing mode**, which caps tokens at a 7-day expiry — that's expected and is exactly what D9's expiry detector is built to flag. Nothing to solve here, just don't be surprised by it.

## 8. Error handling

| Case | Response |
|---|---|
| Unauthenticated (no/invalid JWT) | 401 — handled automatically by the JWT dependency |
| Unknown `provider` | 404 |
| Config missing (`GOOGLE_OAUTH_CLIENT_ID` unset) | 500 with a clear internal error — should never happen post-D7 setup, but fail loud, not silent |

## 9. Out of scope for D7

- `/oauth/{provider}/callback` — code exchange, encrypted token storage (**D8**)
- `DELETE /oauth/{provider}` — disconnect/revoke (later)
- GitHub / Slack provider registration (**D10**)

## 10. Acceptance / test criteria

- `test_oauth_google_consent_redirect_has_correct_scopes` — asserts the built URL's scope list matches exactly the three scopes in Section 5.
- Manual smoke test: hitting the endpoint with a valid JWT returns an authorization URL that, when opened, shows Google's consent screen requesting Calendar + Gmail permissions (and nothing broader).

## 11. Dependencies

- JWT middleware — already live (D5)
- Config loader with Google client ID/secret — already updated (today's earlier work)