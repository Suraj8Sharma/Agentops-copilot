**AGENTOPS COPILOT**

**Technical Implementation Manual**

_MCP-native multi-agent personal assistant — LangGraph orchestration, Flutter client_

**Version 2.0 — Definitive Build Manual**

Build window: Monday, 24 August 2026 — Friday, 9 October 2026

Prepared by Suraj · Team: Suraj, Ishani, Jigyasu, Sanskriti, Shivangi

7th-Semester CSE (AI & ML) Capstone Project

| **Version** | **Date**    | **Prepared by** | **Status**               | **Classification**  |
| ----------- | ----------- | --------------- | ------------------------ | ------------------- |
| 2.0         | 22 Aug 2026 | Suraj           | Final — for distribution | Internal — Team Use |

_"Plan transparently, act only with permission, and log everything so trust is never taken on faith."_

# **Contents**

- 1\. Executive Summary
- 2\. Scope, Constraints & Non-Goals
- 3\. Team Structure & Ownership
- 4\. Target Architecture & Design Principles
- 5\. Authentication & Authorization Design
- 6\. App Page Inventory
- 7\. Database Schema (Supabase PostgreSQL + pgvector)
- 8\. MCP Integration & LangGraph Orchestration
- 9\. Risk & Approval Gate
- 10\. Backend API Reference
- 11\. Folder Structure & Code Organization
- 12\. CI/CD & Deployment
- 13\. Working Rhythm & Calendar
- 14\. Day-by-Day Plan with Dependencies (41 Days)
- 15\. Testing, QA & Fallback Strategy
- 16\. Daily Diary & Weekly Report Templates
- 17\. Checklists (Phase Gates)
- 18\. Acceptance Criteria
- 19\. Risk Register & Fallbacks
- 20\. Appendices

# **1\. Executive Summary**

AgentOps Copilot is an MCP-native, multi-agent personal assistant. A user hands it a task in text or voice; a LangGraph planner breaks that task into an ordered sequence of steps; each step routes through the right Model Context Protocol (MCP) server — Calendar, Gmail, GitHub, or Slack today; and anything risky stops for a one-tap human approval before it runs. The whole loop is built to be auditable end to end: every decision the agent makes is logged, explainable, and reversible before execution — never after.

This manual is the single source of truth for the build. It replaces the early draft implementation plan and expands it to the level of detail the team needs to build, test, and ship without ambiguity: exact database columns and row-level-security policies, exact MCP workflows and LangGraph state transitions, exact folder-level file ownership, and an exact day-by-day schedule across all 41 build days.

## **1.1 Three Goals, In Priority Order**

| **Goal**                    | **What it means**                                                                                                   | **How we will measure it**                                                                                                                               |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G1 — Working agent loop     | Ship plan → risk-tag → approve → execute → log that never silently takes a risky action.                            | 100% of adversarial approval-gate bypass test runs block the action (Acceptance A2); zero unapproved high-risk executions across the whole 41-day build. |
| G2 — Legible Flutter client | A user can always see what the agent is about to do and why, before it happens.                                     | Widget-test coverage ≥80% of screens, 100% on Approval Screen & Plan View (A7); sign-up to first completed task <3 min in usability testing (A4).        |
| G3 — Ship on schedule       | Build starts Mon 24 Aug 2026; feature-complete, tested, deployed and reported on by the first week of October 2026. | All 41 working days tracked against Section 14; Gate 5 submission delivered on Fri 9 Oct 2026.                                                           |

## **1.2 Key Design Decisions**

- Hardcoded risk gate, not an LLM decision. risk_rules is a seeded, migration-controlled table. The planner and every LLM in the system are advisory only where safety is concerned — they can explain a decision, they can never make one.
- MCP as a swappable integration layer. Calendar, Gmail, GitHub and Slack are each a thin client behind the identical call/response contract (Section 8.2), so the planner never contains provider-specific logic and a fifth MCP server is a client, not a rewrite.
- Fail-closed by default. Any action with no matching risk_rules entry defaults to requires_approval = true. Silence in the rule table is never read as permission.
- Auditability by construction. execution_logs receives a row for every node transition, tool call, and approval decision before that decision has any external effect — the audit trail is not reconstructed after the fact.
- Free-tier aware, not free-tier blind. Groq/Gemini rate limits, Render cold starts, and Supabase free-tier caps are treated as first-class constraints that shape the architecture (Section 2.3), not edge cases to patch around later.
- Reversible before, not after. The system is built to make risky actions stoppable before they run; it does not rely on undoing them afterwards.

## **1.3 What "Done" Looks Like on 9 October 2026**

Demo script: a fresh test user signs up, connects Google Calendar and Gmail from the OAuth Connections screen, and types "schedule a call with my professor for Thursday afternoon and email him the agenda." The Agent Plan View shows two steps — create a calendar event (medium risk, auto-executes) and send an email (high risk, requires approval). The Approval Screen surfaces the email with a plain-English explanation of what is about to be sent and why it was flagged. The user approves; the task completes; the Activity Log shows both steps with full payloads and timing; the Trust Dashboard shows the latency, the model used, and which provider — Groq or Gemini — answered the request. Every one of the ten acceptance criteria in Section 18 is green.

# **2\. Scope, Constraints & Non-Goals**

## **2.1 In Scope**

Text + voice task input; LangGraph planning/orchestration; MCP integration with Google Calendar, Gmail, GitHub and Slack; a hardcoded (non-LLM-decided) risk/approval gate; long-term memory via pgvector; daily/weekly digests; push + in-app notifications with an LLM-written banner line; and a Trust Dashboard.

## **2.2 Explicitly Out of Scope for Now**

OCR / photo-to-task input. It stays in the page inventory (Section 6) and the risk register (Section 19) so it is not forgotten, but no one is assigned to it and no phase depends on it. Revisit only after all ten acceptance criteria in Section 18 pass.

## **2.3 Hard Constraints — Free-Tier Architecture**

Every dependency in this system runs on a free tier. This plan is built around those limits rather than around ignoring them; each row below is load-bearing, not a footnote.

| **Constraint**                     | **Detail**                                                                                                                                                                                                                                                                     | **How this plan handles it**                                                                                                                                                                                                                                                                                      |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Groq inference limits              | Groq's free/developer tier enforces per-model requests-per-minute and tokens-per-minute quotas that can be hit under concurrent load or bursty planning calls; exact published numbers should be re-checked at the start of Week 1 since provider terms change without notice. | LLM router (Section 8.4) treats Groq as primary and falls back to Gemini automatically on a 429; every call is logged to llm_usage_logs so a rate-limit hit is visible, not silent. Load test D32 specifically drives concurrent load to prove the fallback engages.                                              |
| Gemini inference limits            | Gemini's free tier caps daily/per-minute requests per model and may throttle or queue under load.                                                                                                                                                                              | Used as the documented fallback, not the default path, so its quota is preserved for exactly the moments Groq is unavailable.                                                                                                                                                                                     |
| Render free-tier cold starts       | A free Render web service spins down after a period of inactivity; the next request pays a cold-start penalty of tens of seconds, which reads as a hang to a first-time user or a demo evaluator.                                                                              | A warm-up ping job fires ahead of the Day-39 demo rehearsal and the final Day-41 submission slot (Risk Register, Section 19). The Flutter client shows an explicit loading state rather than a spinner-that-looks-broken (Acceptance A6 measures the auto-executed, warm-path case).                              |
| Supabase free-tier limits          | Free-tier Postgres projects have a storage cap, pause the project after a week of inactivity, and cap concurrent connections — all of which matter for a system writing an execution_logs row per agent step.                                                                  | Daily incremental deploys and daily team activity keep the project active by construction; execution_logs payloads are kept lean (structured JSON, not raw provider responses) to stay inside the storage budget; connection pooling is handled through Supabase's pooler rather than one connection per request. |
| Firebase Cloud Messaging free tier | FCM itself has no meaningful free-tier request cap for a project this size, but device-token churn (uninstalls, token rotation) needs explicit handling or notifications silently stop delivering.                                                                             | sessions_device_tokens tracks last_active per device; Jigyasu's push-delivery test suite (Section 15) explicitly covers stale-token handling.                                                                                                                                                                     |

## **2.4 Non-Goals**

- Not a production system for many concurrent users — free-tier rate limits are a documented, accepted constraint, not a defect to engineer away.
- Not a general "do anything" agent — deliberately scoped to four tool categories so the system stays demoable and evaluable inside one semester.
- Not removing human judgment from high-stakes actions — the approval gate is a design choice, not a missing feature to be automated away later.

# **3\. Team Structure & Ownership**

Jigyasu, Sanskriti and Shivangi report into Ishani on client-side work; Suraj is the sole merger for the whole repository. Each person's responsibilities below are split into what they build, what they test, and — where it applies — the recurring process work they own.

## **Suraj — Backend, Orchestration & Release Lead**

- Builds: the FastAPI backend, all 17 database tables and migrations, MCP client wiring for Calendar/Gmail/GitHub/Slack, the LangGraph planner, LLM routing between Groq and Gemini, and the risk/approval-gate logic.
- Auth: owns JWT session authentication end to end plus OAuth2 authorization for every third-party provider (Section 5).
- Process: sole reviewer and merger for every pull request in the repo; builds and maintains the CI/CD pipeline; ships daily incremental deploys to Render.
- Testing: LLM evaluation pipeline, OAuth/JWT suite, sign-in/sign-up backend tests, MCP integration tests, the approval-gate bypass adversarial test, the security/RLS audit, and load testing (full named list in Section 15).

**Key files:** _backend/app/main.py, backend/app/agents/graph.py, backend/app/risk/approval_gate.py, backend/app/core/security.py, backend/migrations/ (full list in Appendix D)_

## **Ishani — Frontend Design Lead & Trust Surfaces**

- Builds: the app's design system (colour, type, spacing) and every screen in the core trust loop — Onboarding, Home/Dashboard, Task Composer, Agent Plan View, Approval Screen, OAuth Connections and Trust Dashboard.
- Backend-adjacent: owns the small model that writes notification-banner copy (backend/app/notifications/banner_model.py), built and evaluated separately from the planner so a bad banner line can never change what the agent actually does.
- Process: works alongside Suraj on testing generally; oversees Jigyasu, Sanskriti and Shivangi on client-side work.
- Testing: owns every widget/UI test for the screens a user actually sees; the Approval Screen and Plan View are held to a 100%-coverage, never-mis-render bar (Section 15).

**Key files:** _mobile/lib/core/theme.dart, mobile/lib/features/approval/approval_screen.dart, mobile/lib/features/oauth_connections/oauth_connections_screen.dart, backend/app/notifications/banner_model.py_

## **Jigyasu — Voice, Notifications Delivery & Activity Log**

- Builds: speech-to-text for the chatbot end to end (capture, transcription, accuracy tuning); the Sign Up, Sign In and Forgot Password screens; the Voice Input screen; the Activity Log / Audit Trail screen.
- Notifications: the client-side delivery of notifications — Suraj defines what fires and why (trigger_rules.py), Jigyasu makes sure it reaches the app correctly (push registration, in-app banner rendering, tap-to-open).
- Branding: designs the app logo and the icon/splash asset set.
- Testing: the STT accuracy suite, push-notification delivery tests, and widget tests for his own screens (Section 15).

**Key files:** _mobile/lib/features/voice_input/stt_service.dart, mobile/lib/features/activity_log/activity_log_screen.dart, mobile/lib/features/notifications/banner_widget.dart, mobile/assets/logo/_

## **Sanskriti — Daily Diary, Simpler Screens & Golden Dataset**

- Builds: Settings/Profile and Memory/Preferences — kept to the app's lowest-complexity screens on purpose, since she also carries the two recurring responsibilities below.
- Recurring — diary: writes a diary entry at the end of every working day (docs/diary/).
- Recurring — golden dataset: authors the golden-dataset test cases that Suraj's LLM eval suite and Ishani's banner-model eval run against.
- Testing: exploratory/manual QA support on the sign-in/sign-up and MCP suites, plus widget tests for her own screens.

**Key files:** _mobile/lib/features/settings/settings_screen.dart, mobile/lib/features/memory_prefs/memory_prefs_screen.dart, docs/diary/, docs/eval/_

## **Shivangi — Weekly Report, Simpler Screens & Golden Dataset**

- Builds: Manual To-Do Fallback and Daily/Weekly Digest — the same load-bearing logic as Sanskriti: kept light because of the recurring work below.
- Recurring — report: compiles a weekly report every Saturday (docs/reports/), so a complete report exists by end of October instead of a last-minute scramble.
- Recurring — golden dataset: supports the same golden-dataset work as Sanskriti.
- Testing: exploratory/manual QA support alongside Sanskriti, plus widget tests for her own screens.

**Key files:** _mobile/lib/features/manual_todo/manual_todo_screen.dart, mobile/lib/features/digest/digest_screen.dart, docs/reports/_

