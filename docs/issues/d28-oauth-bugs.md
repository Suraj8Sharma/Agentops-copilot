# D28 Follow-Up Bugs (Identified during D27 Test Suite)

This document contains the two bug reports identified during D27 test coverage. Both tests currently have `@pytest.mark.xfail(strict=True)` in the test suite and are scheduled for resolution in D28.

---

## Issue 1: `get_valid_google_token` does not check connection status (`scope_mismatch` treated as active)

**Component:** `backend/app/mcp_clients/google_token_refresh.py`  
**Test:** `backend/app/tests/test_google_token_refresh.py::test_scope_mismatch_row_returns_none`  
**Severity:** Medium  
**Source:** Manual v2.0 §15.4 (`test_oauth_scope_mismatch_disables_feature_gracefully`)

### Description
In `get_valid_google_token(user_id, provider)`, the query loads `access_token`, `refresh_token`, and `expires_at` from `oauth_connections`:
```python
result = (
    supabase_admin.table("oauth_connections")
    .select("access_token, refresh_token, expires_at")
    .eq("user_id", user_id)
    .eq("provider", provider)
    .limit(1)
    .execute()
)
```
The function never selects or inspects the `status` column. Consequently, if a connection is flagged as `scope_mismatch` (or `revoked`/`expired_testing_mode`), the function will still return the decrypted access token if `expires_at` has not lapsed.

### Steps to Reproduce
1. Insert a row in `oauth_connections` with `status = 'scope_mismatch'` and `expires_at` set 30 minutes in the future.
2. Call `get_valid_google_token(user_id, "google_calendar")`.
3. The function returns the plaintext token instead of `None`.

### Expected Behavior
If `row.get("status") != "active"`, `get_valid_google_token` should treat the connection as unavailable, log a warning, and immediately return `None`.

### Proposed Fix for D28
1. Add `status` to the `.select()` query in `google_token_refresh.py`.
2. Add a status guard before decrypting tokens:
   ```python
   if row.get("status") != "active":
       logger.warning("Connection status is %s, aborting token retrieval", row.get("status"))
       return None
   ```
3. Remove the `@pytest.mark.xfail` marker on `test_scope_mismatch_row_returns_none`.

---

## Issue 2: `DELETE /oauth/{provider}` lacks provider validation (returns 200 on unknown providers instead of 404)

**Component:** `backend/app/api/routers/oauth.py` (`delete_connection`)  
**Test:** `backend/app/tests/test_oauth_revoke.py::test_disconnect_unknown_provider_returns_404`  
**Severity:** Low  
**Source:** D27 §4.2 Contract Test

### Description
The endpoint `DELETE /oauth/{provider}` currently executes a delete statement directly without validating whether `{provider}` is a supported provider (`google_calendar`, `gmail`, `github`, `slack`):
```python
@router.delete("/{provider}", summary="Disconnect OAuth provider")
def delete_connection(
    provider: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    from app.db.supabase_client import create_client
    service_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    service_client.table("oauth_connections").delete().eq(
        "user_id", current_user.id
    ).eq("provider", provider).execute()
    return {"message": "Disconnected"}
```
If a client requests `DELETE /oauth/notion`, the endpoint executes a delete on matching rows (deleting 0 rows) and returns `200 {"message": "Disconnected"}` instead of rejecting the unknown provider with `404 Not Found`.

### Steps to Reproduce
1. Send an authenticated request `DELETE /oauth/notion`.
2. Inspect the response status code.
3. Observed: `200 OK`. Expected: `404 Not Found`.

### Expected Behavior
Requests targeting unsupported provider names should return HTTP 404 with a helpful error message listing the valid providers.

### Proposed Fix for D28
1. In `delete_connection`, validate `provider` against `_SUPPORTED_PROVIDERS` (or the specific connection providers `{'google_calendar', 'gmail', 'github', 'slack'}`):
   ```python
   if provider not in _VALID_PROVIDERS:
       raise HTTPException(
           status_code=status.HTTP_404_NOT_FOUND,
           detail=f"Unknown OAuth provider: {provider!r}."
       )
   ```
2. Remove the `@pytest.mark.xfail` marker on `test_disconnect_unknown_provider_returns_404`.
