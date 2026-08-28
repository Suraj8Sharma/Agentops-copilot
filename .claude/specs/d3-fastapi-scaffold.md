# AgentOps Copilot — Task Spec

**Day:** D3 · Wed 26 Aug 2026
**Owner:** Suraj
**Task (from Section 14, Day-by-Day Plan):** FastAPI scaffold — config/env, health-check, Supabase connection
**Depends on:** D2 (Supabase project + schema v1 + migrations) — assumed complete
**Blocks:** D4 (Auth design + signup/login endpoints)

---

## 1. Objective

Stand up the FastAPI backend skeleton that every later route, MCP client, and the LangGraph planner will be built on top of. By end of day the server must run locally, expose a working `/health` route, and successfully connect to Supabase.

## 2. Scope

| In scope | Out of scope (later days) |
| :-- | :-- |
| Env/config loader | Auth endpoints (D4) |
| `GET /health` route | JWT middleware (D5) |
| Supabase client wiring | MCP clients (D14+) |
| Base FastAPI app structure | LangGraph planner (D13) |

## 3. Files to Create

| File | Purpose |
| :-- | :-- |
| `backend/app/main.py` | FastAPI entrypoint — creates the app instance, registers routers, exposes `/health` |
| `backend/app/core/config.py` | Loads and validates environment variables into a typed settings object |
| `backend/app/core/__init__.py` | Package init |
| `backend/app/db/supabase_client.py` | Initializes and exposes the Supabase client instance |
| `backend/.env.example` | Documents every required environment variable (no real values) |
| `backend/requirements.txt` | Python dependencies for this scaffold |

## 4. Environment Variables (`.env.example`)

| Field | Required today? | Notes |
| :-- | :-- | :-- |
| `SUPABASE_URL` | Yes | Project URL from Supabase dashboard |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service-role key, used server-side only — never exposed to the client |
| `SUPABASE_JWT_SECRET` | No (needed D5) | Placeholder only today |
| `GROQ_API_KEY` | No (needed D18) | Placeholder only today |
| `GEMINI_API_KEY` | No (needed D18) | Placeholder only today |
| `GOOGLE_OAUTH_CLIENT_ID` | No (needed D7) | Placeholder only today |
| `GOOGLE_OAUTH_CLIENT_SECRET` | No (needed D7) | Placeholder only today |
| `GITHUB_OAUTH_CLIENT_ID` | No (needed D10) | Placeholder only today |
| `GITHUB_OAUTH_CLIENT_SECRET` | No (needed D10) | Placeholder only today |
| `SLACK_CLIENT_ID` | No (needed D10) | Placeholder only today |
| `SLACK_CLIENT_SECRET` | No (needed D10) | Placeholder only today |
| `FCM_SERVER_KEY` | No (needed D24) | Placeholder only today |
| `RENDER_DEPLOY_HOOK_URL` | No (needed D34) | Placeholder only today |

> Only `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` need real values today. Everything else should exist as an empty key in `.env.example` so the file is the single source of truth for what the project will eventually need.

## 5. Endpoint Spec

| Method | Path | Auth | Purpose | Response |
| :-- | :-- | :-- | :-- | :-- |
| GET | `/health` | Public | Liveness check for Render + CI | `200 {"status": "ok"}` |

## 6. Config Loader Requirements (`config.py`)

- Reads environment variables via `pydantic-settings` (or `python-dotenv` + a simple settings class — either is acceptable).
- Fails fast with a clear error message if `SUPABASE_URL` or `SUPABASE_SERVICE_ROLE_KEY` is missing at startup.
- Exposes a single `settings` object importable elsewhere in the app (`from app.core.config import settings`).
- Never logs or prints secret values.

## 7. Supabase Connection Requirements

- Use the official `supabase-py` client.
- Initialize once in `db/supabase_client.py` and export a single shared client instance — don't re-instantiate per request.
- Add a lightweight startup check: on app boot, confirm the client can reach Supabase (e.g. a trivial query or the client's own health check) and log success/failure clearly.

## 8. Definition of Done (per Section 16.3 of the manual)

- [ ] Code merged to `main` via a reviewed PR — not just "works on my machine"
- [ ] `GET /health` returns `200 {"status": "ok"}` when run locally (`uvicorn app.main:app --reload`)
- [ ] Supabase connection confirmed working at startup, no errors
- [ ] `.env.example` present and lists every variable from Section 20 Appendix A
- [ ] No secrets committed — `.env` itself is git-ignored
- [ ] One paragraph of docs written same day (README or module docstring) explaining the config/connection setup

## 9. Acceptance Check

Run locally:
```bash
uvicorn app.main:app --reload
curl http://localhost:8000/health
# Expect: {"status": "ok"}
```
Server should start with no missing-env errors and no Supabase connection errors in the logs.