# **4\. Target Architecture & Design Principles**

## **4.1 System Overview**

Flutter App (mobile)

| text / voice input

v

FastAPI Backend <-- JWT session (Supabase Auth)

|

+-- LangGraph Planner (intent -> plan -> risk-tag)

| |

| v

| Risk Gate --(high risk)--> Approval --> push to app, wait for user

| | |

| v (low risk / approved) v

| MCP Clients <-----------------------------------

| | | | |

| Calendar Gmail GitHub Slack

|

+-- LLM Router (Groq primary, Gemini fallback)

+-- Memory (Supabase + pgvector)

|

v

Supabase Postgres (17 tables) + Render hosting

_Every arrow above is logged to execution_logs. The Risk Gate is a lookup against the hardcoded risk_rules table, not an LLM decision._

## **4.2 Design Principles**

| **Principle**                     | **Rule the team must follow**                                                                                                                                                        |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| MCP as the only integration layer | Every third-party capability is a swappable MCP client behind the identical call/response contract (Section 8.2); the planner never contains provider-specific branching.            |
| Risk gate hard, explanation soft  | risk_rules decides whether an action needs approval. The explanation LLM (Section 9.3) only writes plain-English copy describing that decision — it never influences it.             |
| Fail-closed                       | Any action whose action_type has no matching risk_rules row defaults to requires_approval = true. An unrecognized action is never treated as safe.                                   |
| Auditability by construction      | Every node transition, tool call, and approval decision writes to execution_logs before it has any external effect — the log is not reconstructed after the fact from side effects.  |
| Free-tier aware                   | LLM routing, hosting behaviour, and database write patterns are designed around Groq/Gemini/Render/Supabase free-tier limits (Section 2.3) from Day 1, not patched in during Week 6. |
| Reversible before, not after      | The system is built to make a risky action stoppable before it runs. It does not rely on detecting and undoing damage afterwards.                                                    |

# **5\. Authentication & Authorization Design**

## **5.1 Identity, Session & API Authentication**

- Identity & session: Supabase Auth issues a short-lived JWT access token (~1 hour) plus a refresh token on sign-up/sign-in. The Flutter app stores both in secure storage and refreshes silently before expiry.
- API authentication: every FastAPI route except health-check and the auth endpoints sits behind a JWT-verification dependency that checks the token against Supabase's JWKS — no second token system to maintain.
- Third-party OAuth (authorization-code flow): Calendar, Gmail, GitHub and Slack each get their own OAuth app and their own token pair, stored encrypted in oauth_connections, refreshed independently of the user's app session.
- Authorization ("oauthz"): a token's scopes control what is technically callable; risk_rules and the approval gate control what is allowed to happen without a human in the loop. Two separate layers, on purpose — a valid token is necessary but never sufficient for a high-risk action.

## **5.2 OAuth Scopes & Token Behaviour, by Provider**

| **Provider**    | **Scopes requested**                                                            | **Refresh behaviour**                                                                                                          | **If the token expires mid-task**                                                                                                                                                          |
| --------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Google Calendar | calendar.events (read/write on events only, not full calendar admin)            | Google issues a long-lived refresh token on first consent; access tokens (~1h) refresh silently server-side.                   | Task pauses at the failing step, status set to failed with a clear re-auth reason; D9's Testing-mode 7-day expiry detector flags this before it happens in an unverified Google Cloud app. |
| Gmail           | gmail.send, gmail.compose; read scope only if a read-type step is added later   | Same Google refresh-token model as Calendar; tokens are provider-scoped so revoking Gmail doesn't revoke Calendar.             | Draft steps degrade gracefully to "saved, not sent"; send steps (already gated by approval) surface a re-auth prompt instead of a silent failure.                                          |
| GitHub          | repo-scoped OAuth app tokens (issue/comment creation only, not full repo admin) | Classic GitHub OAuth tokens do not expire on a fixed schedule but can be revoked by the user at any time from GitHub settings. | A revoked token returns a 401 from GitHub; the MCP client surfaces this as a clean, typed error rather than a retry loop.                                                                  |
| Slack           | chat:write, channels:read scoped to a single workspace install                  | Slack bot tokens issued on workspace install do not expire under normal operation.                                             | An uninstalled app returns an invalid_auth error; the OAuth Connections screen shows the provider as disconnected.                                                                         |

# **6\. App Page Inventory**

17 screens across the MVP, plus one deferred item. Ownership follows Section 3; Sanskriti and Shivangi are kept to the lowest-complexity screens since they also carry the diary and report.

| **Owner** | **Page**                   | **Purpose**                                                     | **Complexity**         | **Backend dependency**                                              |
| --------- | -------------------------- | --------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------- |
| Ishani    | Onboarding / Splash        | First-run intro, permission priming                             | Low                    | None (static)                                                       |
| Ishani    | Home / Dashboard           | Task list, quick-entry point, status at a glance                | Medium                 | GET /tasks                                                          |
| Ishani    | Task Composer              | Text/voice entry point that kicks off a task                    | Medium                 | POST /tasks                                                         |
| Ishani    | Agent Plan View            | Step-by-step visualisation of what the agent intends to do      | High                   | task_plans, plan_steps                                              |
| Ishani    | Approval Screen            | Risk-flagged action + plain-English explanation, approve/reject | High (safety-critical) | approvals, risk_rules                                               |
| Ishani    | OAuth Connections          | Connect/disconnect Calendar, Gmail, GitHub, Slack               | Medium                 | oauth_connections                                                   |
| Ishani    | Trust Dashboard            | Accuracy / latency / cost observability for the user            | Medium                 | eval_runs, llm_usage_logs                                           |
| Jigyasu   | Sign Up                    | Account creation                                                | Low                    | POST /auth/signup                                                   |
| Jigyasu   | Sign In                    | Login                                                           | Low                    | POST /auth/login                                                    |
| Jigyasu   | Forgot Password / OTP      | Password reset + email verification                             | Low                    | auth endpoints                                                      |
| Jigyasu   | Voice Input                | Mic capture, listening state, live transcription                | Medium                 | on-device STT + Task Composer                                       |
| Jigyasu   | Activity Log / Audit Trail | Searchable history of every decision and action taken           | Medium                 | execution_logs                                                      |
| Jigyasu   | Notifications              | Push + in-app banner list, tap-to-open                          | Medium                 | notifications, sessions_device_tokens                               |
| Sanskriti | Settings / Profile         | Account settings, re-auth reminders, logout, delete account     | Low                    | profiles                                                            |
| Sanskriti | Memory / Preferences       | View / edit what the agent has learned about the user           | Low                    | user_preferences                                                    |
| Shivangi  | Manual To-Do Fallback      | Plain checklist when the agent isn't needed                     | Low                    | None (local only)                                                   |
| Shivangi  | Daily / Weekly Digest      | Rolled-up summary of what the agent did                         | Low-Medium             | digests                                                             |
| Backlog   | OCR / Photo-to-Task        | Camera capture -> task text (vision pipeline)                   | —                      | Deferred — not in MVP scope, revisit after acceptance criteria pass |

# **7\. Database Schema (Supabase PostgreSQL + pgvector)**

17 tables on Supabase/Postgres, owned end to end by Suraj, defined across one .sql migration file per table under backend/migrations/. The pgvector extension is enabled once for memory_embeddings. Every user-scoped table carries a row-level-security (RLS) policy restricting rows to user_id = auth.uid(); config/internal tables listed in Group F are service-role only and are never queried directly by the Flutter client.

## **7.1 RLS Pattern (applies to every user-scoped table below)**

alter table &lt;table_name&gt; enable row level security;

create policy "&lt;table_name&gt;\_owner_select" on &lt;table_name&gt;

for select using (user_id = auth.uid());

create policy "&lt;table_name&gt;\_owner_write" on &lt;table_name&gt;

for insert, update, delete using (user_id = auth.uid());

\-- join-based tables (task_plans, plan_steps) resolve ownership through

\-- the parent task's user_id rather than carrying their own user_id column.

## **Group A — Identity, Auth & Connections**

### **profiles**

Core user profile row, one per Supabase Auth user; created on first sign-in.

| **Column**           | **Type / Constraints**                        | **Notes**                                                   |
| -------------------- | --------------------------------------------- | ----------------------------------------------------------- |
| user_id              | uuid, PK, FK auth.users(id) ON DELETE CASCADE | Primary key, mirrors Supabase Auth identity                 |
| display_name         | text                                          | Shown across the app                                        |
| email                | text, NOT NULL                                | Denormalised copy of auth.users.email for query convenience |
| avatar_url           | text                                          | Nullable                                                    |
| onboarding_completed | boolean, DEFAULT false                        |                                                             |
| created_at           | timestamptz, DEFAULT now()                    |                                                             |

**RLS policy:** _user_id = auth.uid()_

### **oauth_connections**

One row per (user, provider) — encrypted OAuth token pair for Calendar, Gmail, GitHub, Slack.

| **Column**    | **Type / Constraints**                                      | **Notes**                                        |
| ------------- | ----------------------------------------------------------- | ------------------------------------------------ |
| id            | uuid, PK, DEFAULT gen_random_uuid()                         |                                                  |
| user_id       | uuid, FK profiles(user_id) ON DELETE CASCADE                |                                                  |
| provider      | text, CHECK IN ('google_calendar','gmail','github','slack') |                                                  |
| access_token  | text, ENCRYPTED (pgsodium/vault)                            | Never logged in plaintext                        |
| refresh_token | text, ENCRYPTED                                             | Nullable — GitHub classic tokens may not rotate  |
| scopes        | text\[\]                                                    | Granted OAuth scopes, audited against risk_rules |
| expires_at    | timestamptz                                                 |                                                  |
| status        | text, DEFAULT 'active'                                      | active \| expired \| revoked \| scope_mismatch   |
| connected_at  | timestamptz, DEFAULT now()                                  |                                                  |

**RLS policy:** _user_id = auth.uid() for SELECT/UPDATE/DELETE; INSERT restricted to the OAuth callback service role_

### **sessions_device_tokens**

Push-notification device targets (FCM tokens), one row per installed device.

| **Column**  | **Type / Constraints**                       | **Notes**      |
| ----------- | -------------------------------------------- | -------------- |
| id          | uuid, PK, DEFAULT gen_random_uuid()          |                |
| user_id     | uuid, FK profiles(user_id) ON DELETE CASCADE |                |
| fcm_token   | text, NOT NULL                               |                |
| device_type | text                                         | ios \| android |
| created_at  | timestamptz, DEFAULT now()                   |                |
| last_active | timestamptz                                  |                |

**RLS policy:** _user_id = auth.uid()_

## **Group B — Task Orchestration**

### **tasks**

One row per user-submitted request, text or voice.

| **Column**         | **Type / Constraints**                       | **Notes**                                                                                   |
| ------------------ | -------------------------------------------- | ------------------------------------------------------------------------------------------- |
| id                 | uuid, PK, DEFAULT gen_random_uuid()          |                                                                                             |
| user_id            | uuid, FK profiles(user_id) ON DELETE CASCADE |                                                                                             |
| input_type         | text                                         | text \| voice                                                                               |
| raw_input          | text                                         | User's original text, or empty for voice                                                    |
| transcription_text | text                                         | Nullable — STT output for voice input                                                       |
| status             | text, DEFAULT 'submitted'                    | submitted \| planning \| awaiting_approval \| executing \| completed \| failed \| cancelled |
| created_at         | timestamptz, DEFAULT now()                   |                                                                                             |
| completed_at       | timestamptz                                  |                                                                                             |

**RLS policy:** _user_id = auth.uid()_

### **task_plans**

LangGraph planner output for a task — one plan per task (re-planning creates a new row, not an overwrite).

| **Column**      | **Type / Constraints**               | **Notes**                                         |
| --------------- | ------------------------------------ | ------------------------------------------------- |
| id              | uuid, PK, DEFAULT gen_random_uuid()  |                                                   |
| task_id         | uuid, FK tasks(id) ON DELETE CASCADE |                                                   |
| planner_version | text                                 | Prompt/graph version tag, for regression tracking |
| plan_json       | jsonb, NOT NULL                      | Ordered step list as produced by the planner node |
| status          | text, DEFAULT 'draft'                | draft \| active \| superseded                     |
| created_at      | timestamptz, DEFAULT now()           |                                                   |

**RLS policy:** _via task_id -> tasks.user_id = auth.uid() (join-based policy)_

### **plan_steps**

Individual tool-call steps inside a plan — the unit the risk gate and MCP layer operate on.

