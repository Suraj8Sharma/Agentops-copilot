# D28 Spec: OAuth Bug Fixes — scope_mismatch guard + provider validation

**Task (Manual §15.4, D28, Suraj):** Fix the two xfail bugs found during D27; remove xfail markers; confirm full green suite.
**Date:** Thu 24 Sep 2026 · **Owner:** Suraj · **Source:** D27 follow-ups (§8); `docs/issues/d28-oauth-bugs.md` Issues 1 & 2
**Depends on:** D27 merged; `feature/d27-oauth-jwt-test-suite` green in CI
**Type:** Production code fix + test marker removal. No new test cases beyond removing xfail.

---

## 1. Objective

Fix the two production bugs left open by D27 and turn the two `strict=True` xfail tests green.

| Issue | File | Symptom |
|---|---|---|
| **Issue 1** | `app/mcp_clients/google_token_refresh.py` | `get_valid_google_token` ignores `status`; a `scope_mismatch` row is treated as active and returns a token |
| **Issue 2** | `app/api/routers/oauth.py` (`delete_connection`) | `DELETE /oauth/{unknown}` returns 200 instead of 404 |

Both bugs are fully documented in [`docs/issues/d28-oauth-bugs.md`](../../docs/issues/d28-oauth-bugs.md).

After both fixes the entire D27+D28 test suite must be green with no xfail markers remaining.

---

## 2. Step 0: read before writing (10 min)

Confirm the exact shapes in production code before touching anything.

1. **`app/mcp_clients/google_token_refresh.py`** — check the `.select()` call at line ~101. Confirm `status` is **not** in the selected columns. Note where decryption begins (after `row = result.data[0]`) — the status guard goes **before** decryption.
2. **`app/api/routers/oauth.py`** — check `delete_connection` (bottom of file, line ~796). Confirm there is no `_SUPPORTED_PROVIDERS` guard. Note that `_SUPPORTED_PROVIDERS` already exists (line ~138) — it is `frozenset(PROVIDER_CONFIG)` = `{"google", "github", "slack"}`.

> [!IMPORTANT]
> `_SUPPORTED_PROVIDERS` in the connect/callback endpoints contains `"google"` (the OAuth consent provider), **not** `"google_calendar"` / `"gmail"` (the storage-level provider names). The DELETE endpoint receives storage-level provider names. Define a separate `_VALID_DISCONNECT_PROVIDERS` set for the fix — do **not** reuse `_SUPPORTED_PROVIDERS` without reading this note.

Record findings in the diary. They determine the exact guard values used.

---

## 3. Production code changes

### 3.1 Fix Issue 1 — `google_token_refresh.py`

**File:** `backend/app/mcp_clients/google_token_refresh.py`

**Change 1 of 2 — add `status` to the SELECT query.**

Existing line ~101:
```python
.select("access_token, refresh_token, expires_at")
```
Replace with:
```python
.select("access_token, refresh_token, expires_at, status")
```

**Change 2 of 2 — add status guard after `row = result.data[0]`.**

Insert immediately after `row = result.data[0]` (before the `encrypted_access` line), so the function returns `None` without decrypting or refreshing a disabled connection:

```python
connection_status = row.get("status", "active")
if connection_status != "active":
    logger.warning(
        "google_token_refresh: connection is %r, aborting token retrieval "
        "[user_id=%s provider=%s]",
        connection_status,
        user_id,
        provider,
    )
    return None
```

No other logic in the function changes. `_mark_expired` is unaffected.

### 3.2 Fix Issue 2 — `oauth.py` DELETE endpoint

**File:** `backend/app/api/routers/oauth.py`

**Change 1 of 2 — add `_VALID_DISCONNECT_PROVIDERS` constant.**

Add near the top of the router constants section (after `_SUPPORTED_PROVIDERS`, around line ~139):

```python
# Provider names as stored in oauth_connections.provider — used to validate
# DELETE /oauth/{provider}.  These differ from _SUPPORTED_PROVIDERS which
# uses the OAuth-flow names ("google", "github", "slack").
_VALID_DISCONNECT_PROVIDERS: frozenset[str] = frozenset(
    {"google_calendar", "gmail", "github", "slack"}
)
```

**Change 2 of 2 — add provider guard to `delete_connection`.**

Insert before the Supabase client creation, as the very first line inside `delete_connection`:

```python
if provider not in _VALID_DISCONNECT_PROVIDERS:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"Unknown OAuth provider: {provider!r}. "
            f"Valid providers: {', '.join(sorted(_VALID_DISCONNECT_PROVIDERS))}."
        ),
    )
```

---

## 4. Test changes — remove xfail markers

After both production fixes, remove the `@pytest.mark.xfail` decorator from exactly two tests.

### 4.1 `test_google_token_refresh.py`

Remove the decorator block from `test_scope_mismatch_row_returns_none`:

```python
# REMOVE this entire decorator:
@pytest.mark.xfail(
    strict=True,
    reason=(
        "get_valid_google_token does not check status field; "
        "scope_mismatch rows proceed as active. Fix in D28. "
        "Documented in docs/issues/d28-oauth-bugs.md (Issue 1)"
    ),
)
```

The test body is unchanged. After the fix it must pass green.

### 4.2 `test_oauth_revoke.py`

Remove the decorator block from `test_disconnect_unknown_provider_returns_404`:

```python
# REMOVE this entire decorator:
@pytest.mark.xfail(
    strict=True,
    reason=(
        "DELETE /oauth/{provider} does not validate provider against _SUPPORTED_PROVIDERS. "
        "An unknown provider like 'notion' silently runs an empty delete instead of returning 404. "
        "Fix in D28: add _SUPPORTED_PROVIDERS guard to the DELETE endpoint. "
        "Documented in docs/issues/d28-oauth-bugs.md (Issue 2)"
    ),
)
```

The test body is unchanged. After the fix it must pass green.

---

## 5. Test conventions (unchanged from D27)

- No new test files in D28.
- No changes to any test body — only the two `@pytest.mark.xfail` decorator blocks are removed.
- Run `ruff` before pushing.
- Run the full suite: `pytest backend/app/tests/` — expect 0 xfail, 0 skip, all green.

---

## 6. Out of scope

- Any new feature work.
- Any other test file modifications.
- Live Supabase or provider calls (still fully mocked in the test suite).
- Full 17-table RLS audit → D33.
- Live two-user RLS test → Week 5 (optional).

---

## 7. Done when

- [ ] Step 0 findings recorded in the diary.
- [ ] `google_token_refresh.py`: `status` added to `.select()`; status guard inserted.
- [ ] `oauth.py`: `_VALID_DISCONNECT_PROVIDERS` defined; `delete_connection` guards on it with 404.
- [ ] `@pytest.mark.xfail` removed from `test_scope_mismatch_row_returns_none`.
- [ ] `@pytest.mark.xfail` removed from `test_disconnect_unknown_provider_returns_404`.
- [ ] Full `pytest backend/app/tests/` green — **0 xfail, 0 failures**.
- [ ] CI passes with no live Supabase and no secrets.
- [ ] `ruff` clean on changed files.
- [ ] PR reviewed and merged; D28 diary entry notes both issues closed.
- [ ] GitHub issues for Issue 1 and Issue 2 closed/linked in the PR.

---

## 8. Follow-ups

| Item | When |
|---|---|
| Live two-user RLS test against a Supabase test container | Week 5, optional |
| Full 17-table RLS audit | D33 |
