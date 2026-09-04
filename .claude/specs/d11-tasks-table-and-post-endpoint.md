# Tasks Table, task_plans, plan_steps & POST /tasks Endpoint — Technical Spec

**Project:** AgentOps Copilot
**Plan reference:** D11 — "tasks / task_plans / plan_steps tables live; POST /tasks endpoint"
**Owner / track:** Suraj — backend
**Branch:** `feature/tasks-table`
**Files:**
- `backend/migrations/20260904000007_create_task_plans_plan_steps.sql` (new)
- `backend/app/api/routers/tasks.py` (replace stub)
**Status going into this spec:** The `tasks` table already exists (D2 migration). `tasks.py` is a stub returning an empty list (built in D5 purely for JWT middleware testing). The LangGraph planner does not exist yet (D13). This spec creates the remaining DB tables and a real `POST /tasks` endpoint that accepts input, writes a `tasks` row, and returns the new task — wiring to the planner happens on D13.

---

## 1. Objective

1. **DB Layer:** Create `task_plans` and `plan_steps` tables with correct foreign keys, RLS, and indices. The `tasks` table already exists and does not need to be recreated.
2. **POST /tasks:** Replace the current stub with a real endpoint that accepts a user''s text or voice task, validates input, writes a row to `tasks`, and returns the created task object. The LangGraph orchestration is **not** wired in yet — the endpoint writes status `''submitted''` and returns immediately. The planner picks this up on D13.
3. **GET /tasks:** Promote the stub `GET /tasks` to return real rows from Supabase for the current user (paginated).
4. **GET /tasks/{id}:** Add a task-detail endpoint returning the full task row.

---

## 2. Endpoints

### 2.1 POST /tasks

| | |
|---|---|
| **Method** | `POST` |
| **Path** | `/tasks` |
| **Auth** | JWT required |
| **Purpose** | Submit a new task (text or voice) |

**Request body (JSON):**

```json
{
  "input_type": "text",
  "raw_input": "Schedule a call with my professor for Thursday afternoon and email him the agenda.",
  "transcription_text": null
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `input_type` | string | Yes | `"text"` or `"voice"` |
| `raw_input` | string | Conditional | Required when `input_type = "text"`. Max 5000 chars. |
| `transcription_text` | string | Conditional | Required when `input_type = "voice"`. Max 5000 chars. Populated by the Flutter STT client before the API call. |

**Response (201 Created):**

```json
{
  "id": "<uuid>",
  "user_id": "<uuid>",
  "input_type": "text",
  "raw_input": "Schedule a call...",
  "transcription_text": null,
  "status": "submitted",
  "created_at": "2026-09-04T07:00:00Z",
  "completed_at": null
}
```

---

### 2.2 GET /tasks

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tasks` |
| **Auth** | JWT required |
| **Purpose** | List the authenticated user''s tasks, newest-first |

**Query params:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `limit` | int | 20 | Max 100 |
| `offset` | int | 0 | For pagination |
| `status` | string | — | Optional filter: one of the valid status values |

**Response (200 OK):**

```json
{
  "tasks": [ ... ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

### 2.3 GET /tasks/{id}

| | |
|---|---|
| **Method** | `GET` |
| **Path** | `/tasks/{id}` |
| **Auth** | JWT required |
| **Purpose** | Single task detail |

Returns the full task row. Returns `404` if the task does not exist or belongs to a different user (RLS enforces this; the backend returns `404` rather than `403` to avoid leaking task existence).

---

## 3. Database — New Tables

The `tasks` table already exists from D2. Two new tables are introduced in this migration.

### 3.1 task_plans

LangGraph planner output for a task — one plan per task (re-planning creates a new row, not an overwrite).

| Column | Type / Constraints | Notes |
|---|---|---|
| `id` | uuid, PK, DEFAULT gen_random_uuid() | |
| `task_id` | uuid, FK tasks(id) ON DELETE CASCADE | |
| `planner_version` | text | Prompt/graph version tag for regression tracking |
| `plan_json` | jsonb, NOT NULL | Ordered step list as produced by the planner node |
| `status` | text, DEFAULT `''draft''` | `draft` or `active` or `superseded` |
| `created_at` | timestamptz, DEFAULT now() | |

**RLS policy:** Read via join `task_plans.task_id → tasks.user_id = auth.uid()`. INSERT restricted to service role (the planner writes plans, not the user directly).

---

### 3.2 plan_steps

Individual tool-call steps within a plan — the unit that the risk gate and MCP layer operate on.

| Column | Type / Constraints | Notes |
|---|---|---|
| `id` | uuid, PK, DEFAULT gen_random_uuid() | |
| `plan_id` | uuid, FK task_plans(id) ON DELETE CASCADE | |
| `step_index` | int, NOT NULL | Execution order within the plan |
| `tool_name` | text, NOT NULL | e.g. `calendar.create_event` |
| `mcp_server` | text, NOT NULL | `calendar` or `gmail` or `github` or `slack` |
| `input_params` | jsonb, NOT NULL | |
| `risk_tier` | text, NOT NULL | `low` or `medium` or `high` (assigned by risk_rules lookup) |
| `requires_approval` | boolean, NOT NULL | |
| `status` | text, DEFAULT `''pending''` | `pending` or `awaiting_approval` or `approved` or `rejected` or `executing` or `done` or `failed` |
| `output` | jsonb | Tool call result once executed |
| `executed_at` | timestamptz | |

**RLS policy:** Read via join `plan_steps.plan_id → task_plans.task_id → tasks.user_id = auth.uid()`. INSERT/UPDATE restricted to service role.

---

## 4. Implementation Steps

### 4.1 Migration

Create `backend/migrations/20260904000007_create_task_plans_plan_steps.sql`:

1. Create `task_plans` with FK to `tasks`, CHECK on `status`.
2. Create index on `task_plans(task_id)`.
3. Enable RLS on `task_plans`; add SELECT policy via task join; **no** INSERT/UPDATE policy for the user role (service-role only).
4. Create `plan_steps` with FK to `task_plans`, CHECK on `mcp_server` and `status`.
5. Create index on `plan_steps(plan_id)`.
6. Enable RLS on `plan_steps`; add SELECT policy via double join; service-role only for writes.

Migration must be idempotent (`CREATE TABLE IF NOT EXISTS`, `DROP POLICY IF EXISTS` + re-create).

---

### 4.2 Pydantic Schemas

Add `TaskCreate`, `TaskOut`, `TaskListOut` schemas in `backend/app/api/routers/tasks.py`:

```python
class TaskCreate(BaseModel):
    input_type: Literal["text", "voice"]
    raw_input: str | None = Field(None, max_length=5000)
    transcription_text: str | None = Field(None, max_length=5000)

    @model_validator(mode="after")
    def check_input_present(self) -> "TaskCreate":
        if self.input_type == "text" and not self.raw_input:
            raise ValueError("raw_input required for text tasks")
        if self.input_type == "voice" and not self.transcription_text:
            raise ValueError("transcription_text required for voice tasks")
        return self

