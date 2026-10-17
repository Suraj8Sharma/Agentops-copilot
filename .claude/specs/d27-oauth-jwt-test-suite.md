# D27 Spec: OAuth / JWT Test Suite (v2)

**Task (Manual §14, D27, Suraj):** OAuth/JWT test suite: refresh, expiry, revoke, RLS-isolation tests
**Date:** Wed 23 Sep 2026 · **Owner:** Suraj · **Source:** Manual v2.0 (§14, §15.4, §16.3, §18 A3, §17 Gate 3)
**Depends on:** D26 merged; D8 (callback + encryption); D9 (sweep); existing auth tests
**Type:** Test-only day. No production code changes.

---

## 1. Objective

Close the OAuth/JWT test gaps left after D8-D9, in plain terms: prove that Google tokens refresh correctly, that failures are handled cleanly, that disconnect removes a connection, and that the RLS policies on `oauth_connections` and `tasks` are defined as intended.

Four areas:

1. **Google token refresh:** `get_valid_google_token` (valid, expired, revoked, missing, network error, scope mismatch), plus the A3 success-rate check.
2. **Disconnect:** `DELETE /oauth/{provider}` deletes the row and requires a JWT.
3. **RLS policy definitions:** migration SQL asserts owner-only access and no client INSERT on `oauth_connections`.
4. **JWT lifecycle:** already fully covered by `test_jwt.py`. **No new JWT tests in D27.**

All new tests are fully mocked: no live Supabase, no real provider calls, no env vars in CI.

---

## 2. Already covered (do not duplicate or modify)

| File | Covers |
|---|---|
| `test_jwt.py` | Valid accepted, missing rejected, tampered rejected, expired rejected (`token_expired` + `X-Token-Expired`), refresh issues new pair, bad refresh rejected |
| `test_oauth_connect.py` | Correct scopes, required URL params, unique state, unknown provider 404, missing client_id 500, GitHub/Slack 200 |
| `test_oauth_callback.py` | Code-for-token exchange, tokens encrypted at rest, invalid state 400, consent denied 400 |
| `test_oauth_sweep.py` | 7-day Testing-mode flag, sweep needs CRON_SECRET, background refresh |
| `test_oauth_github_slack.py` | GitHub/Slack callback flows |

---

## 3. Step 0: read before writing (15 min)

Open these and copy the real shapes into the tests. Do not write tests from memory.

1. `app/mcp_clients/google_token_refresh.py`: confirm the exact Supabase call chains (`select`, `update().eq().in_()`), the helper names (`_mark_expired`), whether it checks `status`, and what it catches (`httpx.RequestError` vs broader).
2. `app/api/routers/oauth.py` DELETE route: confirm whether it checks `_SUPPORTED_PROVIDERS`.
3. Migrations `20260825000004` and `20260828000006`: note exact policy names and whether any policy uses `for all`.

Record findings in the diary. They decide the two xfail cases in §4.

---

## 4. New test files and required cases

### 4.1 `test_google_token_refresh.py` (9 tests)

Target: `app.mcp_clients.google_token_refresh.get_valid_google_token`

Patch: `supabase_admin`, `httpx.post`, and `settings` (all inside the `google_token_refresh` module).

| Test | Proves |
|---|---|
| `test_valid_token_returned_without_refresh` | `expires_at` 30 min ahead returns the decrypted token; `httpx.post` not called |
| `test_expired_token_triggers_google_refresh` | `expires_at` 10 min ago calls `httpx.post` with `grant_type=refresh_token`; DB update receives newly encrypted values; stored value != plaintext, and decrypts to the new token |
| `test_refresh_updates_both_provider_rows` | Update targets both `google_calendar` and `gmail` (shared token), matching the real call chain |
| `test_revoked_token_returns_none_and_marks_expired` | Non-2xx `{"error": "invalid_grant"}` returns `None` and sets `status="expired"` |
| `test_missing_refresh_token_returns_none` | `refresh_token=None` with past `expires_at` returns `None`; no `httpx.post` |
| `test_no_db_row_returns_none` | Empty query result returns `None` (this is also the "after disconnect, provider is unusable" case) |
| `test_network_error_returns_none` | `httpx.RequestError` returns `None`, does not raise |
| `test_scope_mismatch_row_returns_none` | Row with `status="scope_mismatch"` returns `None` (Manual §15.4 named test: `test_oauth_scope_mismatch_disables_feature_gracefully`). See xfail rule below |
| `test_refresh_success_rate_meets_a3_threshold` | **Acceptance A3.** Run 20 expiry simulations (19 succeed, 1 returns `invalid_grant`). Assert success rate >= 95%, and the failing run returns `None` with `_mark_expired` called (a clear failure, never silent, never an exception) |

