# Notifications Table + Push Endpoint (FCM Integration) — Technical Spec

**Project:** AgentOps Copilot
**Plan reference:** D24 — "notifications table + push endpoint (FCM integration point); Week-4 PR merge"
**Owner / track:** Suraj — backend
**Branch:** `feature/d24-notifications-push`
**Date:** Sat 19 Sep 2026 (Week 4 close — Gate 2)
**Files:**
- `backend/migrations/20260919000019_create_notifications.sql` (new)
- `backend/migrations/20260919000020_create_sessions_device_tokens.sql` (new)
- `backend/app/notifications/fcm.py` (new)
- `backend/app/api/routers/notifications.py` (new)
- `backend/app/main.py` (modify — register notifications router)
- `backend/app/core/config.py` (modify — add `FIREBASE_SERVICE_ACCOUNT_PATH`)
- `backend/app/tests/test_notifications.py` (new)

**Status going into this spec:**
- `trigger_rules.py` — ✅ done (D20): `NotificationEvent` enum + `evaluate_trigger()` defined
- `banner_model.py` — ✅ done (D17/D11): LLM banner-text generation function live
- `digests.py` router — ✅ done (D23): structural reference for this router
- `notifications` and `sessions_device_tokens` tables — **not yet created** (this day)
- FCM push send function — **not yet created** (this day)
- `GET /notifications` and `POST /notifications/{id}/read` endpoints — **not yet created** (this day)

D24 is also the **Gate 2** checkpoint ("core loop + notifications live") and the Saturday Week-4 PR merge day.

---

## 1. Objective

Three parallel deliverables must land together today:

1. **DB Layer:** Create the `notifications` table and the `sessions_device_tokens` table with correct columns, constraints, indexes, and RLS — exactly matching the schema defined in Section 7, Group A and Group E of the project manual.
2. **FCM Push:** Implement a lightweight `backend/app/notifications/fcm.py` helper that sends a push notification to every registered device token for a user via the Firebase Cloud Messaging HTTP v1 API.
3. **API Endpoints:** Implement `GET /notifications`, `POST /notifications/{id}/read`, and `POST /device-tokens` (device-token registration) in a new `notifications.py` router, following the same patterns as `digests.py`.

These three form the complete backend half of Week 4's notifications work. Jigyasu wires the Flutter Notifications list screen to these endpoints the same day — the endpoint shape must match the payload contract agreed on D23.

---

## 2. Database — New Tables

### 2.1 `notifications`

In-app + push notification records, including the LLM-written banner line.

| Column | Type / Constraints | Notes |
|---|---|---|
| `id` | uuid, PK, DEFAULT gen_random_uuid() | |
| `user_id` | uuid, FK profiles(user_id) ON DELETE CASCADE | |
| `type` | text, NOT NULL | CHECK: `approval_needed \| task_completed \| digest_ready \| oauth_expiring` |
| `title` | text, NOT NULL | |
| `body` | text, NOT NULL | |
| `banner_text` | text | Short LLM-written line, advisory only; nullable |
| `read` | boolean, NOT NULL, DEFAULT false | |
| `related_task_id` | uuid, FK tasks(id) | Nullable |
| `created_at` | timestamptz, NOT NULL, DEFAULT now() | |

**Indexes:**
- `notifications_user_id_idx` on `(user_id)` — primary query pattern
- `notifications_created_at_idx` on `(created_at DESC)` — newest-first ordering
- `notifications_user_read_idx` on `(user_id, read)` — unread-count queries

**RLS policy:** `user_id = auth.uid()` for SELECT/UPDATE. INSERT restricted to service-role only (backend writes notifications, users never insert directly).

### 2.2 `sessions_device_tokens`

Push-notification device targets (FCM tokens), one row per installed device.