| **Column**        | **Type / Constraints**                    | **Notes**                                                                           |
| ----------------- | ----------------------------------------- | ----------------------------------------------------------------------------------- |
| id                | uuid, PK, DEFAULT gen_random_uuid()       |                                                                                     |
| plan_id           | uuid, FK task_plans(id) ON DELETE CASCADE |                                                                                     |
| step_index        | int, NOT NULL                             | Execution order within the plan                                                     |
| tool_name         | text, NOT NULL                            | e.g. calendar.create_event                                                          |
| mcp_server        | text, NOT NULL                            | calendar \| gmail \| github \| slack                                                |
| input_params      | jsonb, NOT NULL                           |                                                                                     |
| risk_tier         | text, NOT NULL                            | low \| medium \| high (assigned by risk_rules lookup)                               |
| requires_approval | boolean, NOT NULL                         |                                                                                     |
| status            | text, DEFAULT 'pending'                   | pending \| awaiting_approval \| approved \| rejected \| executing \| done \| failed |
| output            | jsonb                                     | Tool call result once executed                                                      |
| executed_at       | timestamptz                               |                                                                                     |

**RLS policy:** _via plan_id -> task_plans -> tasks.user_id = auth.uid()_

### **approvals**

The human decision record for a risk-flagged step.

| **Column**       | **Type / Constraints**                    | **Notes**                                                 |
| ---------------- | ----------------------------------------- | --------------------------------------------------------- |
| id               | uuid, PK, DEFAULT gen_random_uuid()       |                                                           |
| step_id          | uuid, FK plan_steps(id) ON DELETE CASCADE |                                                           |
| user_id          | uuid, FK profiles(user_id)                |                                                           |
| decision         | text                                      | approved \| rejected                                      |
| explanation_text | text                                      | Advisory copy shown at decision time (Section 9.3)        |
| decided_at       | timestamptz                               |                                                           |
| response_time_ms | int                                       | Time from surfaced to decided — feeds the Trust Dashboard |

**RLS policy:** _user_id = auth.uid()_

## **Group C — Risk & Audit**

### **risk_rules**

The hardcoded, seeded safety table. Never written to by the app or by any LLM at runtime — only by a migration, reviewed like code.

| **Column**        | **Type / Constraints** | **Notes**                                                                     |
| ----------------- | ---------------------- | ----------------------------------------------------------------------------- |
| id                | serial, PK             |                                                                               |
| action_type       | text, NOT NULL         | e.g. gmail.send, calendar.delete_event                                        |
| mcp_server        | text, NOT NULL         |                                                                               |
| risk_tier         | text, NOT NULL         | low \| medium \| high                                                         |
| requires_approval | boolean, NOT NULL      |                                                                               |
| rationale         | text                   | Human-readable justification, shown to reviewers in PRs that touch this table |

**RLS policy:** _Global config, read-only to the app role; writable only via migration under service-role_

### **execution_logs**

The full audit trail — every planner decision, gate decision, MCP call, and LLM call writes a row here before it has any external effect.

| **Column**    | **Type / Constraints**                   | **Notes**                                                                                                    |
| ------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| id            | bigint, PK, GENERATED ALWAYS AS IDENTITY |                                                                                                              |
| task_id       | uuid, FK tasks(id) ON DELETE CASCADE     |                                                                                                              |
| step_id       | uuid, FK plan_steps(id)                  | Nullable — planner-level events have no step yet                                                             |
| agent_name    | text                                     | planner \| risk_gate \| mcp_calendar \| mcp_gmail \| mcp_github \| mcp_slack \| llm_router \| banner_model   |
| event_type    | text                                     | plan_created \| risk_tagged \| approval_requested \| approval_decided \| tool_called \| tool_result \| error |
| payload       | jsonb, NOT NULL                          |                                                                                                              |
| latency_ms    | int                                      |                                                                                                              |
| model_used    | text                                     | groq:&lt;model&gt; \| gemini:&lt;model&gt;, nullable for non-LLM events                                      |
| tokens_used   | int                                      |                                                                                                              |
| cost_estimate | numeric(10,6)                            |                                                                                                              |
| created_at    | timestamptz, DEFAULT now()               |                                                                                                              |

**RLS policy:** _via task_id -> tasks.user_id = auth.uid() for SELECT; INSERT restricted to service role_

## **Group D — Memory & Personalization**

### **memory_embeddings**

pgvector long-term memory store — task outcomes and stated preferences, embedded for similarity retrieval.

| **Column**     | **Type / Constraints**                       | **Notes**                               |
| -------------- | -------------------------------------------- | --------------------------------------- |
| id             | bigint, PK, GENERATED ALWAYS AS IDENTITY     |                                         |
| user_id        | uuid, FK profiles(user_id) ON DELETE CASCADE |                                         |
| content_text   | text, NOT NULL                               |                                         |
| embedding      | vector(768)                                  | pgvector column; HNSW index, cosine ops |
| category       | text                                         | preference \| outcome \| correction     |
| source_task_id | uuid, FK tasks(id)                           |                                         |
| created_at     | timestamptz, DEFAULT now()                   |                                         |

**RLS policy:** _user_id = auth.uid()_

### **user_preferences**

Structured, durable preferences distilled from memory so the planner can reference them without a similarity search on every call.

| **Column**         | **Type / Constraints**                       | **Notes**                                        |
| ------------------ | -------------------------------------------- | ------------------------------------------------ |
| id                 | uuid, PK, DEFAULT gen_random_uuid()          |                                                  |
| user_id            | uuid, FK profiles(user_id) ON DELETE CASCADE |                                                  |
| preference_key     | text, NOT NULL                               | e.g. default_meeting_length, always_cc           |
| preference_value   | jsonb, NOT NULL                              |                                                  |
| confidence         | numeric(3,2)                                 | 0.00–1.00                                        |
| last_reinforced_at | timestamptz                                  |                                                  |
| source             | text                                         | extracted_from_memory \| user_stated_in_settings |

**RLS policy:** _user_id = auth.uid()_

## **Group E — Communication**

### **digests**

Daily/weekly rolled-up summaries generated by a scheduled job.

| **Column**     | **Type / Constraints**                       | **Notes**                   |
| -------------- | -------------------------------------------- | --------------------------- |
| id             | uuid, PK, DEFAULT gen_random_uuid()          |                             |
| user_id        | uuid, FK profiles(user_id) ON DELETE CASCADE |                             |
| period_type    | text                                         | daily \| weekly             |
| summary_text   | text, NOT NULL                               |                             |
| tasks_included | jsonb                                        | Array of task_id references |
| generated_at   | timestamptz, DEFAULT now()                   |                             |

**RLS policy:** _user_id = auth.uid()_

### **notifications**

In-app + push notification records, including the LLM-written banner line.

| **Column**      | **Type / Constraints**                       | **Notes**                                                           |
| --------------- | -------------------------------------------- | ------------------------------------------------------------------- |
| id              | uuid, PK, DEFAULT gen_random_uuid()          |                                                                     |
| user_id         | uuid, FK profiles(user_id) ON DELETE CASCADE |                                                                     |
| type            | text                                         | approval_needed \| task_completed \| digest_ready \| oauth_expiring |
| title           | text                                         |                                                                     |
| body            | text                                         |                                                                     |
| banner_text     | text                                         | Short LLM-written line (Section 9.3), advisory only                 |
| read            | boolean, DEFAULT false                       |                                                                     |
| related_task_id | uuid, FK tasks(id)                           |                                                                     |
| created_at      | timestamptz, DEFAULT now()                   |                                                                     |

**RLS policy:** _user_id = auth.uid()_

## **Group F — Observability, Eval & MCP Health (service-role only)**

### **llm_usage_logs**

Every LLM call, for free-tier rate-limit tracking and routing audits.

| **Column**     | **Type / Constraints**                   | **Notes**                                                              |
| -------------- | ---------------------------------------- | ---------------------------------------------------------------------- |
| id             | bigint, PK, GENERATED ALWAYS AS IDENTITY |                                                                        |
| provider       | text                                     | groq \| gemini                                                         |
| model          | text                                     |                                                                        |
| tokens_in      | int                                      |                                                                        |
| tokens_out     | int                                      |                                                                        |
| latency_ms     | int                                      |                                                                        |
| request_type   | text                                     | planning \| routing \| risk_explanation \| banner \| memory_extraction |
| rate_limit_hit | boolean, DEFAULT false                   |                                                                        |
| created_at     | timestamptz, DEFAULT now()               |                                                                        |

**RLS policy:** _Internal — service-role only, never exposed to the client_

### **eval_cases**

Golden-dataset test cases authored by Sanskriti and Shivangi (Section 15).

| **Column**      | **Type / Constraints**              | **Notes**                                                                         |
| --------------- | ----------------------------------- | --------------------------------------------------------------------------------- |
| id              | uuid, PK, DEFAULT gen_random_uuid() |                                                                                   |
| category        | text                                | planner \| router \| risk_explanation \| banner \| oauth_edge_case \| mcp_failure |
| input_prompt    | text, NOT NULL                      |                                                                                   |
| expected_output | jsonb                               |                                                                                   |
| actual_output   | jsonb                               |                                                                                   |
| pass            | boolean                             |                                                                                   |
| run_id          | uuid, FK eval_runs(id)              |                                                                                   |
| evaluated_at    | timestamptz                         |                                                                                   |

**RLS policy:** _Internal — service-role only_

### **eval_runs**

One row per eval-suite execution in CI, feeds the Trust Dashboard's accuracy panel.

| **Column**     | **Type / Constraints**              | **Notes**                                                               |
| -------------- | ----------------------------------- | ----------------------------------------------------------------------- |
| id             | uuid, PK, DEFAULT gen_random_uuid() |                                                                         |
| run_date       | timestamptz, DEFAULT now()          |                                                                         |
| suite_name     | text                                | planner_eval \| router_eval \| risk_explainer_eval \| banner_model_eval |
| pass_count     | int                                 |                                                                         |
| fail_count     | int                                 |                                                                         |
| avg_latency_ms | int                                 |                                                                         |
| notes          | text                                |                                                                         |

**RLS policy:** _Internal — service-role only_

### **mcp_server_registry**

Health tracking for the four MCP servers, polled and surfaced on the Trust Dashboard.

| **Column**        | **Type / Constraints** | **Notes**                            |
| ----------------- | ---------------------- | ------------------------------------ |
| id                | serial, PK             |                                      |
| server_name       | text                   | calendar \| gmail \| github \| slack |
| endpoint_url      | text                   |                                      |
| status            | text                   | healthy \| degraded \| down          |
| last_health_check | timestamptz            |                                      |
| version           | text                   |                                      |

**RLS policy:** _Internal — service-role only_

## **7.2 Indexing & Vector Search**

- memory_embeddings.embedding uses an HNSW index with cosine similarity ops, matching the standard pgvector operator class used for nearest-neighbour retrieval on 768-dimension embeddings.
- Every foreign key used in an RLS join path (task_plans.task_id, plan_steps.plan_id, approvals.step_id, execution_logs.task_id) is indexed, since RLS policies evaluate the join on every row read.
- eval_cases.run_id and llm_usage_logs.created_at are indexed to keep the Trust Dashboard's aggregate queries fast without a service-tier Postgres plan.

# **8\. MCP Integration & LangGraph Orchestration**

## **8.1 LangGraph Planner State Management**

The planner is built as an explicit LangGraph StateGraph rather than a single prompt, so every intermediate decision is a named, inspectable node rather than hidden inside one large completion. State is persisted through a checkpointer backed by Supabase Postgres, keyed by thread_id = task_id, so a task that is mid-approval when the app is closed resumes exactly where it left off the next time the user opens it — the graph does not need to re-plan from scratch.

### **State Schema**

| **Field**              | **Type**              | **Description**                                                     |
| ---------------------- | --------------------- | ------------------------------------------------------------------- |
| task_id                | str (uuid)            | Also the checkpointer thread_id                                     |
| user_id                | str (uuid)            | Used for every downstream MCP call and RLS-scoped read              |
| raw_input / input_type | str / enum            | The original text or voice-transcribed request                      |
| intent                 | str                   | Output of the intent-classify node                                  |
| plan                   | list\[Step\]          | Ordered step objects: tool_name, mcp_server, input_params           |
| current_step_index     | int                   | Which step the graph is currently on                                |
| step_results           | dict\[int, Any\]      | Output of each completed step, available to later steps             |
| risk_flags             | dict\[int, RiskTier\] | Result of the risk-tag node per step                                |
| approval_status        | dict\[int, str\]      | pending \| approved \| rejected, per step requiring approval        |
| retries                | dict\[int, int\]      | Per-step retry counter for transient MCP/LLM failures               |
| error                  | Optional\[str\]       | Set on unrecoverable failure; halts the graph, task.status = failed |

### **Node Sequence**

intent_classify --> plan --> risk_tag --> \[conditional\]

|

requires_approval? | no --> execute --> log --> next_step / complete

v

yes

|

approval_gate (halts graph, checkpoint saved)

|

user decision arrives asynchronously via POST /approvals/{id}

|

approved --> execute --> log --> next_step / complete

rejected --> log --> skip_step / halt_task