**xfail rule for `test_scope_mismatch_row_returns_none`:** if Step 0 shows the function does not check `status`, write the test as `@pytest.mark.xfail(strict=True, reason="scope_mismatch enforcement not implemented; D28")`, log a GitHub issue, and note the deviation in the PR and diary. Do not change production code in D27. `strict=True` makes the test fail loudly once the fix lands, so the marker gets removed.

### 4.2 `test_oauth_revoke.py` (3 tests)

Target: `DELETE /oauth/{provider}` in `app.api.routers.oauth`.

Patch `app.api.routers.oauth.create_client`; override `get_current_user` with a fake user.

| Test | Proves |
|---|---|
| `test_disconnect_google_deletes_row` | `DELETE /oauth/google_calendar` returns 200 `{"message": "Disconnected"}` and calls `table().delete().eq("user_id", …).eq("provider", "google_calendar").execute()` |
| `test_disconnect_requires_jwt` | No Authorization header returns 401 |
| `test_disconnect_unknown_provider_returns_404` | `DELETE /oauth/notion` returns 404. **Contract test.** If Step 0 shows no `_SUPPORTED_PROVIDERS` guard, mark `xfail(strict=True)`, log a GitHub issue, fix in D28 |

### 4.3 `test_rls_policy_definitions.py` (4 tests)

These are **policy-definition checks**, not live isolation tests. They read migration SQL and assert the policies are written as intended. They cannot prove runtime isolation; the live two-user test is the Week-5 upgrade (§8).

Helper: load the file, strip `--` comments, collapse whitespace, lowercase, then match with regex so formatting changes do not break tests.

| Test | Proves |
|---|---|
| `test_rls_enabled_on_oauth_connections` | `20260825000004` contains `enable row level security` for `oauth_connections` |
| `test_oauth_connections_select_policy_is_owner_only` | SELECT policy on `oauth_connections` uses `user_id = auth.uid()` |
| `test_oauth_connections_no_insert_policy_for_authenticated` | No `insert` policy for `authenticated`, **and no `for all` policy**, since `for all` silently includes INSERT. INSERT is service-role only |
| `test_tasks_select_policy_is_owner_only` | `20260828000006` tasks SELECT policy uses `user_id = auth.uid()` |

---

## 5. Test conventions

- One `Fernet.generate_key()` per test module. No fixed keys, no real secrets.
- Never assert plaintext tokens in stored DB values. Assert encrypted != plaintext, then decrypt and compare.
- Use `freezegun` or pass explicit `expires_at` values; never sleep.
- Each new file's module docstring names the spec section and manual item it satisfies.
- Run `ruff` before pushing. Definition of Done (§16.3) applies.

---

## 6. Out of scope

- Live Supabase or provider tests (Week-5 upgrade).
- Full 17-table RLS audit: `test_rls_security.py`, D33.
- GitHub/Slack provider-side revocation.
- Production code changes. Any bug found becomes a GitHub issue, fixed in D28.

---

## 7. Done when

- [ ] Step 0 findings recorded in the diary.
- [ ] `test_google_token_refresh.py`: 9 tests (8 green + scope-mismatch green or strict-xfail).
- [ ] `test_oauth_revoke.py`: 3 tests (2 green + unknown-provider green or strict-xfail).
- [ ] `test_rls_policy_definitions.py`: 4 tests green.
- [ ] Full `pytest app/tests/` green; no existing file modified.
- [ ] CI passes with no live Supabase and no secrets.
- [ ] Module docstrings reference this spec.
- [ ] GitHub issues logged for any xfail; deviations noted in the PR.
- [ ] PR reviewed and merged; D27 diary notes that live-DB RLS is deferred to Week 5.
- [ ] OAuth/JWT suite confirmed running in CI (Gate 3, Sat 26 Sep).

---

## 8. Follow-ups

| Item | When |
|---|---|
| Fix xfail items (scope-mismatch enforcement, unknown-provider guard), remove markers | D28 |
| Live two-user RLS test against a Supabase test container, replacing §4.3 | Week 5, optional |
| Full 17-table RLS audit | D33 |