| Column | Type / Constraints | Notes |
|---|---|---|
| `id` | uuid, PK, DEFAULT gen_random_uuid() | |
| `user_id` | uuid, FK profiles(user_id) ON DELETE CASCADE | |
| `fcm_token` | text, NOT NULL | |
| `device_type` | text | CHECK: `ios \| android` |
| `created_at` | timestamptz, NOT NULL, DEFAULT now() | |
| `last_active` | timestamptz | Updated on each push attempt |

**Indexes:**
- `sessions_device_tokens_user_id_idx` on `(user_id)` — look up all tokens for a user
- Unique constraint on `(user_id, fcm_token)` — prevent duplicate registrations from the same device

**RLS policy:** `user_id = auth.uid()` — users manage only their own device tokens.

---

## 3. Migration Files

### 3.1 `20260919000019_create_notifications.sql`

```sql
-- Migration: 20260919000019_create_notifications
-- Creates the notifications table for in-app + push notification records.
-- D24: notifications table + push endpoint (FCM integration)
-- Idempotent: yes  Destructive: no

create table if not exists public.notifications (
    id               uuid        not null default gen_random_uuid(),
    user_id          uuid        not null,
    type             text        not null,
    title            text        not null,
    body             text        not null,
    banner_text      text,                           -- nullable: LLM-written advisory copy
    read             boolean     not null default false,
    related_task_id  uuid,
    created_at       timestamptz not null default now(),

    constraint notifications_pkey primary key (id),
    constraint notifications_user_id_fkey
        foreign key (user_id) references public.profiles (user_id) on delete cascade,
    constraint notifications_related_task_id_fkey
        foreign key (related_task_id) references public.tasks (id) on delete set null,
    constraint notifications_type_check
        check (type in ('approval_needed', 'task_completed', 'digest_ready', 'oauth_expiring'))
);

-- Indexes
create index if not exists notifications_user_id_idx
    on public.notifications (user_id);

create index if not exists notifications_created_at_idx
    on public.notifications (created_at desc);

create index if not exists notifications_user_read_idx
    on public.notifications (user_id, read);

-- RLS
alter table public.notifications enable row level security;

-- SELECT: users see only their own notifications
drop policy if exists "notifications_owner_select" on public.notifications;
create policy "notifications_owner_select" on public.notifications
    for select
    using (user_id = auth.uid());

-- UPDATE: users can mark their own notifications as read (no other mutation allowed client-side)
drop policy if exists "notifications_owner_update" on public.notifications;
create policy "notifications_owner_update" on public.notifications
    for update
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- INSERT: service-role only; no client policy (RLS default deny)
-- DELETE: service-role only; no client policy
```

### 3.2 `20260919000020_create_sessions_device_tokens.sql`

```sql
-- Migration: 20260919000020_create_sessions_device_tokens
-- Creates the sessions_device_tokens table for FCM push targets.
-- D24: notifications table + push endpoint (FCM integration)
-- Idempotent: yes  Destructive: no

create table if not exists public.sessions_device_tokens (
    id           uuid        not null default gen_random_uuid(),
    user_id      uuid        not null,
    fcm_token    text        not null,
    device_type  text,
    created_at   timestamptz not null default now(),
    last_active  timestamptz,

    constraint sessions_device_tokens_pkey primary key (id),
    constraint sessions_device_tokens_user_id_fkey
        foreign key (user_id) references public.profiles (user_id) on delete cascade,
    constraint sessions_device_tokens_device_type_check
        check (device_type in ('ios', 'android')),
    constraint sessions_device_tokens_user_token_unique
        unique (user_id, fcm_token)
);

create index if not exists sessions_device_tokens_user_id_idx
    on public.sessions_device_tokens (user_id);

alter table public.sessions_device_tokens enable row level security;

-- SELECT: users can see their own device tokens
drop policy if exists "device_tokens_owner_select" on public.sessions_device_tokens;
create policy "device_tokens_owner_select" on public.sessions_device_tokens
    for select
    using (user_id = auth.uid());

-- INSERT: users can register their own tokens
drop policy if exists "device_tokens_owner_insert" on public.sessions_device_tokens;
create policy "device_tokens_owner_insert" on public.sessions_device_tokens
    for insert
    with check (user_id = auth.uid());

-- UPDATE: users can update their own tokens (e.g. last_active)
drop policy if exists "device_tokens_owner_update" on public.sessions_device_tokens;
create policy "device_tokens_owner_update" on public.sessions_device_tokens
    for update
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- DELETE: users can revoke their own tokens (on logout/uninstall)
drop policy if exists "device_tokens_owner_delete" on public.sessions_device_tokens;
create policy "device_tokens_owner_delete" on public.sessions_device_tokens
    for delete
    using (user_id = auth.uid());
```