class TaskOut(BaseModel):
    id: UUID
    user_id: UUID
    input_type: str
    raw_input: str | None
    transcription_text: str | None
    status: str
    created_at: datetime
    completed_at: datetime | None
```

---

### 4.3 POST /tasks Handler

```
POST /tasks
  1. get_current_user → user_id
  2. Validate body → TaskCreate
  3. supabase_client (user-JWT forwarded) INSERT into tasks:
       { user_id, input_type, raw_input, transcription_text, status=''submitted'' }
  4. Return TaskOut with 201 Created
```

**Client selection:** Use the **user-JWT-forwarded** Supabase client (not service role) so RLS enforces `user_id = auth.uid()` at the DB level.

---

### 4.4 GET /tasks Handler

Replace the stub:
- Query `tasks` table (RLS scopes to current user automatically).
- Apply `status` filter if provided.
- Order by `created_at DESC`.
- Apply `limit` / `offset`.
- Return count + list.

---

### 4.5 GET /tasks/{id} Handler

- Query `tasks` WHERE `id = :id`.
- RLS automatically scopes to the current user.
- Return `404` if no row returned.

---

## 5. Config / Env

No new environment variables required for this day. Re-uses:
- `SUPABASE_URL` / `SUPABASE_ANON_KEY` — for user-scoped reads/inserts.
- `SUPABASE_SERVICE_ROLE_KEY` — reserved for the planner (D13); not used by this endpoint.

---

## 6. Security Notes

- **RLS is the primary gate.** The `tasks` table already has user-scoped RLS policies. The `task_plans` and `plan_steps` tables add join-based SELECT policies; their write path is service-role only.
- **No service-role key in the POST /tasks handler.** The user''s JWT is forwarded to Supabase so the DB enforces that `user_id` matches the authenticated caller.
- **Input sanitisation.** `raw_input` and `transcription_text` are stored as user-provided text and are never interpreted as code or SQL. Max-length validation (5000 chars) guards against oversized payloads.

---

## 7. Error Handling

| Case | Response |
|---|---|
| No/invalid JWT | 401 Unauthorized |
| `input_type = "text"` with no `raw_input` | 422 Unprocessable Entity |
| `input_type = "voice"` with no `transcription_text` | 422 Unprocessable Entity |
| `input_type` is not `"text"` or `"voice"` | 422 Unprocessable Entity |
| Supabase insert fails (DB error) | 500 with logged error; no partial state |
| `GET /tasks/{id}` — task not found or not owned by caller | 404 Not Found |

---

## 8. Out of Scope for D11

- LangGraph planner invocation (D13) — the task is written with `status=''submitted''` and stays there until D13 picks it up.
- `GET /tasks/{id}/plan` endpoint — requires `task_plans` data; wired in D13.
- `risk_rules` table seeding (D12).
- Approval flow (`POST /approvals/{step_id}`) — D17.
- Notifications triggered on task state changes — D20/D24.

---

## 9. Acceptance / Test Criteria

- `test_post_tasks_creates_task_for_authenticated_user`: POST with valid JWT and `input_type=text` returns 201 and a `tasks` row is present in the DB with `status=''submitted''` and the correct `user_id`.
- `test_post_tasks_requires_raw_input_for_text_type`: POST with `input_type=text` and no `raw_input` returns 422.
- `test_post_tasks_requires_transcription_for_voice_type`: POST with `input_type=voice` and no `transcription_text` returns 422.
- `test_post_tasks_rejects_unauthenticated_request`: POST without a JWT returns 401.
- `test_get_tasks_returns_only_current_users_tasks`: Two test users each submit a task; `GET /tasks` for user A returns only user A''s tasks (RLS isolation).
- `test_get_tasks_id_returns_404_for_other_users_task`: User A cannot fetch user B''s task by ID.
- `test_task_plans_rls_service_role_only_write`: Inserting a `task_plans` row with the anon/user role is rejected by RLS; inserting with the service-role key succeeds.

---

## 10. Dependencies

- D2 complete (`tasks` table exists).
- D5 complete (`get_current_user` JWT dependency available in `app.core.security`).
- D8 complete (Supabase client patterns for user-JWT forwarding established in `oauth.py`).
