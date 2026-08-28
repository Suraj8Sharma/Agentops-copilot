# Auth Design Decision — D4 (27 Aug 2026)

**Author:** Suraj
**Status:** Decided — documented before endpoint build

## 1. Identity & Session Authentication

Supabase Auth handles user identity and issues a short-lived JWT access token (~1 hour) plus a refresh token on sign-up or sign-in. The Flutter app stores both in secure storage and silently refreshes the access token before it expires. Every FastAPI route except `/health` and the auth endpoints sits behind a JWT-verification dependency that checks the token against Supabase's JWKS.

**Login methods supported:**
- Email + password (standard signup/login)
- "Continue with Google" — using Supabase Auth's built-in Google OAuth provider, for **identity only**. No Calendar or Gmail scopes are requested at this step. This just proves who the user is and creates/accesses their AgentOps account.

## 2. Third-Party OAuth for MCP Tooling

Calendar, Gmail, GitHub, and Slack are each a **separate** OAuth app with their own token pair, requested only when the user actively connects that integration from the OAuth Connections screen — not bundled into login. Tokens are stored encrypted in `oauth_connections` and refreshed independently of the user's app session.

## 3. Why These Are Kept Separate

A login token proves **who the user is**. An MCP OAuth token proves **what AgentOps is allowed to do on their behalf**. Keeping these decoupled means:

- Revoking Calendar access never breaks the user's ability to log in.
- Logging in with Google never silently grants Calendar/Gmail permissions the user didn't explicitly ask for.
- This aligns with the system's existing "fail-closed" principle (Section 4.2) — a valid session token is necessary but never sufficient for a high-risk action; MCP scopes are opt-in per integration, on their own screen, with their own consent.

## 4. Practical Impact on Today's Build

- `POST /auth/signup` and `POST /auth/login` support email/password directly via Supabase Auth.
- Google sign-in reuses Supabase Auth's Google provider — no separate backend route needed for it beyond what Supabase already handles.
- The OAuth Connections screen (Ishani, already scoped in Section 6) remains the single place where Calendar/Gmail/GitHub/Slack permissions are requested — unchanged from the original plan.