---

## 4. Config — Add `FIREBASE_SERVICE_ACCOUNT_PATH`

### 4.1 `.env` / `.env.example`

Replace the old `FCM_SERVER_KEY=` placeholder in `.env.example` with:

```
# --- Firebase Cloud Messaging (required from D24) ----------------------------
# Path to the Firebase service-account JSON downloaded from:
# Firebase Console → Project Settings → Service Accounts → Generate new private key
FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/firebase-service-account.json
```

Update `.env` with the real path to the downloaded service-account JSON before running locally.

> **Security:** Never commit the service-account JSON to source control. Add `firebase-service-account*.json` to `.gitignore` now.

### 4.2 `backend/app/core/config.py`

Remove the old `fcm_server_key` field and add `firebase_service_account_path`:

```python
# REMOVE:
# fcm_server_key: str = Field(..., alias="FCM_SERVER_KEY")

# ADD (in Settings — pydantic-settings BaseSettings):
firebase_service_account_path: str = Field(..., alias="FIREBASE_SERVICE_ACCOUNT_PATH")
```

Same fail-fast rule as all other required keys: missing at startup → pydantic raises `ValidationError`, server does not start.

### 4.3 `requirements.txt`

Add the `firebase-admin` SDK (not yet a dependency):

```
firebase-admin>=6.5.0
```

---

## 5. FCM Push Helper — `backend/app/notifications/fcm.py`

### 5.1 Purpose

A thin, best-effort wrapper around the FCM HTTP v1 API via the `firebase-admin` SDK. It initialises the app once at module load, then sends a push to every device token registered for a user. Token errors (stale/invalid tokens) are caught, logged, and the stale token is deleted from `sessions_device_tokens` — matching the stale-token handling requirement from Section 2.3 of the project manual.

> **Why `firebase-admin` instead of raw `httpx`?** The legacy FCM endpoint (`https://fcm.googleapis.com/fcm/send` with `Authorization: key=<server-key>`) was deprecated June 2023 and shut down starting July 2024. The `firebase-admin` SDK targets the FCM HTTP v1 API and handles OAuth2 credential rotation automatically.

### 5.2 Module-Level Initialisation (once at import)

```python
import firebase_admin
from firebase_admin import credentials, messaging
from app.core.config import settings

cred = credentials.Certificate(settings.firebase_service_account_path)
firebase_admin.initialize_app(cred)
```

This runs once when `fcm.py` is first imported. If the service-account file is missing or malformed, the import will raise immediately — consistent with the fail-fast pattern used elsewhere.

### 5.3 Implementation Contract

```python
def send_push_notification(
    user_id: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> None:
    """
    Send a push notification to all registered devices for user_id via FCM HTTP v1.
    Best-effort: never raises. Logs warnings on partial or total failure.
    Stale/invalid tokens are silently removed from sessions_device_tokens.
    """
```

**Implementation steps inside `send_push_notification`:**

1. Query `sessions_device_tokens` for all rows where `user_id = user_id`.
2. If no tokens exist, log at DEBUG level and return immediately.
3. For each token, build and send via the SDK:
   ```python
   message = messaging.Message(
       notification=messaging.Notification(title=title, body=body),
       data=data or {},
       token=fcm_token,
   )
   response = messaging.send(message)
   ```