Every arrow above corresponds to a conditional edge in the graph, not a hardcoded sequence: the risk_tag node's output (requires_approval, from a risk_rules lookup) is what routes execution to either the execute node directly or through the approval_gate node first. This is the single point in the codebase where Section 9's hardcoded gate logic actually forks the graph — it is intentionally the only branch in the whole planner that a prompt cannot influence.

### **Retries, Idempotency & Multi-Step Ordering**

- Each MCP tool call carries a client-generated idempotency key derived from plan_id + step_index, so a retried call after a timeout cannot double-create a calendar event or double-send an email.
- Transient errors (timeout, 5xx from an MCP server, a rate-limited LLM call) increment retries\[step\] and retry with exponential backoff, capped at 3 attempts before the step is marked failed and the graph halts with a clear error surfaced to the Activity Log.
- A mixed-risk multi-step plan (e.g. create an event, then email an attendee) executes low-risk steps as they become ready and pauses only the specific step that is high-risk — later low-risk steps that don't depend on the paused step's output are not blocked behind it.

## **8.2 MCP Client Architecture**

All four providers are integrated via the **Model Context Protocol (MCP)** using official, cloud-hosted remote MCP servers. This makes AgentOps a genuinely MCP-native application — the execute node communicates with tools exclusively through the MCP JSON-RPC protocol, not through direct REST API wrappers.

### **Why Official Remote MCP Servers**

Each provider now maintains an official hosted MCP endpoint:

| **Provider**     | **Official MCP Endpoint**                        | **Hosted by** |
| ---------------- | ------------------------------------------------ | ------------- |
| Google Calendar  | `https://calendarmcp.googleapis.com/mcp/v1`      | Google        |
| Gmail            | `https://gmailmcp.googleapis.com/mcp/v1`         | Google        |
| GitHub           | Official GitHub MCP remote endpoint              | GitHub        |
| Slack            | `https://mcp.slack.com/mcp`                      | Slack         |

These are cloud-hosted, persistent services. There are no subprocesses to spawn, no Node.js runtime required on Render, and no session lifecycle to manage. Each tool call is a standard HTTP POST with the user's OAuth token in the `Authorization` header — making per-user multi-tenancy trivially correct.

### **How Per-User Auth Works**

Every user's OAuth token is stored in `oauth_connections` (written during D8-D10). When the execute node runs a step for a given user:

1. Fetch that user's token for the relevant provider from `oauth_connections`.
2. Call the official MCP endpoint with `Authorization: Bearer <user_token>`.
3. The hosted MCP server uses that token to call the provider API on the user's behalf.
4. Result is returned as a standard MCP JSON-RPC response.

Alice's token goes to Alice's Calendar. Bob's token goes to Bob's GitHub. They never mix. No proxy, no session store, no subprocesses.

### **MCP Client Envelope**

Every provider client (calendar_client.py, gmail_client.py, github_client.py, slack_client.py) implements the identical envelope below, so the planner and the risk gate never contain provider-specific branching.

| **Field**       | **Direction** | **Description**                                                                                                                                                                                                                            |
| --------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| tool_name       | request       | e.g. calendar.create_event — the base tool identifier; for the handful of tools whose risk_rules.action_type is more specific (Section 9.2), the risk-tag node derives the exact action_type from tool_name plus known input_params fields |
| mcp_server      | request       | calendar \| gmail \| github \| slack                                                                                                                                                                                                       |
| input_params    | request       | Provider-specific JSON payload                                                                                                                                                                                                             |
| idempotency_key | request       | plan_id:step_index                                                                                                                                                                                                                         |
| status          | response      | success \| error \| rate_limited                                                                                                                                                                                                           |
| output          | response      | Provider result on success                                                                                                                                                                                                                 |
| error           | response      | Typed error code + human-readable message on failure                                                                                                                                                                                       |
| latency_ms      | response      | Logged to execution_logs on every call                                                                                                                                                                                                     |

### **Design Decision Record**

See `docs/decisions/mcp-wrapper-vs-native.md` for the full analysis of why official remote MCP servers were chosen over REST wrappers or per-user stdio subprocess spawning. Short version: official hosted endpoints solve multi-tenancy via per-request OAuth token injection, with no infrastructure overhead.

## **8.3 Per-Provider Workflows**

### **Google Calendar MCP**

**Integration:** Official Google remote MCP server (`https://calendarmcp.googleapis.com/mcp/v1`). Currently in Developer Preview. Requires Calendar API enabled in GCP project. Auth: user's Google OAuth token in `Authorization` header per request.

Used for any scheduling step. list_events and find_free_slots are read-only and inform the planner before it proposes a create/update step.

| **Tool**                                                                      | **Purpose**                              | **Default risk tier** | **Approval default**                         |
| ----------------------------------------------------------------------------- | ---------------------------------------- | --------------------- | -------------------------------------------- |
| calendar.list_events                                                          | Read a date range to check for conflicts | low                   | No                                           |
| calendar.find_free_slots                                                      | Compute open slots across a range        | low                   | No                                           |
| calendar.create_event_internal_only / calendar.create_event_external_attendee | Create a new event with attendees        | medium / high         | No (internal-only) / Yes (external attendee) |
| calendar.update_event                                                         | Move/edit an existing event              | medium                | No                                           |
| calendar.delete_event                                                         | Remove an event                          | high                  | Yes                                          |

_Example plan_steps.input_params:_

{"tool_name": "calendar.create_event",

"mcp_server": "calendar",

"input_params": {

"title": "Call with Professor Rao",

"start": "2026-09-24T15:00:00+05:30",

"end": "2026-09-24T15:30:00+05:30",

"attendees": \["<professor.rao@university.edu>"\]

}}

### **Gmail — Read/Draft via MCP, Send via Resend**

**Architecture decision:** Gmail is split across two integrations:

- **Gmail MCP server** (official Google remote MCP, Developer Preview) — handles list, read, and draft operations via MCP JSON-RPC. Auth: user's Google OAuth token in `Authorization` header per request.
- **Resend** (transactional email API, free tier: 3,000 emails/month) — handles all outbound sending. Auth: Resend API key (single key in `.env`, not per-user). From-address is a verified sender domain configured once.

**Why Resend for sending:** Gmail's official MCP server does not yet support `send_message` reliably in Developer Preview. Resend is a standard transactional email service with better deliverability than direct Gmail SMTP, a trivial REST API, and a generous free tier that comfortably covers the capstone demo load. This is a common production pattern — mailbox reads from the user's own account, outbound delivery through a dedicated transactional service.

Draft creation is low risk and never blocks; sending is always treated as high risk regardless of recipient, because an email is not reversible once sent.

| **Tool**            | **Purpose**                         | **Integration** | **Default risk tier** | **Approval default**        |
| ------------------- | ----------------------------------- | --------------- | --------------------- | --------------------------- |
| gmail.list_messages | Read recent messages for context    | Gmail MCP       | low                   | No                          |
| gmail.get_message   | Read a single message body          | Gmail MCP       | low                   | No                          |
| gmail.create_draft  | Prepare an email without sending it | Gmail MCP       | low                   | No                          |
| gmail.send_message  | Send an email                       | Resend API      | high                  | Yes — always, no exceptions |

_Example plan_steps.input_params (send):_

{"tool_name": "gmail.send_message",

"mcp_server": "gmail",

"input_params": {

"to": \["<professor.rao@university.edu>"\],

"subject": "Agenda for Thursday's call",

"body": "Hi Professor Rao, ..." }}

_The execute node routes `gmail.send_message` to the Resend client, not the Gmail MCP server. All other gmail.* tools route to the Gmail MCP server._



### **GitHub MCP**

**Integration:** Official GitHub remote MCP server. Hosted by GitHub. Auth: user's GitHub OAuth token in `Authorization` header per request. Stable and production-grade.

Scoped to issue-level interactions only in the MVP — no PR merges, no repo administration, deliberately narrower than the OAuth app's technical ceiling.

| **Tool**                 | **Purpose**                        | **Default risk tier** | **Approval default** |
| ------------------------ | ---------------------------------- | --------------------- | -------------------- |
| github.list_issues       | Read open issues for context       | low                   | No                   |
| github.create_issue      | File a new issue                   | medium                | No                   |
| github.comment_on_issue  | Add a comment to an existing issue | medium                | No                   |
| github.create_pr_comment | Comment on a pull request          | medium                | No                   |

_Example plan_steps.input_params:_

{"tool_name": "github.create_issue",

"mcp_server": "github",

"input_params": {

"repo": "team/agentops",

"title": "Investigate STT drift on noisy audio",

"body": "Filed from Task #482" }}

### **Slack MCP**

**Integration:** Official Slack-hosted MCP server (`https://mcp.slack.com/mcp`). Generally available, production-grade. Auth: Slack OAuth token (bot token with required scopes) per request via `Authorization` header.

Posting to a public/shared channel is treated as higher risk than a direct message, since a public post is visible to a whole workspace instantly.

| **Tool**                                           | **Purpose**                  | **Default risk tier**               | **Approval default**           |
| -------------------------------------------------- | ---------------------------- | ----------------------------------- | ------------------------------ |
| slack.list_channels                                | Read available channels      | low                                 | No                             |
| slack.post_message_dm / slack.post_message_channel | Post to a channel or DM      | medium (DM) / high (public channel) | No (DM) / Yes (public channel) |
| slack.add_reaction                                 | React to an existing message | low                                 | No                             |

_Example plan_steps.input_params:_

{"tool_name": "slack.post_message",

"mcp_server": "slack",

"input_params": {

"channel": "#team-standup",

"text": "Daily digest: 3 tasks completed, 1 pending approval." }}

## **8.4 LLM Router — Groq / Gemini**

| **Rule**                          | **Detail**                                                                                                                                                                       |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Default provider                  | Groq, for planning, intent classification, and routing calls — chosen for latency on the free tier.                                                                              |
| Fallback trigger                  | Any 429 (rate-limited) or 5xx response from Groq, or a call requiring a Gemini-specific capability, routes to Gemini automatically — no manual intervention, no dropped request. |
| Logging                           | Every call — successful or not — writes a row to llm_usage_logs (provider, model, tokens, latency, rate_limit_hit) so routing is auditable, not a black box.                     |
| Separation from the risk decision | The router chooses which model answers a prompt. It never chooses whether an action needs approval — that is risk_rules alone (Section 9).                                       |

# **9\. Risk & Approval Gate**

This is the single most safety-critical subsystem in AgentOps, and the one place in the whole plan where "close enough" is not an acceptable bar. Everything in this section exists to guarantee one property: no action tagged high-risk executes without an explicit, logged, human approval — 100% of the time, including under adversarial testing (Acceptance A2).

## **9.1 risk_rules — Seed Data**

risk_rules is populated by a migration, reviewed like code, and is never written to by the running application or by any LLM. A representative seed set:

| **action_type**                         | **mcp_server** | **risk_tier** | **requires_approval** | **rationale**                                                                            |
| --------------------------------------- | -------------- | ------------- | --------------------- | ---------------------------------------------------------------------------------------- |
| calendar.list_events                    | calendar       | low           | false                 | Read-only, no side effects                                                               |
| calendar.create_event_internal_only     | calendar       | medium        | false                 | Reversible, all attendees on a known/internal domain                                     |
| calendar.create_event_external_attendee | calendar       | high          | true                  | Involves a party outside the organization; needs confirmation before external visibility |
| calendar.delete_event                   | calendar       | high          | true                  | Destructive and not easily reversible for the invitee's view                             |
| gmail.create_draft                      | gmail          | low           | false                 | Nothing leaves the user's account                                                        |
| gmail.send_message                      | gmail          | high          | true                  | Irreversible the moment it is sent                                                       |
| github.create_issue                     | github         | medium        | false                 | Reversible — can be closed/edited                                                        |
| github.comment_on_issue                 | github         | medium        | false                 | Visible externally but editable/deletable                                                |
| slack.post_message_dm                   | slack          | medium        | false                 | Private, low blast radius                                                                |
| slack.post_message_channel              | slack          | high          | true                  | Instantly visible to a whole workspace                                                   |
| &lt;any action_type not listed&gt;      | \*             | high          | true                  | Fail-closed default — see 9.2                                                            |

## **9.2 approval_gate.py — Fail-Closed Enforcement Logic**

def evaluate(step: PlanStep) -> RiskDecision:

rule = risk_rules.lookup(step.tool_name, step.mcp_server)

if rule is None:

\# No matching row: default-deny, never default-allow.

return RiskDecision(risk_tier="high", requires_approval=True,

rationale="no matching risk_rules entry — fail closed")

log_execution(step, event_type="risk_tagged", payload=rule)

return RiskDecision(risk_tier=rule.risk_tier,

requires_approval=rule.requires_approval,

rationale=rule.rationale)

def gate(step: PlanStep, decision: RiskDecision):

if not decision.requires_approval:

return execute(step) # low/medium risk, auto-execute

create_approval_request(step, decision) # halts graph, checkpoint saved

return WAIT_FOR_USER # never proceeds without an explicit approvals row

