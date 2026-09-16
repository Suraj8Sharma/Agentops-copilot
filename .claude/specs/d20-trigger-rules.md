# D20 - Notification trigger rules Technical Spec

**Project:** AgentOps Copilot
**Plan reference:** D20
**Owner / track:** Suraj – backend
**Branch:** `feature/d20-trigger-rules`
**Files:**
- `backend/app/notifications/trigger_rules.py` (new)
- `backend/app/tests/test_trigger_rules.py` (new)

---

## 1. Objective

Define the canonical notification event types and the unified firing logic for the backend. This module (`trigger_rules.py`) sits between the core agent loop / scheduled jobs and the notification delivery system (FCM / in-app banners). It provides a standard contract for what events can trigger notifications and standardizes their payload, which is then consumed by Ishani's `banner_model.py` for copy generation.

## 2. Scope

| In scope | Out of scope (later days) |
| :-- | :-- |
| `NotificationEvent` Enum defining valid trigger types | Actually sending push notifications via FCM (D24) |
| A `evaluate_trigger()` function to determine if a notification should be created | Database schema for the `notifications` table (D24) |
| Documentation of payload contracts for each event type | The LLM call to generate banner copy (already defined in `banner_model.py`) |
| Test suite validating the trigger logic | Digest generation jobs (D23) |

## 3. Files to Create / Modify

| File | Purpose |
| :-- | :-- |
| `backend/app/notifications/trigger_rules.py` | Contains the `NotificationEvent` enum and the `evaluate_trigger` function. |
| `backend/app/tests/test_trigger_rules.py` | Unit tests for the firing logic and payload structure. |

## 4. Trigger Rules Design

### 4.1 Event Types (The Contract)
Based on the `banner_model.py` constraints, the system supports the following canonical event types. Define these in an `Enum`:

```python
from enum import Enum

class NotificationEvent(str, Enum):
    APPROVAL_NEEDED = "approval_needed"
    TASK_COMPLETED = "task_completed"
    DIGEST_READY = "digest_ready"
    OAUTH_EXPIRING = "oauth_expiring"
```

### 4.2 Firing Logic and Payload Schema
Implement the `evaluate_trigger` function. This function acts as the gatekeeper for creating notifications. 

```python
def evaluate_trigger(event_type: NotificationEvent, payload: dict) -> bool:
    """
    Evaluates whether an event should fire a notification based on its type and payload.
    Returns True if the notification should proceed, False otherwise.
    """
```

**Payload requirements per event (must be validated in `evaluate_trigger`):**
- **`approval_needed`**: Must contain `tool_name`, `task_id`, and `input_params`. Always fires (`True`).
- **`task_completed`**: Must contain `task_id`. May contain `tool_name`. Always fires (`True`) for now (user preferences can override this in the future).
- **`digest_ready`**: Must contain `digest_period` ("daily" | "weekly"). Always fires (`True`).
- **`oauth_expiring`**: Must contain `provider` and `expires_at`. Logic: Fire if `expires_at` is within 3 days; otherwise return `False`.

## 5. Definition of Done (per Section 16.3 of the manual)

- [ ] Code merged to `main` via a reviewed PR.
- [ ] `trigger_rules.py` is implemented with the `NotificationEvent` enum and `evaluate_trigger` function.
- [ ] Payload requirements for each event type are enforced.
- [ ] No secrets logged in plaintext.
- [ ] Tests exist and pass (see Section 6).

## 6. Required Test Suite Update (CI/CD Gate)

Create `backend/app/tests/test_trigger_rules.py` to cover the logic:

| Test name | What it checks |
| :-- | :-- |
| `test_approval_needed_always_fires` | An `approval_needed` event with valid payload returns `True`. |
| `test_oauth_expiring_fires_within_window` | An `oauth_expiring` event returns `True` if within 3 days. |
| `test_oauth_expiring_suppressed_if_future` | An `oauth_expiring` event returns `False` if expiration is > 3 days. |
| `test_invalid_payload_raises_error` | Missing required fields (e.g. `task_id` for `task_completed`) raises a `ValueError`. |

## 7. Acceptance Check

```bash
# Run tests locally
pytest backend/app/tests/test_trigger_rules.py -v
# Expect: all tests pass and coverage is 100% on trigger_rules.py
```