4. On success: update `last_active` on that token's row in `sessions_device_tokens`.
5. On `messaging.UnregisteredError` (SDK equivalent of the old `InvalidRegistration`/`NotRegistered`): delete the stale token row from `sessions_device_tokens`, log at WARNING.
6. On any other `messaging.FirebaseError` or network/IO exception: log at WARNING, do **not** delete the token, do **not** re-raise.
7. After iterating all tokens, log a summary at INFO level: `user_id`, total tokens, success count, failure count.

> **Security:** Never log raw token values or any credential content — log only `user_id`, token count, and success/failure counts.

> **Future note:** `# TODO(D25+): if load testing shows per-message SDK calls are too slow under concurrency, revisit batching via messaging.send_each() — not needed for Gate 2.`

---

## 6. Notifications Router — `backend/app/api/routers/notifications.py`

### 6.1 Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/notifications` | JWT | List the user's in-app notifications, newest-first |
| `POST` | `/notifications/{id}/read` | JWT | Mark a single notification as read |
| `POST` | `/device-tokens` | JWT | Register an FCM device token for this user |
| `DELETE` | `/device-tokens/{token_id}` | JWT | Remove a device token (logout / uninstall) |

### 6.2 `GET /notifications`

**Query params:**
- `limit: int` — default 20, max 100
- `offset: int` — default 0
- `unread_only: bool` — default False; if True, filter `read = false`

**Response schema `NotificationListOut`:**
```json
{
  "notifications": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "type": "approval_needed",
      "title": "...",
      "body": "...",
      "banner_text": "...",
      "read": false,
      "related_task_id": "uuid or null",
      "created_at": "ISO-8601"
    }
  ],
  "total": 5,
  "limit": 20,
  "offset": 0
}
```

**Implementation notes:**
- Query `notifications` table filtered by `user_id = current_user.id`, ordered by `created_at DESC`.
- RLS enforces isolation; explicit `user_id` filter added as a defence-in-depth measure (same as `digests.py`).
- If `unread_only=True`, add `.eq("read", False)` to the query.
- On DB error: return HTTP 500, log at ERROR level.

### 6.3 `POST /notifications/{id}/read`

**Request body:** None (the action is the mark-as-read).

**Response:** `{"id": "<id>", "read": true}`

**Implementation notes:**
- Verify the notification belongs to the current user before updating (or rely on RLS UPDATE policy — add explicit ownership check as defence in depth).
- Update `read = true` where `id = <id>` AND `user_id = current_user.id`.
- If no row updated (wrong ID or wrong user): return HTTP 404.

### 6.4 `POST /device-tokens`

**Request body `DeviceTokenIn`:**
```json
{
  "fcm_token": "eAPx...",
  "device_type": "android"
}
```

**Response:** `{"id": "uuid", "fcm_token": "...", "device_type": "android", "created_at": "..."}`

**Implementation notes:**
- Use an UPSERT (`on_conflict="user_id,fcm_token"`) to handle re-registration of the same token (e.g. after app restart) — update `last_active` on conflict.
- `device_type` is optional (nullable); validate against `["ios", "android"]` in the Pydantic model using a `Literal`.

### 6.5 `DELETE /device-tokens/{token_id}`

**Response:** HTTP 204 No Content on success.

**Implementation notes:**
- Delete from `sessions_device_tokens` where `id = token_id` AND `user_id = current_user.id`.
- If not found or not owned: return HTTP 404.

### 6.6 Register in `main.py`

Add to `backend/app/main.py`:

```python
from app.api.routers import ..., notifications
...
app.include_router(notifications.router)
```

---

## 7. Notification Creation Helper (Internal)

Add a `create_notification()` internal function (not a public endpoint) to `notifications.py` or a new `backend/app/notifications/service.py`. This is the function called by the agent loop and jobs when a notification event fires.