- No code path in the system can call execute() on a high-risk step without first passing through gate() and receiving an explicit approved decision recorded in the approvals table.
- The lookup is a plain table read — there is no LLM call, no prompt, and no model inference anywhere between a plan step and the decision of whether it needs a human. This is deliberate: a misjudged "this looks safe" call from a language model would defeat the entire point of human-in-the-loop.
- Any change to risk_rules ships as a reviewed migration with Suraj's sign-off (Section 3), exactly like a change to application code — never as a runtime configuration value the app can adjust on its own.
- For the handful of tools whose risk genuinely depends on the call's own parameters — calendar.create_event (attendee domain) and slack.post_message (target channel type) — the risk-tag node computes the specific action_type (e.g. calendar.create_event_internal_only vs. calendar.create_event_external_attendee, slack.post_message_dm vs. slack.post_message_channel) as a pure, deterministic function of fields already present in plan_steps.input_params, before it ever reaches risk_rules.lookup(). The lookup itself is unchanged: still a flat read on action_type + mcp_server, still no LLM in the loop, still fail-closed if the computed action_type has no matching row.

## **9.3 The Explanation LLM — Advisory Only**

For actions already flagged as needing approval, a small, fast LLM call writes a clear, plain-English explanation of what is about to happen and why it was flagged — helping the human decide faster, not deciding for them. It is built and evaluated completely separately from the planner (owned by Ishani, not Suraj), specifically so a bad or vague explanation can never change what the agent actually does.

SYSTEM: You explain, in one or two plain sentences, an action an AI assistant

is about to take on a user's behalf. State only facts present in the input.

Never invent details. Never suggest the user should or shouldn't approve —

describe, don't recommend. Non-alarming tone.

INPUT: {"tool_name": "gmail.send_message",

"input_params": {"to": \["<professor.rao@university.edu>"\],

"subject": "Agenda for Thursday's call"}}

OUTPUT: "This will send an email to <professor.rao@university.edu> with the

subject 'Agenda for Thursday's call'."

- Guardrail 1 — no false claims about the action (test_risk_explainer_no_false_claims_about_the_action, Section 15).
- Guardrail 2 — non-alarming, non-persuasive tone; the explainer describes, it never argues for approve or reject (test_risk_explainer_tone_is_non_alarming).
- Guardrail 3 — output is capped in length and stored in approvals.explanation_text purely as a display field; nothing in the approval_gate.py logic reads this text to make a decision.

## **9.4 Adversarial Bypass Testing**

The approval-gate bypass test (test_approval_gate_bypass_attempt_always_fails, Section 15) deliberately tries to reach execute() on a high-risk step through every code path the team can think of — direct API calls, replayed requests, malformed plan JSON, missing risk_rules rows — and asserts every single attempt is blocked. This single test is non-negotiable: a failing run blocks the release candidate at Gate 4 regardless of what else is green (Section 17), and it is the direct test for Acceptance Criterion A2.

# **10\. Backend API Reference**

Every route sits behind the JWT-verification dependency (Section 5.1) except the two marked Public.

| **Method** | **Path**                   | **Auth** | **Purpose**                                                         |
| ---------- | -------------------------- | -------- | ------------------------------------------------------------------- |
| GET        | /health                    | Public   | Liveness check for Render + CI                                      |
| POST       | /auth/signup               | Public   | Create an account (delegates to Supabase Auth)                      |
| POST       | /auth/login                | Public   | Issue JWT access + refresh token pair                               |
| POST       | /auth/reset-password       | Public   | Trigger a password-reset email                                      |
| GET        | /oauth/{provider}/connect  | JWT      | Start the OAuth consent redirect for a provider                     |
| GET        | /oauth/{provider}/callback | JWT      | Exchange the authorization code, store encrypted tokens             |
| DELETE     | /oauth/{provider}          | JWT      | Disconnect / revoke a provider connection                           |
| POST       | /tasks                     | JWT      | Submit a new text or voice task, kicks off the LangGraph run        |
| GET        | /tasks                     | JWT      | List the user's tasks with status                                   |
| GET        | /tasks/{id}                | JWT      | Task detail including its plan and step statuses                    |
| GET        | /tasks/{id}/plan           | JWT      | Full task_plans + plan_steps for the Agent Plan View                |
| POST       | /approvals/{step_id}       | JWT      | Record an approve/reject decision, resumes the LangGraph checkpoint |
| GET        | /approvals/pending         | JWT      | List steps currently awaiting this user's decision                  |
| GET        | /notifications             | JWT      | List in-app notifications                                           |
| POST       | /notifications/{id}/read   | JWT      | Mark a notification read                                            |
| GET        | /digests                   | JWT      | List daily/weekly digests                                           |
| GET        | /memory/preferences        | JWT      | List learned user_preferences for the Memory screen                 |
| PATCH      | /memory/preferences/{id}   | JWT      | Edit or delete a learned preference                                 |
| GET        | /dashboard/metrics         | JWT      | Aggregate latency/cost/accuracy for the Trust Dashboard             |
| GET        | /activity-log              | JWT      | Paginated, filterable execution_logs for the Activity Log screen    |

# **11\. Folder Structure & Code Organization**

Suraj sets this up on Day 1; everyone works inside it from there. This is the full, file-level layout — every key file each team member creates is named in place, and the same files are indexed by owner in Appendix D.

agentops/

|-- backend/ # Suraj

| |-- app/

| | |-- main.py # FastAPI entrypoint

| | |-- api/

| | | |-- auth.py # signup / login / reset

| | | |-- oauth.py # OAuth consent + callback

| | | |-- tasks.py # POST/GET /tasks

| | | |-- approvals.py

| | | |-- notifications.py

| | | |-- digests.py