```python
def create_notification(
    user_id: str,
    event_type: str,           # maps to NotificationEvent enum value
    title: str,
    body: str,
    related_task_id: str | None = None,
) -> str:
    """
    Inserts a row into the notifications table, generates banner_text via
    banner_model.generate_banner_text(), and fires send_push_notification().
    Returns the new notification id (uuid).
    Best-effort on FCM send — a push failure never blocks the notification insert.
    """
```

**Steps:**
1. Call `generate_banner_text(...)` from `banner_model.py` to get `banner_text`. If the call raises, set `banner_text = None` and log at WARNING — banner failure must not block the notification row.
2. Insert row into `notifications` table via `supabase.table("notifications").insert({...}).execute()`.
3. After successful insert, call `send_push_notification(user_id, title, body)` (best-effort, no re-raise).
4. Return the inserted `id`.

> **Note:** `create_notification()` is the integration point Jigyasu's Flutter client depends on. Its DB contract (table shape + RLS) must be stable before the Day-24 merge.

---

## 8. Error Handling

| Scenario | Expected Behaviour |
|---|---|
| FCM send fails for one token (stale/invalid) | Delete the stale token; continue to other tokens; log at WARNING |
| FCM send fails for all tokens (network error) | Log at WARNING; notification row is still inserted; never re-raise |
| `banner_model.generate_banner_text()` raises | Set `banner_text = None`; insert notification without banner; log at WARNING |
| `notifications` insert fails | Log at ERROR; raise so the caller knows the notification was not created |
| `GET /notifications` DB error | Return HTTP 500; log at ERROR |
| `POST /notifications/{id}/read` — wrong owner | Return HTTP 404 (do not leak existence of other users' notifications) |
| Device token already registered (duplicate) | UPSERT — update `last_active`; return 200/201 normally |

---

## 9. Security Notes

- **Never log FCM tokens in plaintext** — log only `user_id` and token count.
- **Never log credential content** — the service-account JSON (`FIREBASE_SERVICE_ACCOUNT_PATH`) must never appear in logs; fail loudly at startup if the file is missing, never at runtime.
- **Service-account JSON must not be committed** — add `firebase-service-account*.json` to `.gitignore`.
- **No client-side notification insert** — the INSERT RLS policy on `notifications` is service-role only; a client calling this endpoint directly is blocked by RLS before any application logic runs.
- **`related_task_id` FK** — set to `ON DELETE SET NULL` so task deletions don't cascade-delete notification history.

---

## 10. Config / Env

| Variable | Required from | Notes |
|---|---|---|
| `FIREBASE_SERVICE_ACCOUNT_PATH` | D24 (today) | Path to the Firebase service-account JSON. Download from Firebase Console → Project Settings → Service Accounts → Generate new private key. **Do not commit this file.** |
| `SUPABASE_URL` | D3 | Already present |
| `SUPABASE_SERVICE_ROLE_KEY` | D3 | Already present |

**New dependency:** `firebase-admin>=6.5.0` — add to `requirements.txt`.

---

## 11. Out of Scope

- `DELETE /notifications/{id}` — not in the API reference for this sprint.
- Notification grouping, batching, or de-duplication logic — Week 5+.
- Trust Dashboard `/dashboard/metrics` — D30.
- Android notification channels or iOS APNs certificates — Jigyasu's Flutter side.
- `sessions_device_tokens.last_active` automatic sweep job — not needed for Gate 2; stale token cleanup handled on failed push send.

---

## 12. Acceptance / Test Criteria

Create `backend/app/tests/test_notifications.py`. Use `unittest.mock.patch` on `supabase.table(...)` and on `httpx.post` — no real DB or FCM calls in unit tests.

### 12.1 Migration tests (run via `pytest` against the test Supabase project):

| Test | What it checks |
|---|---|
| `test_notifications_table_created` | Table exists with all required columns |
| `test_notifications_type_check_constraint` | INSERT with invalid `type` value raises a DB constraint error |
| `test_sessions_device_tokens_table_created` | Table exists with all required columns |
| `test_device_token_unique_constraint` | Inserting duplicate `(user_id, fcm_token)` raises a DB unique violation |

### 12.2 FCM helper unit tests:

Use `unittest.mock.patch` on `firebase_admin.messaging.send` — no real FCM calls in unit tests.

| Test | What it checks |
|---|---|
| `test_send_push_no_tokens_returns_early` | When no device tokens exist, `messaging.send` is never called |
| `test_send_push_success_updates_last_active` | On successful `messaging.send`, `last_active` is updated in the DB |
| `test_send_push_stale_token_deleted` | When `messaging.send` raises `messaging.UnregisteredError`, the token row is deleted from `sessions_device_tokens` |
| `test_send_push_network_error_does_not_raise` | When `messaging.send` raises a generic `messaging.FirebaseError`, function returns without raising |
| `test_send_push_does_not_log_raw_token` | Confirms the FCM token value does not appear in captured log output |

### 12.3 API endpoint unit tests:

| Test | What it checks |
|---|---|
| `test_get_notifications_returns_list` | `GET /notifications` returns a `NotificationListOut` with correct structure |
| `test_get_notifications_unread_filter` | `unread_only=true` filters to only `read=false` rows |
| `test_mark_notification_read` | `POST /notifications/{id}/read` sets `read=true` |
| `test_mark_notification_wrong_owner_returns_404` | Marking another user's notification returns 404 |
| `test_register_device_token` | `POST /device-tokens` inserts a row and returns the new token record |
| `test_register_device_token_duplicate_upserts` | Re-registering the same token updates `last_active` |
| `test_delete_device_token` | `DELETE /device-tokens/{id}` removes the correct row |
| `test_delete_device_token_wrong_owner_returns_404` | Deleting another user's token returns 404 |

### 12.4 `create_notification()` unit tests:

| Test | What it checks |
|---|---|
| `test_create_notification_inserts_row` | Inserts into `notifications` and calls `send_push_notification` |
| `test_create_notification_banner_failure_inserts_anyway` | If `generate_banner_text` raises, notification is still created with `banner_text=None` |
| `test_create_notification_push_failure_does_not_raise` | If `send_push_notification` fails, `create_notification` still returns the notification id |

---

## 13. Week-4 PR Merge Coordination (Gate 2)

D24 is the Gate 2 checkpoint. Before merging, confirm:

- [ ] Both migrations (`notifications`, `sessions_device_tokens`) applied to Supabase test project and verified with `verify_schema.sql`.
- [ ] `FIREBASE_SERVICE_ACCOUNT_PATH` set in `.env`; service-account JSON present at that path; file added to `.gitignore`.
- [ ] `firebase-admin>=6.5.0` added to `requirements.txt` and installed in `.venv`.
- [ ] `fcm.py`, `notifications.py` router, and `create_notification()` helper all present and passing tests.
- [ ] `main.py` registers the `notifications` router.
- [ ] All tests in `test_notifications.py` pass: `pytest backend/app/tests/test_notifications.py -v`
- [ ] CI green: ruff lint + pytest + eval smoke subset + build check.
- [ ] Coordinate with **Jigyasu**: confirm `GET /notifications` response shape matches the payload contract agreed on D23 before Suraj merges.
- [ ] No direct pushes to `main` (A9 — branch protection applies on gate day same as any other day).

---

## 14. Dependencies

- D11 (tasks table) — ✅ done
- D17 (FCM device-token setup on the Flutter side, Jigyasu) — ✅ done
- D20 (trigger_rules.py — `NotificationEvent` enum + `evaluate_trigger`) — ✅ done
- D22 (execution_logs wire-up) — ✅ done; independent of notification delivery
- D23 (digests table + digest job; notifications payload contract agreed with Jigyasu) — ✅ done
- `banner_model.py` (Ishani, D17) — ✅ done; imported as-is