| | | \`-- memory.py

| | |-- agents/

| | | |-- graph.py # LangGraph StateGraph

| | | \`-- nodes.py # planner pipeline nodes

| | |-- mcp_clients/

| | | |-- calendar_client.py

| | | |-- gmail_client.py

| | | |-- github_client.py

| | | \`-- slack_client.py

| | |-- llm/

| | | |-- router.py # Groq / Gemini fallback

| | | |-- groq_client.py

| | | \`-- gemini_client.py

| | |-- risk/

| | | |-- risk_rules.py # hardcoded risk tiers

| | | \`-- approval_gate.py # fail-closed enforcement

| | |-- notifications/

| | | |-- trigger_rules.py # Suraj - event types + firing

| | | \`-- banner_model.py # Ishani - banner-text LLM call

| | |-- memory/

| | | |-- embedding.py

| | | \`-- retrieval.py

| | |-- db/

| | | \`-- models.py

| | |-- core/

| | | |-- config.py

| | | \`-- security.py # JWT verify / refresh

| | \`-- tests/ # full named list in Section 15

| | \`-- ... (see Section 15 for every file)

| |-- migrations/ # one .sql file per table + RLS

| |-- requirements.txt

| \`-- .env.example

|-- mobile/

| |-- lib/

| | |-- core/

| | | |-- theme.dart # Ishani - design tokens

| | | \`-- router.dart # Ishani - navigation shell

| | |-- features/

| | | |-- onboarding/onboarding_screen.dart - Ishani

| | | |-- home/home_screen.dart - Ishani

| | | |-- task_composer/task_composer_screen.dart - Ishani

| | | |-- plan_view/plan_view_screen.dart - Ishani

| | | |-- approval/approval_screen.dart - Ishani

| | | |-- oauth_connections/oauth_connections_screen.dart - Ishani

| | | |-- trust_dashboard/trust_dashboard_screen.dart - Ishani

| | | |-- auth/ (signup, signin, forgot_password screens) - Jigyasu

| | | |-- voice_input/ (voice_input_screen, stt_service) - Jigyasu

| | | |-- activity_log/activity_log_screen.dart - Jigyasu

| | | |-- notifications/ (notifications_screen, banner_widget) - Jigyasu

| | | |-- settings/settings_screen.dart - Sanskriti

| | | |-- memory_prefs/memory_prefs_screen.dart - Sanskriti

| | | |-- manual_todo/manual_todo_screen.dart - Shivangi

| | | \`-- digest/digest_screen.dart - Shivangi

| | \`-- main.dart

| |-- assets/

| | |-- logo/ # Jigyasu - logo + icon assets

| | \`-- icons/

| |-- test/screens/ # full named list in Section 15

| \`-- pubspec.yaml

|-- docs/

| |-- plan/ # this document, source form

| |-- diary/ # Sanskriti - one .md per day

| |-- reports/ # Shivangi - weekly reports

| |-- eval/ # golden dataset (Sanskriti/Shivangi)

| \`-- architecture/ # diagrams, schema exports

|-- .github/workflows/

| |-- ci.yml # lint + test + eval-smoke

| \`-- deploy.yml # Render auto-deploy on merge

\`-- README.md

## **11.1 Key Files Explained**

| **File**                                                  | **Purpose**                                                                                                                                                                                                                                               |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| backend/app/main.py                                       | FastAPI application entrypoint — mounts every router in api/, registers the JWT-verification dependency globally, wires the Supabase client and CORS, and exposes /health for Render's readiness probe and CI.                                            |
| backend/app/agents/graph.py                               | Defines the LangGraph StateGraph itself — the nodes from Section 8.1, the conditional edge that forks to the approval_gate, and the Postgres-backed checkpointer configuration. This is the file that makes the agent loop resumable across app restarts. |
| backend/app/agents/nodes.py                               | The actual node implementations (intent_classify, plan, risk_tag, execute, log) that graph.py wires together — kept separate from graph.py so the graph's shape and each node's logic can be reviewed independently.                                      |
| backend/app/risk/approval_gate.py                         | The fail-closed enforcement logic in Section 9.2 — the single file every high-risk action must pass through, and the target of the adversarial bypass test.                                                                                               |
| backend/app/core/security.py                              | JWT verification/refresh dependency used by every protected route; the one place token validation logic lives, so it is audited once rather than per-route.                                                                                               |
| mobile/lib/features/approval/approval_screen.dart         | The safety-critical screen: renders the risk explanation from Section 9.3 and the approve/reject controls. Held to 100% widget-test coverage and a never-mis-render bar (Section 15).                                                                     |
| mobile/lib/features/plan_view/plan_view_screen.dart       | Renders the ordered plan_steps for a task so the user can see, before anything executes, exactly what the agent intends to do — the core of Goal G2.                                                                                                      |
| mobile/lib/features/voice_input/stt_service.dart          | Wraps the speech_to_text package: mic capture, live transcription, permission/timeout/retry error states, and accuracy tuning for accents and background noise (Jigyasu, Section 15).                                                                     |
| mobile/lib/features/activity_log/activity_log_screen.dart | Renders execution_logs as a searchable, filterable audit trail — the user-facing half of the auditability principle in Section 4.2.                                                                                                                       |

# **12\. CI/CD & Deployment**

- Every pull request runs: lint (ruff + dart analyze) → unit tests (pytest + flutter test) → a smoke subset of the eval suite → a build check. All four must pass.
- Branch protection on main: no direct pushes, one required review, all checks green. Suraj is the sole merger, so nothing lands without a second pair of eyes on the diff.
- Merge to main auto-deploys the backend to Render — "daily incremental" means small merges land and go live the same day rather than saving up for big-bang releases, so a broken deploy is always traceable to a small diff.
- The Flutter app doesn't deploy daily (store review lag); CI instead builds a debug APK on every merge and pushes it to Firebase App Distribution so the whole team always tests against the latest build.

# **13\. Working Rhythm & Calendar**

Build starts Monday, 24 August 2026. The team works six days a week (Monday–Saturday), Sunday kept free as a buffer/rest day — if a task slips, it has somewhere to land without eating into the next week. That gives 41 working days across 7 weeks, ending Friday, 9 October 2026: the first week of October, as targeted.

Saturday of every week is a review + PR-merge day — whatever is in flight gets wrapped up and merged rather than carried forward silently. Section 14 lays out every one of the 41 days.

Frontend/backend pattern: in Weeks 1–2, screens are built against mock data while backend infrastructure comes online; from Week 3 onward, screens get wired to real endpoints as each one lands. A screen's "build" day and its "wire to real data" day are sometimes weeks apart in Section 14 on purpose — that gap is not slippage.

| **Week** | **Dates**    | **Focus**                                                                                      |
| -------- | ------------ | ---------------------------------------------------------------------------------------------- |
| Week 1   | 24–29 Aug    | Foundations — repo, DB v1, FastAPI scaffold, JWT, design system, screen shells, logo direction |
| Week 2   | 31 Aug–5 Sep | Auth + OAuth (Google/GitHub/Slack), core tables, golden dataset v1                             |
| Week 3   | 7–12 Sep     | LangGraph planner, MCP clients (Calendar/Gmail/GitHub), approval gate, core screens wired      |
| Week 4   | 14–19 Sep    | Memory, notifications (trigger + delivery + banner model), digests                             |
| Week 5   | 21–26 Sep    | Test suites stood up in CI, Trust Dashboard wired                                              |
| Week 6   | 28 Sep–3 Oct | Integration, load & security testing, polish, release candidate                                |
| Week 7   | 5–9 Oct      | Final smoke test, demo rehearsal, report + submission                                          |

# **14\. Day-by-Day Plan with Dependencies (41 Days)**

_Every task assumes the prior day's dependency for that same track is complete unless noted. Sanskriti additionally logs a diary entry at the end of every working day (Section 16); Shivangi additionally compiles the weekly report every Saturday (Section 16) — not repeated in every cell below._

| **Day** | **Date**   | **Suraj**                                                                                      | **Ishani**                                                                          | **Jigyasu**                                                                        | **Sanskriti**                                                            | **Shivangi**                                                           |
| ------- | ---------- | ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| D1      | Mon 24 Aug | Repo init — monorepo structure, branch protection, CI skeleton (lint+test stub)                | Design tokens (colour/type/spacing) + Flutter theme setup                           | STT approach research (speech_to_text vs cloud); logo concepts x3                  | Diary set up + Day-1 entry; Settings/Profile wireframe (mock)            | Weekly-report template set up; Manual To-Do wireframe (mock)           |
| D2      | Tue 25 Aug | Supabase project + schema v1 (profiles, tasks, oauth_connections) + migrations                 | Navigation shell + routing skeleton, screen stubs for all pages                     | Logo v1 (3 concepts) shared for feedback                                           | Settings/Profile screen UI build (mock)                                  | Manual To-Do screen UI build (mock)                                    |
| D3      | Wed 26 Aug | FastAPI scaffold — config/env, health-check, Supabase connection                               | Onboarding/Splash screen UI (mock)                                                  | Sign Up screen UI (mock)                                                           | Memory/Preferences wireframe (mock)                                      | Daily/Weekly Digest wireframe (mock)                                   |
| D4      | Thu 27 Aug | Auth design decided (JWT session + OAuth2 for MCP scopes, documented); signup/login endpoints  | Home/Dashboard screen UI (mock task list)                                           | Sign In screen UI (mock)                                                           | Memory/Preferences screen UI build (mock)                                | Digest screen UI build (mock)                                          |
| D5      | Fri 28 Aug | JWT middleware (verify/refresh) + protected routes; draft RLS policies                         | Task Composer screen UI — text mode (mock)                                          | Forgot Password / OTP screen UI (mock)                                             | Golden-dataset format defined (input / expected / category)              | Weekly report #0 — kickoff notes + plan summary                        |
| D6      | Sat 29 Aug | CI runs pytest on every PR; Week-1 PR merge — repo + auth skeleton frozen                      | Design QA on auth screens; Week-1 review                                            | Logo direction finalised; Week-1 review                                            | Week-1 review; PR merge (6 diary entries logged)                         | Week-1 review; PR merge                                                |
| D7      | Mon 31 Aug | Google OAuth2 app registered (Calendar+Gmail scopes); consent-flow endpoint                    | Agent Plan View screen UI (mock)                                                    | Voice Input screen UI — mic + listening state (mock)                               | Golden dataset — 15 cases (planner/router category)                      | Manual To-Do — polish (add/complete/delete, mock)                      |
| D8      | Tue 1 Sep  | OAuth callback + token exchange + encrypted token storage live                                 | Approval Screen UI — risk card + approve/reject (mock)                              | Activity Log screen UI — filterable list (mock)                                    | Golden dataset — 15 cases (risk-explanation category)                    | Digest screen — polish (date-range picker, mock)                       |
| D9      | Wed 2 Sep  | Token-refresh job + 7-day Testing-mode expiry detection/flagging                               | OAuth Connections screen UI — 4 provider cards (mock)                               | speech_to_text package integrated — local mic capture POC                          | Settings/Profile — polish (dark mode, delete-account entry)              | Weekly report #1 — Week 1 progress compiled                            |
| D10     | Thu 3 Sep  | GitHub + Slack OAuth apps registered; token flow extended to both                              | Trust Dashboard UI — mock charts (latency/cost/accuracy)                            | Notifications screen UI — list view (mock)                                         | Memory/Preferences — polish (edit/delete preference)                     | Manual To-Do — empty/error states                                      |
| D11     | Fri 4 Sep  | tasks / task_plans / plan_steps tables live; POST /tasks endpoint                              | Notification-banner small model — spec + prompt draft                               | Logo final asset export (icon sizes, splash asset)                                 | Golden dataset — 10 cases (OAuth/edge-case category)                     | Digest — empty/error states                                            |
| D12     | Sat 5 Sep  | risk_rules table seeded; Week-2 PR merge — auth + OAuth layer frozen v1                        | Week-2 review; PR merge — core screen shells complete                               | Week-2 review; PR merge — auth + voice UI shells complete                          | Week-2 review; PR merge — 40 golden cases handed to Suraj                | Week-2 review; PR merge; weekly report #1 finalised                    |
| D13     | Mon 7 Sep  | LangGraph skeleton — intent-classify -> plan -> risk-tag nodes                                 | Wire Home/Dashboard to real GET /tasks                                              | Wire Sign Up / Sign In to real auth endpoints                                      | Wire Settings/Profile to real profile endpoint                           | Manual To-Do — local persistence (on-device store), fully standalone   |
| D14     | Tue 8 Sep  | MCP client — Google Calendar (create/list events)                                              | Wire Task Composer to real POST /tasks                                              | Activity Log — filter & search interactions (mock)                                 | Golden dataset — content review with Suraj (align to eval_cases schema)  | Digest screen — wire prep (payload contract agreed with Suraj)         |
| D15     | Wed 9 Sep  | MCP client — Gmail (draft/send, read)                                                          | Wire Agent Plan View to real task_plans/plan_steps data                             | Wire real transcription into Task Composer voice mode                              | Settings/Profile — final QA pass                                         | Weekly report #2 — Week 2 progress compiled                            |
| D16     | Thu 10 Sep | MCP client — GitHub (create issue/comment)                                                     | Wire Approval Screen to real approvals endpoint                                     | Voice Input error states — permission, timeout, retry                              | Assist Ishani — draft example risk-explanation copy                      | Manual To-Do — polish (local reminders, optional)                      |
| D17     | Fri 11 Sep | Approval-gate logic (fail-closed) + approvals table/endpoint                                   | Notification-banner model — first working version                                   | Firebase Cloud Messaging setup — device-token registration                         | Week-3 review prep                                                       | Week-3 review prep                                                     |
| D18     | Sat 12 Sep | LLM router (Groq primary / Gemini fallback) wired; Week-3 PR merge — orchestration core frozen | Week-3 review; PR merge — core loop UI wired end-to-end                             | Week-3 review; PR merge                                                            | Week-3 review; PR merge                                                  | Week-3 review; PR merge; weekly report #2 finalised                    |
| D19     | Mon 14 Sep | memory_embeddings + user_preferences tables; pgvector retrieval function                       | Coordinate notification-banner output into in-app banner (with Jigyasu)             | Notification banner UI component + tap-to-open handling                            | Wire Memory/Preferences to real user_preferences table                   | Digest screen wiring starts (payload mock finalised while job pending) |
| D20     | Tue 15 Sep | Notification trigger rules (event types + firing logic) documented for team                    | Banner copy rules per event type (with Suraj)                                       | In-app banner display logic — consumes event types + model output                  | Memory/Preferences — empty/error states                                  | Digest — placeholder states while backend job pending                  |
| D21     | Wed 16 Sep | llm_usage_logs + rate-limit backoff handling (Groq/Gemini free tier)                           | Wire OAuth Connections to real OAuth endpoints (Suraj's OAuth layer live since D12) | STT accuracy pass — accents / background-noise tuning                              | Golden dataset — notification-banner-text eval cases                     | Weekly report #3 — Week 3 progress compiled                            |
| D22     | Thu 17 Sep | execution_logs table + logging middleware on every step                                        | OAuth Connections — edge cases: revoke, re-auth, scope-mismatch states              | Wire Activity Log to real execution_logs                                           | Golden dataset — MCP-failure edge cases                                  | Digest screen — wire-to-real-table prep                                |
| D23     | Fri 18 Sep | digests table + scheduled daily/weekly digest-generation job                                   | Approval Screen edge cases — multi-step, rejected mid-flow                          | Notifications screen — payload contract agreed with Suraj                          | QA pass — Settings + Memory screens vs real data                         | Digest screen wired to real digests table (job live today)             |
| D24     | Sat 19 Sep | notifications table + push endpoint (FCM integration point); Week-4 PR merge                   | Week-4 review; PR merge                                                             | Wire Notifications list to real notifications/push endpoint; Week-4 PR merge       | Week-4 review; PR merge                                                  | Week-4 review; PR merge; weekly report #3 finalised                    |
| D25     | Mon 21 Sep | eval_cases / eval_runs tables; golden-dataset ingestion pipeline                               | Frontend test-suite setup (widget-test framework, golden-screen baseline)           | Widget tests — Auth screens, Voice Input                                           | Support Suraj — run golden dataset through eval pipeline, log mismatches | Widget tests — Manual To-Do, Digest screens                            |
| D26     | Tue 22 Sep | LLM eval suite v1 — planner + router accuracy tests running in CI                              | Widget tests — Onboarding, Home/Dashboard, Task Composer                            | STT test suite — accuracy benchmark vs reference transcripts                       | Golden dataset — regression cases from eval failures                     | Exploratory testing — Digest / Manual-To-Do edge cases                 |
| D27     | Wed 23 Sep | OAuth/JWT test suite — refresh, expiry, revoke, RLS-isolation tests                            | Widget tests — Plan View, Approval Screen (safety-critical)                         | Push-notification delivery test — FCM registration + reliability                   | Exploratory testing — sign-in / sign-up suite                            | Weekly report #4 draft — Week 4 progress                               |
| D28     | Thu 24 Sep | Sign-in/sign-up test suite — registration, duplicate email, reset, lockout                     | Widget tests — Activity Log                                                         | Bug fixes — OAuth/JWT test findings (client-side)                                  | Exploratory testing — MCP integration suite                              | Bug fixes — Digest / Manual-To-Do issues found                         |
| D29     | Fri 25 Sep | MCP integration test suite — connectivity, failure handling, idempotency                       | Notification-banner model — quality pass vs golden banner-text cases                | Bug fixes — sign-in/sign-up test findings                                          | Week-5 review prep                                                       | Week-5 review prep                                                     |
| D30     | Sat 26 Sep | Trust Dashboard metrics endpoint; Week-5 PR merge                                              | Trust Dashboard wired to real metrics; Week-5 review; PR merge                      | Week-5 review; PR merge                                                            | Week-5 review; PR merge                                                  | Week-5 review; PR merge; weekly report #4 finalised                    |
| D31     | Mon 28 Sep | Approval-gate bypass adversarial test (must never pass) + agent-loop e2e test                  | Support e2e test from UI side (approval-gate bypass)                                | Support e2e test — voice-input-to-task-completion flow                             | Support e2e testing — Settings/Memory flows                              | Support e2e testing — Digest / Manual-To-Do flows                      |
| D32     | Tue 29 Sep | Load test — concurrent users vs free-tier LLM/MCP limits, verify backoff                       | Support load test — observe UI under backend load/latency                           | Support load test — rapid voice-task submissions                                   | Support load test — observe/log results                                  | Support load test — observe/log results                                |
| D33     | Wed 30 Sep | Security/RLS audit across all tables; account-deletion cascade test                            | Accessibility + RLS-adjacent UI audit (no cross-user data ever renders)             | Logo/branding final polish (icons, splash, adaptive app-icon config, store assets) | Support RLS/security audit — manual checks, Settings/Memory              | Weekly report #5 draft — Week 5 progress                               |
| D34     | Thu 1 Oct  | Render deploy pipeline hardened — daily incremental auto-deploy from main                      | UI polish pass — spacing/empty/loading states, all screens                          | Notification UX polish — grouping, dismiss, deep-link correctness                  | Bug bash — file issues, Settings/Memory                                  | Bug bash — file issues, Digest/Manual-To-Do                            |
| D35     | Fri 2 Oct  | Full regression run (eval + auth + MCP + e2e); bug triage                                      | Full frontend regression pass; bug triage with Suraj                                | Regression pass — voice + notification flows                                       | Regression pass — Settings/Memory screens                                | Regression pass — Digest/Manual-To-Do screens                          |
| D36     | Sat 3 Oct  | Bug-fix day; Week-6 PR merge — release candidate cut                                           | Bug-fix day; Week-6 review; PR merge                                                | Bug-fix day; Week-6 review; PR merge                                               | Week-6 review; PR merge                                                  | Week-6 review; PR merge; weekly report #5 finalised                    |
| D37     | Mon 5 Oct  | Final smoke test on deployed Render build; backend freeze                                      | Final smoke test — full UI on deployed build                                        | Final smoke test — voice + notifications on deployed build                         | Final smoke test — Settings/Memory on deployed build                     | Final smoke test — Digest/Manual-To-Do on deployed build               |
| D38     | Tue 6 Oct  | Support frontend-backend integration fixes with team                                           | Fix last frontend-backend integration issues                                        | Demo script support — voice-input demo flow                                        | Compile golden-dataset + eval-results appendix content                   | Compile final report draft v1 (all 6 weekly reports merged)            |
| D39     | Wed 7 Oct  | Backend monitoring check during demo rehearsal                                                 | Demo rehearsal — UI walkthrough                                                     | Demo rehearsal — voice-input segment                                               | Demo rehearsal support; final diary compilation begins                   | Final report — review pass with Suraj/Ishani for accuracy              |
| D40     | Thu 8 Oct  | CI/CD + deployment appendix docs; usage/eval stats for report                                  | Screenshot/appendix assets for report                                               | Store-listing assets finalised for report appendix                                 | Final diary compilation handed to Shivangi                               | Final report — incorporate diary + appendix assets, near-final draft   |
| D41     | Fri 9 Oct  | Final PR merge freeze; tag v1.0; submission support                                            | Submission support                                                                  | Submission support                                                                 | Submission support                                                       | Final report submitted — project submission complete                   |

# **15\. Testing, QA & Fallback Strategy**

| **Layer**                        | **Owner**                                                | **Covers**                                                                                                                                                              | **Tooling**                                              |
| -------------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| LLM Evaluation Suite             | Suraj (pipeline) + Sanskriti & Shivangi (golden dataset) | Planner accuracy, router accuracy, risk-explanation quality, hallucination/grounding checks, prompt-change regression                                                   | pytest + custom eval harness, cases stored in eval_cases |
| OAuth & JWT Tests                | Suraj                                                    | Token refresh, 7-day Testing-mode expiry, revoke handling, scope mismatch, RLS isolation                                                                                | pytest against a Supabase test project                   |
| Sign-in / Sign-up Tests          | Suraj (backend) + Jigyasu (client)                       | Registration, duplicate email, password strength, email verification, login, brute-force lockout, password reset, session persistence, logout, account-deletion cascade | pytest + flutter integration_test                        |
| MCP Integration Tests            | Suraj                                                    | Per-server connectivity, tool-call success/failure, timeout handling, idempotency (no double-creates on retry)                                                          | pytest against MCP sandbox/mock servers                  |
| Agent-Loop / Approval-Gate Tests | Suraj + Ishani                                           | Full task flow end-to-end; approval-gate bypass adversarial test (must always fail closed); low-risk auto-execute path; mixed-risk multi-step ordering                  | pytest + LangGraph test harness                          |
| Frontend Widget Tests            | Ishani, with each owner testing their own screens        | Every screen renders correctly; Approval Screen and Plan View must never mis-render (safety-critical)                                                                   | flutter test — widget + golden tests                     |
| Security / RLS Tests             | Suraj                                                    | Cross-user data isolation on all 17 tables, token encryption at rest, no plaintext secrets in logs                                                                      | pytest + manual audit pass (D33)                         |
| Load / Performance Tests         | Suraj, team observes/logs                                | Concurrent-user simulation against Groq/Gemini free-tier limits, Render cold-start behaviour                                                                            | lightweight async load script                            |

_The approval-gate bypass test (row 5) is non-negotiable — see acceptance criterion A2. A single failing run blocks the release candidate regardless of what else is green._

## **15.1 LLM Evaluation Pipeline**

The eval pipeline is a closed loop, not a one-off script: Sanskriti and Shivangi author cases into eval_cases (input_prompt, expected_output, category); Suraj's harness replays every case against the current planner/router/explainer/banner models on each CI run; results land in eval_runs (pass_count, fail_count, avg_latency_ms) and feed the Trust Dashboard directly. A prompt or graph change that regresses a previously-passing case is caught by test_eval_suite_regression_no_new_failures_vs_last_frozen_run before it can merge — the frozen run is the last green eval_runs row on main.

| **File**                    | **Named tests**                                                                                                                               |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| test_planner_eval.py        | test_planner_produces_valid_plan_json, test_planner_step_count_within_golden_expected_range, test_planner_selects_correct_mcp_server_per_step |
| test_router_eval.py         | test_router_intent_classification_accuracy, test_router_confidence_threshold_gating, test_llm_router_falls_back_to_gemini_on_groq_429         |
| test_risk_explainer_eval.py | test_risk_explainer_no_false_claims_about_the_action, test_risk_explainer_tone_is_non_alarming                                                |
| test_banner_model_eval.py   | test_banner_model_output_length_under_limit, test_banner_model_matches_triggering_event_type                                                  |
| (suite-wide)                | test_eval_suite_regression_no_new_failures_vs_last_frozen_run                                                                                 |

## **15.2 Flutter Widget Testing**

Every screen gets at least render + basic-interaction coverage; the Approval Screen and Plan View additionally get golden-file tests (a pixel-level reference image), since those two screens are the ones a user's trust in the whole system rests on — a silent mis-render there is a safety bug, not a cosmetic one. Coverage floor: 80% overall, 100% on those two screens (Acceptance A7).

| **File**                                    | **Named tests**                                                                                       |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| approval_screen_test.dart                   | test_approval_screen_renders_risk_explanation (golden test), test_approval_screen_never_auto_approves |
| plan_view_test.dart                         | test_plan_view_renders_all_steps_in_order                                                             |
| oauth_connections_test.dart                 | test_oauth_connections_shows_correct_connect_state_per_provider                                       |
| activity_log_test.dart                      | test_activity_log_filters_by_date_and_type                                                            |
| voice_input_test.dart                       | test_voice_input_shows_listening_state                                                                |
| settings_test.dart / memory_prefs_test.dart | test_settings_delete_account_requires_confirmation, test_memory_prefs_edit_updates_value              |
| manual_todo_test.dart / digest_test.dart    | test_manual_todo_add_complete_delete, test_digest_renders_empty_state_when_no_tasks                   |

## **15.3 STT Accuracy Suite**

Jigyasu benchmarks the speech_to_text integration against a reference transcript set covering multiple accents and three background-noise conditions (quiet, moderate ambient, loud), measuring word-error rate (WER) per condition rather than a single blended number — a system that is accurate in a quiet room but unusable outdoors would pass a blended average and still fail real usage. Results are tracked per condition across D9, D21, and D26 (STT integration → accuracy tuning → formal benchmark) so drift is visible before Week 6 hardening.

## **15.4 Named Tests — Remaining Suites**

| **Suite**                                                             | **Named tests**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| OAuth & JWT (test_oauth.py, test_jwt.py)                              | test_jwt_valid_token_accepted, test_jwt_expired_token_rejected, test_jwt_refresh_issues_new_access_token, test_jwt_tampered_signature_rejected, test_oauth_google_consent_redirect_has_correct_scopes, test_oauth_callback_exchanges_code_for_token, test_oauth_token_encrypted_at_rest, test_oauth_token_refresh_before_expiry, test_oauth_7day_testing_mode_expiry_is_flagged, test_oauth_revoked_access_returns_clean_error, test_oauth_scope_mismatch_disables_feature_gracefully                                                                                                                              |
| Sign-in / Sign-up (test_signup_signin.py + Flutter)                   | test_signup_valid_credentials_creates_account, test_signup_duplicate_email_rejected, test_signup_weak_password_rejected, test_signup_sends_verification_email, test_email_verification_link_activates_account, test_email_verification_expired_link_can_resend, test_login_correct_credentials_succeeds, test_login_incorrect_password_rejected, test_login_lockout_after_5_failed_attempts, test_forgot_password_sends_reset_email, test_reset_password_invalidates_old_sessions, test_session_persists_across_app_restart, test_logout_clears_local_session, test_account_deletion_cascades_across_all_17_tables |
| MCP Integration (test_mcp_\*.py)                                      | test_calendar_create_event_success, test_calendar_list_events_returns_expected_range, test_calendar_invalid_params_returns_clear_error, test_gmail_draft_email_success, test_gmail_send_respects_approval_gate, test_github_create_issue_success, test_github_retry_is_idempotent_no_double_create, test_mcp_server_timeout_handled_gracefully, test_mcp_server_down_marks_task_failed_not_hung                                                                                                                                                                                                                    |
| Agent-Loop / Approval-Gate (test_approval_gate.py, test_agent_e2e.py) | test_low_risk_action_auto_executes_without_approval, test_high_risk_action_blocks_pending_approval, test_approval_gate_bypass_attempt_always_fails, test_rejected_approval_halts_task_with_no_side_effects, test_mixed_risk_multi_step_plan_orders_correctly, test_task_resumes_after_app_closed_mid_approval, test_e2e_text_task_completes_full_loop, test_e2e_voice_task_completes_full_loop                                                                                                                                                                                                                     |
| Security / RLS (test_rls_security.py)                                 | test_rls_user_cannot_read_other_users_tasks, test_rls_user_cannot_read_other_users_oauth_tokens, test_rls_user_cannot_read_other_users_memory, test_rls_service_role_tables_not_exposed_to_client, test_tokens_never_logged_in_plaintext, test_account_deletion_removes_all_17_tables                                                                                                                                                                                                                                                                                                                              |
| Load / Performance (test_concurrent_tasks.py)                         | test_50_concurrent_users_no_5xx_errors, test_groq_rate_limit_triggers_gemini_fallback_under_load, test_render_cold_start_shows_loading_state_not_error                                                                                                                                                                                                                                                                                                                                                                                                                                                             |

# **16\. Daily Diary & Weekly Report Templates**

## **16.1 Sanskriti — Daily Diary**

One entry per working day, in docs/diary/, filename YYYY-MM-DD.md. Kept short — 5–10 lines is enough; the point is a continuous record, not a polished write-up.

\## &lt;Date&gt; — Day N

Planned: ...

Actually did: ... (PRs, files, tests — be specific)

Blockers: ...

What's next: ...

_Example, filled:_

\## 2026-09-02 — Day 10

Planned: Memory/Preferences UI polish (edit/delete preference)

Actually did: PR #41 merged; edit + delete flows working; 4 widget tests green

Blockers: none

What's next: empty/error states for Memory/Preferences (D20)

## **16.2 Shivangi — Weekly Report**

Six reports total — kickoff notes (#0) plus one report per week for Weeks 1–5 — in docs/reports/, due every Saturday alongside the PR-merge review. Weeks 6 and 7 are not given their own standalone weekly report; their progress is written directly into the final report (D38–D40).

- Week number & dates
- Goals for the week vs. what actually shipped
- Screens/features completed
- Test results summary
- Risks or slippage
- Plan for next week

The six weekly reports get merged into one final report during Week 7 (D38–D40), so the report is never a last-minute scramble — it has been written incrementally the whole time.

## **16.3 Definition of Done (applies to every day-plan task in Section 14)**

- Code merged to main via a reviewed PR — not just "works on my machine."
- Tests exist and pass (pytest / flutter test / SQL RLS tests as applicable); linters clean.
- Fail-closed / fail-open behaviour verified where the task touches a user-facing or risk-relevant path.
- Logging present in execution_logs if the task is on the agent loop or the LLM cost path.
- One paragraph of docs (README or module doc) written the same day.

# **17\. Checklists (Phase Gates)**

## **Gate 1 — End of Week 2 (5 Sep): Auth + OAuth layer frozen**

| **Owner** | **Item**                                                            |
| --------- | ------------------------------------------------------------------- |
| Suraj     | Signup/login + JWT middleware merged and covered by tests           |
| Suraj     | Google, GitHub, Slack OAuth apps registered; token exchange working |
| Ishani    | All 7 core screen shells exist (even against mock data)             |
| Jigyasu   | Auth screens + Voice Input screen shells exist                      |
| Sanskriti | 40 golden test cases delivered to Suraj                             |
| Shivangi  | Weekly report #1 delivered                                          |

## **Gate 2 — End of Week 4 (19 Sep): Core loop + notifications live**

| **Owner** | **Item**                                                                                       |
| --------- | ---------------------------------------------------------------------------------------------- |
| Suraj     | Planner, MCP clients, approval gate, notifications table all merged                            |
| Ishani    | Home, Composer, Plan View, Approval Screen, OAuth Connections wired to real data               |
| Jigyasu   | Voice input working end-to-end; notification banner rendering; Activity Log wired to real data |
| Sanskriti | Memory/Preferences wired; notification-banner eval cases delivered                             |
| Shivangi  | Digest screen wired; weekly report #3 delivered                                                |

## **Gate 3 — End of Week 5 (26 Sep): Test suites running in CI**

| **Owner**            | **Item**                                                           |
| -------------------- | ------------------------------------------------------------------ |
| Suraj                | LLM eval, OAuth/JWT, sign-in/sign-up, MCP suites all running in CI |
| Ishani               | Widget tests written for every screen; Trust Dashboard wired       |
| Jigyasu              | STT + push-notification test suites passing                        |
| Sanskriti / Shivangi | Exploratory pass complete on every screen; bugs filed              |

## **Gate 4 — End of Week 6 (3 Oct): Release candidate**

| **Owner**            | **Item**                                                                    |
| -------------------- | --------------------------------------------------------------------------- |
| Suraj                | Full regression green; Render auto-deploy stable; RLS/security audit closed |
| Ishani               | UI polish complete; zero P0/P1 bugs open on core screens                    |
| Jigyasu              | Logo/branding final; notification UX polish done                            |
| Sanskriti / Shivangi | Bug bash complete; weekly report #5 delivered                               |

## **Gate 5 — 9 Oct: Submission**

| **Owner** | **Item**                                                   |
| --------- | ---------------------------------------------------------- |
| Suraj     | v1.0 tagged; backend frozen; deployment docs in appendix   |
| Ishani    | Demo walkthrough rehearsed                                 |
| Jigyasu   | Voice-input demo segment rehearsed; store assets finalised |
| Sanskriti | Full diary handed off                                      |
| Shivangi  | Final report submitted                                     |

# **18\. Acceptance Criteria**

| **ID** | **Criterion**                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1     | Planner produces a valid, executable plan for at least 90% of golden-dataset task inputs.                                                                                                                                                                                                                                                                                                                                         |
| A2     | Every action tagged high-risk is blocked pending approval in 100% of adversarial bypass-test runs — zero tolerance.                                                                                                                                                                                                                                                                                                               |
| A3     | OAuth token refresh succeeds automatically in at least 95% of expiry-simulation runs; failures surface a clear re-auth prompt, never a silent failure.                                                                                                                                                                                                                                                                            |
| A4     | A first-time user can go from sign-up to first completed task in under 3 minutes in usability testing.                                                                                                                                                                                                                                                                                                                            |
| A5     | All 17 database tables have row-level security enabled: the 12 user-scoped tables enforce owner-only access via user_id = auth.uid() policies, and the 5 service-role-only tables (risk_rules, llm_usage_logs, eval_cases, eval_runs, mcp_server_registry) have RLS enabled with no client-facing policy, so only the backend's service-role key can read or write them. Cross-user data leakage found in the security audit = 0. |
| A6     | p95 end-to-end latency for a simple, low-risk, auto-executed task is under 8 seconds.                                                                                                                                                                                                                                                                                                                                             |
| A7     | Widget-test coverage is at least 80% of screens overall, and 100% for the Approval Screen and Plan View.                                                                                                                                                                                                                                                                                                                          |
| A8     | A diary entry exists for at least 90% of working days; a weekly report is delivered every week without a gap.                                                                                                                                                                                                                                                                                                                     |
| A9     | CI blocks merge on any failing test or lint error; zero direct pushes to main across the whole project.                                                                                                                                                                                                                                                                                                                           |
| A10    | Render deployment succeeds with zero manual intervention for at least 90% of merges in the final two weeks.                                                                                                                                                                                                                                                                                                                       |

# **19\. Risk Register & Fallbacks**

Every row follows the same shape: if the risk in column one materializes, the fallback in column four is what happens next — pre-agreed now, not debated mid-sprint.

| **Risk**                                                              | **Prob.** | **Impact** | **If it happens, then… (fallback)**                                                                                                                                                                                                                                      |
| --------------------------------------------------------------------- | --------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Groq/Gemini free-tier rate limit hit mid-demo                         | Med       | High       | ...then the LLM router (Section 8.4) has already failed over to the secondary provider automatically since D18; if both are saturated, cached responses from the demo script serve the walkthrough and the UI shows a graceful degradation message — never a hard crash. |
| Google OAuth Testing-mode 7-day token expiry breaks the demo          | Med       | High       | ...then the automated re-auth reminder built on D9 has already flagged it days in advance; a fresh consent pass is scheduled the morning of the D39 rehearsal regardless, so the demo account's tokens are never more than a day old.                                    |
| Render free-tier cold start causes visible lag in front of evaluators | Med       | Medium     | ...then the pre-scheduled warm-up ping job (fired 10 minutes before the demo slot, Section 2.3) has already brought the instance up; the Flutter client additionally shows an explicit loading state rather than an unexplained delay.                                   |
| LangGraph/MCP integration bugs surface late                           | Low       | Medium     | ...then Week 6 absorbs it — it is deliberately kept as an integration/hardening buffer with no new-feature work scheduled, so a late bug has a week of slack rather than zero.                                                                                           |
| A team member is unavailable (exams/illness) during a critical week   | Med       | Medium     | ...then Suraj and Ishani, who are cross-briefed on every critical-path item, cover the gap; Weeks 6–7 carry slack specifically for this scenario.                                                                                                                        |
| Play Store review delay if a public listing is pursued                | Low       | Low        | ...then the primary demo path stays Firebase App Distribution / direct APK install, which was never gated on Play Store approval in the first place.                                                                                                                     |
| Scope creep — OCR gets pulled back in mid-project                     | Low       | Low        | ...then it is redirected to the explicitly parked backlog item in Section 2.2/2.4; it is revisited only after all ten acceptance criteria in Section 18 pass, never mid-sprint.                                                                                          |
| Approval-gate bypass test fails at Gate 4                             | Low       | High       | ...then the release candidate is blocked outright, regardless of every other test's status (Section 15) — there is no override for this specific failure.                                                                                                                |
| Supabase free-tier project pauses from inactivity over a break        | Low       | Medium     | ...then daily incremental deploys and daily team activity (Section 2.3) keep the project active by construction; if it still pauses, a five-minute Supabase dashboard resume is the documented recovery step, done before the next working day starts.                   |

# **20\. Appendices**

## **Appendix A — backend/.env.example**

SUPABASE_URL=

SUPABASE_SERVICE_ROLE_KEY=

SUPABASE_JWT_SECRET=

GROQ_API_KEY=

GEMINI_API_KEY=

GOOGLE_OAUTH_CLIENT_ID=

GOOGLE_OAUTH_CLIENT_SECRET=

GITHUB_OAUTH_CLIENT_ID=

GITHUB_OAUTH_CLIENT_SECRET=

SLACK_CLIENT_ID=

SLACK_CLIENT_SECRET=

FCM_SERVER_KEY=

RENDER_DEPLOY_HOOK_URL=

## **Appendix B — CLI Cheat Sheet**

\# Backend

uvicorn app.main:app --reload

pytest app/tests -v

pytest app/tests/eval -v # LLM eval suite only

supabase db push # run migrations

\# Mobile

flutter run

flutter test

## **Appendix C — Glossary**

| **Term**       | **Definition**                                                                                     |
| -------------- | -------------------------------------------------------------------------------------------------- |
| MCP            | Model Context Protocol — the standard the agent uses to call Calendar/Gmail/GitHub/Slack.          |
| LangGraph      | The framework used to build the planner as an explicit state graph rather than a single prompt.    |
| RLS            | Row-Level Security — Postgres policies that keep one user's data invisible to another.             |
| JWT            | JSON Web Token — the signed session token issued by Supabase Auth.                                 |
| OAuth2         | The authorization-code flow used to connect third-party accounts (Calendar, Gmail, GitHub, Slack). |
| pgvector       | Postgres extension used for storing and searching memory embeddings.                               |
| Risk tier      | A hardcoded label (low/medium/high) on a possible action that decides if it needs approval.        |
| Golden dataset | Sanskriti/Shivangi's frozen set of test cases used to grade the LLM eval suite.                    |
| Approval gate  | The point in the pipeline where a high-risk step stops and waits for the user.                     |
| Fail-closed    | The default-deny posture: an action with no matching rule is treated as high risk, never as safe.  |
| Checkpointer   | LangGraph's mechanism for persisting graph state so a paused task resumes without re-planning.     |

## **Appendix D — Key Files by Owner**

| **Owner** | **File**                                                            | **Purpose**                                  |
| --------- | ------------------------------------------------------------------- | -------------------------------------------- |
| Suraj     | backend/app/main.py                                                 | FastAPI entrypoint                           |
| Suraj     | backend/app/core/security.py                                        | JWT verify/refresh dependency                |
| Suraj     | backend/app/core/config.py                                          | Env/config loader                            |
| Suraj     | backend/app/api/auth.py                                             | Signup, login, reset routes                  |
| Suraj     | backend/app/api/oauth.py                                            | OAuth consent + callback routes              |
| Suraj     | backend/app/api/tasks.py                                            | POST/GET /tasks routes                       |
| Suraj     | backend/app/agents/graph.py                                         | LangGraph StateGraph definition              |
| Suraj     | backend/app/agents/nodes.py                                         | Intent / plan / risk-tag / execute nodes     |
| Suraj     | backend/app/mcp_clients/\*.py                                       | Calendar, Gmail, GitHub, Slack clients       |
| Suraj     | backend/app/llm/router.py                                           | Groq primary / Gemini fallback routing       |
| Suraj     | backend/app/risk/risk_rules.py                                      | Hardcoded risk-tier table                    |
| Suraj     | backend/app/risk/approval_gate.py                                   | Fail-closed approval enforcement             |
| Suraj     | backend/app/notifications/trigger_rules.py                          | Notification event types + firing logic      |
| Suraj     | backend/migrations/\*.sql                                           | All 17 tables + RLS policies                 |
| Suraj     | .github/workflows/ci.yml + deploy.yml                               | CI checks + Render auto-deploy               |
| Ishani    | mobile/lib/core/theme.dart                                          | Design tokens — colour, type, spacing        |
| Ishani    | mobile/lib/core/router.dart                                         | Navigation shell                             |
| Ishani    | mobile/lib/features/home/home_screen.dart                           | Home / Dashboard                             |
| Ishani    | mobile/lib/features/task_composer/task_composer_screen.dart         | Task Composer                                |
| Ishani    | mobile/lib/features/plan_view/plan_view_screen.dart                 | Agent Plan View                              |
| Ishani    | mobile/lib/features/approval/approval_screen.dart                   | Approval Screen (safety-critical)            |
| Ishani    | mobile/lib/features/oauth_connections/oauth_connections_screen.dart | OAuth Connections                            |
| Ishani    | mobile/lib/features/trust_dashboard/trust_dashboard_screen.dart     | Trust Dashboard                              |
| Ishani    | backend/app/notifications/banner_model.py                           | Small LLM model — notification-banner copy   |
| Jigyasu   | mobile/lib/features/auth/signup_screen.dart                         | Sign Up                                      |
| Jigyasu   | mobile/lib/features/auth/signin_screen.dart                         | Sign In                                      |
| Jigyasu   | mobile/lib/features/auth/forgot_password_screen.dart                | Forgot Password / OTP                        |
| Jigyasu   | mobile/lib/features/voice_input/voice_input_screen.dart             | Voice Input                                  |
| Jigyasu   | mobile/lib/features/voice_input/stt_service.dart                    | speech_to_text integration                   |
| Jigyasu   | mobile/lib/features/activity_log/activity_log_screen.dart           | Activity Log / Audit Trail                   |
| Jigyasu   | mobile/lib/features/notifications/notifications_screen.dart         | Notifications list                           |
| Jigyasu   | mobile/lib/features/notifications/banner_widget.dart                | In-app banner + tap-to-open                  |
| Jigyasu   | mobile/assets/logo/                                                 | App logo + icon assets                       |
| Sanskriti | mobile/lib/features/settings/settings_screen.dart                   | Settings / Profile                           |
| Sanskriti | mobile/lib/features/memory_prefs/memory_prefs_screen.dart           | Memory / Preferences                         |
| Sanskriti | docs/diary/YYYY-MM-DD.md                                            | One diary entry per working day              |
| Sanskriti | docs/eval/golden_dataset.jsonl                                      | Golden test cases for Suraj + Ishani's evals |
| Shivangi  | mobile/lib/features/manual_todo/manual_todo_screen.dart             | Manual To-Do Fallback                        |
| Shivangi  | mobile/lib/features/digest/digest_screen.dart                       | Daily / Weekly Digest                        |
| Shivangi  | docs/reports/week-00.md ... week-05.md                              | Weekly reports                               |
| Shivangi  | docs/reports/final_report.md                                        | Final report, compiled Week 7                |

## **Appendix E — MCP Capability Quick Reference**

| **Server** | **Tools**                                                              | **Default risk range** |
| ---------- | ---------------------------------------------------------------------- | ---------------------- |
| Calendar   | list_events, find_free_slots, create_event, update_event, delete_event | low → high             |
| Gmail      | list_messages, get_message, create_draft, send_message                 | low → high             |
| GitHub     | list_issues, create_issue, comment_on_issue, create_pr_comment         | low → medium           |
| Slack      | list_channels, post_message, add_reaction                              | low → high             |

**— End of Document —**

_AgentOps Copilot Technical Implementation Manual · Version 2.0 · 22 August 2026_