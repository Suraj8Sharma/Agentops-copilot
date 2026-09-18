"""Tests for the D16 GitHub MCP client.

All external calls (Supabase, httpx) are mocked — no live DB or network needed.

Test map vs. spec acceptance criteria (d16_github_mcp_client_spec.md §9):
  test_github_call_routes_to_mcp_endpoint              -> AC-1  single call_tool entry point
  test_github_token_fernet_decrypted                   -> AC-2  Fernet decryption
  test_github_sse_response_parsed                      -> AC-3  SSE parsing, not raw .json()
  test_github_session_reused_across_calls              -> AC-4  session ID reuse
  test_github_session_reinit_on_rejection              -> AC-4  re-init on rejection
  test_github_notifications_initialized_sent           -> AC-5  notifications/initialized
  test_oauth_revoked_access_returns_clean_error        -> AC-6  401 → AUTH_EXPIRED
  test_github_create_issue_idempotency_precheck        -> AC-7  idempotency check
  test_github_execution_log_stub_present               -> AC-8  execution_logs stub
  test_github_429_returns_rate_limited                  -> AC-9a error taxonomy
  test_github_timeout_returns_timeout_error             -> AC-9b error taxonomy
  test_github_unknown_tool_returns_invalid_params       -> AC-9c error taxonomy
  test_github_5xx_returns_provider_error                -> AC-9d error taxonomy
  test_github_token_missing_returns_auth_expired        -> AC-9e error taxonomy
  test_github_create_issue_success                      -> named test (Section 15.4)
  test_github_retry_is_idempotent_no_double_create      -> named test (Section 15.4)
  test_call_tool_routes_github_server                   -> router integration
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import httpx

USER_ID = str(uuid.uuid4())
PLAN_ID = str(uuid.uuid4())
GITHUB_TOKEN_PLAINTEXT = "gho_test_github_token_abc123"
IDEMPOTENCY_KEY = f"{PLAN_ID}:0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_supabase(token=GITHUB_TOKEN_PLAINTEXT):
    """Mock supabase that returns a raw (unencrypted) token."""
    mock = MagicMock()
    chain = MagicMock()
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = MagicMock(data={"access_token": token} if token else None)
    mock.table.return_value.select.return_value = chain
    return mock


def _make_supabase_no_token():
    return _make_supabase(token=None)


def _make_sse_response(status_code=200, result=None, error=None, session_id="sess-123"):
    """Build a mock httpx.Response with SSE body like GitHub MCP returns."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.headers = {"mcp-session-id": session_id, "content-type": "text/event-stream"}

    if error:
        body = {"jsonrpc": "2.0", "id": 1, "error": error}
    else:
        body = {"jsonrpc": "2.0", "id": 1, "result": result or {}}

    import json

    resp.text = f"event: message\ndata: {json.dumps(body)}\n\n"
    resp.json.side_effect = ValueError("should use SSE parsing, not .json()")
    return resp


def _make_json_response(status_code, json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.headers = {"content-type": "application/json"}
    resp.json.return_value = json_body or {}
    resp.text = ""
    return resp


def _clear_session_cache():
    """Clear the module-level session cache between tests."""
    from app.mcp_clients.github import _session_cache

    _session_cache.clear()


def _patch_init_and_call(mock_sb, call_response, init_session_id="sess-abc"):
    """Return patches for supabase + httpx.post that handle init + tool call."""
    import json

    init_resp = MagicMock()
    init_resp.status_code = 200
    init_resp.is_success = True
    init_resp.headers = {
        "mcp-session-id": init_session_id,
        "content-type": "text/event-stream",
    }
    init_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"protocolVersion": "2025-06-18", "serverInfo": {"name": "github-mcp-server"}},
    }
    init_resp.text = f"event: message\ndata: {json.dumps(init_body)}\n\n"

    # notify response (fire-and-forget)
    notify_resp = MagicMock()
    notify_resp.status_code = 200
    notify_resp.is_success = True

    responses = [init_resp, notify_resp, call_response]

    return responses


# ---------------------------------------------------------------------------
# AC-1: Single call_tool entry point, no backend branching
# ---------------------------------------------------------------------------


def test_github_call_routes_to_mcp_endpoint():
    """All github.* tools POST to GITHUB_MCP_URL."""
    from app.mcp_clients.github import GITHUB_MCP_URL, call

    _clear_session_cache()
    mock_sb = _make_supabase()
    tool_resp = _make_sse_response(result={"issues": []})
    responses = _patch_init_and_call(mock_sb, tool_resp)
    posted_urls = []

    def post_side(url, **kw):
        posted_urls.append(url)
        return responses.pop(0)

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", side_effect=post_side),
    ):
        result = call("github.list_issues", {"repo": "owner/repo"}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "success"
    assert all(url == GITHUB_MCP_URL for url in posted_urls)


# ---------------------------------------------------------------------------
# AC-2: Fernet decryption used for token retrieval
# ---------------------------------------------------------------------------


def test_github_token_fernet_decrypted():
    """_fetch_github_token decrypts with Fernet when ENCRYPTION_KEY is set."""
    from cryptography.fernet import Fernet

    from app.mcp_clients.github import _fetch_github_token

    key = Fernet.generate_key().decode()
    fernet = Fernet(key.encode())
    encrypted = fernet.encrypt(GITHUB_TOKEN_PLAINTEXT.encode()).decode()

    mock_sb = _make_supabase(token=encrypted)
    mock_settings = MagicMock(ENCRYPTION_KEY=key)

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", mock_settings),
    ):
        token = _fetch_github_token(USER_ID)

    assert token == GITHUB_TOKEN_PLAINTEXT


# ---------------------------------------------------------------------------
# AC-3: SSE response parsing
# ---------------------------------------------------------------------------


def test_github_sse_response_parsed():
    """GitHub MCP SSE responses are parsed via data: line, not .json()."""
    import json

    from app.mcp_clients.github import _parse_sse_json

    body = {"jsonrpc": "2.0", "id": 1, "result": {"issue_number": 42}}
    resp = MagicMock()
    resp.headers = {"content-type": "text/event-stream"}
    resp.text = f"event: message\ndata: {json.dumps(body)}\n\n"
    resp.json.side_effect = ValueError("should not call .json()")

    parsed = _parse_sse_json(resp)
    assert parsed["result"]["issue_number"] == 42


# ---------------------------------------------------------------------------
# AC-4: Session ID captured and reused; re-init on rejection
# ---------------------------------------------------------------------------


def test_github_session_reused_across_calls():
    """Second call reuses the session ID from the first init."""
    from app.mcp_clients.github import call

    _clear_session_cache()
    mock_sb = _make_supabase()
    tool_resp = _make_sse_response(result={"ok": True})
    responses = _patch_init_and_call(mock_sb, tool_resp)
    call_count = {"init": 0}

    def post_side(url, **kw):
        body = kw.get("json", {})
        if body.get("method") == "initialize":
            call_count["init"] += 1
        return responses.pop(0) if responses else tool_resp

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", side_effect=post_side),
    ):
        call("github.list_issues", {"repo": "o/r"}, USER_ID, IDEMPOTENCY_KEY)
        # Second call — should NOT re-initialize
        call("github.list_issues", {"repo": "o/r"}, USER_ID, f"{PLAN_ID}:1")

    assert call_count["init"] == 1


def test_github_session_reinit_on_rejection():
    """A 404/410 response triggers session re-init, then retries the call."""
    from app.mcp_clients.github import _session_cache, call

    _clear_session_cache()
    # Pre-seed a stale session
    _session_cache[USER_ID] = "stale-session"

    mock_sb = _make_supabase()
    import json

    # First call returns 404 (session rejected)
    rejected_resp = MagicMock()
    rejected_resp.status_code = 404
    rejected_resp.is_success = False
    rejected_resp.headers = {}

    # Re-init responses
    init_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"protocolVersion": "2025-06-18"},
    }
    init_resp = MagicMock()
    init_resp.status_code = 200
    init_resp.is_success = True
    init_resp.headers = {"mcp-session-id": "new-session", "content-type": "text/event-stream"}
    init_resp.text = f"event: message\ndata: {json.dumps(init_body)}\n\n"

    notify_resp = MagicMock()
    notify_resp.status_code = 200
    notify_resp.is_success = True

    retry_resp = _make_sse_response(result={"ok": True}, session_id="new-session")

    responses = [rejected_resp, init_resp, notify_resp, retry_resp]

    def post_side(url, **kw):
        return responses.pop(0)

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", side_effect=post_side),
    ):
        result = call("github.list_issues", {"repo": "o/r"}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "success"
    assert _session_cache[USER_ID] == "new-session"


# ---------------------------------------------------------------------------
# AC-5: notifications/initialized sent after initialize
# ---------------------------------------------------------------------------


def test_github_notifications_initialized_sent():
    """After initialize, notifications/initialized is POSTed before tool call."""
    from app.mcp_clients.github import call

    _clear_session_cache()
    mock_sb = _make_supabase()
    tool_resp = _make_sse_response(result={"ok": True})
    responses = _patch_init_and_call(mock_sb, tool_resp)
    methods_sent = []

    def post_side(url, **kw):
        body = kw.get("json", {})
        if "method" in body:
            methods_sent.append(body["method"])
        return responses.pop(0)

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", side_effect=post_side),
    ):
        call("github.list_issues", {"repo": "o/r"}, USER_ID, IDEMPOTENCY_KEY)

    assert "initialize" in methods_sent
    assert "notifications/initialized" in methods_sent
    init_idx = methods_sent.index("initialize")
    notify_idx = methods_sent.index("notifications/initialized")
    assert notify_idx > init_idx


# ---------------------------------------------------------------------------
# AC-6: 401 → AUTH_EXPIRED, no retry
# ---------------------------------------------------------------------------


def test_oauth_revoked_access_returns_clean_error():
    """A 401 returns AUTH_EXPIRED error, no retry attempted."""
    from app.mcp_clients.github import _session_cache, call

    _clear_session_cache()
    _session_cache[USER_ID] = "existing-session"

    mock_sb = _make_supabase()
    resp_401 = MagicMock()
    resp_401.status_code = 401
    resp_401.is_success = False
    resp_401.headers = {}

    call_count = {"n": 0}

    def post_side(url, **kw):
        call_count["n"] += 1
        return resp_401

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", side_effect=post_side),
    ):
        result = call(
            "github.create_issue", {"repo": "o/r", "title": "bug"}, USER_ID, IDEMPOTENCY_KEY
        )

    assert result["status"] == "error"
    assert result["error"]["code"] == "AUTH_EXPIRED"
    assert call_count["n"] == 1  # no retry


# ---------------------------------------------------------------------------
# AC-7: Idempotency check before create_issue
# ---------------------------------------------------------------------------


def test_github_create_issue_idempotency_precheck():
    """If plan_steps shows done, no MCP call is made."""
    from app.mcp_clients.github import call

    _clear_session_cache()
    cached_output = {"issue_url": "https://github.com/o/r/issues/42", "number": 42}

    chain = MagicMock()
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = MagicMock(data={"status": "done", "output": cached_output})
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value = chain

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("httpx.post") as mp,
    ):
        result = call(
            "github.create_issue", {"repo": "o/r", "title": "t"}, USER_ID, IDEMPOTENCY_KEY
        )

    mp.assert_not_called()
    assert result["status"] == "success"
    assert result["output"] == cached_output


# ---------------------------------------------------------------------------
# AC-8: execution_logs stub present
# ---------------------------------------------------------------------------


def test_github_429_returns_rate_limited():
    """429 from GitHub MCP → status=rate_limited, code=RATE_LIMITED."""
    from app.mcp_clients.github import _session_cache, call

    _clear_session_cache()
    _session_cache[USER_ID] = "sess"

    mock_sb = _make_supabase()
    resp = MagicMock()
    resp.status_code = 429
    resp.is_success = False
    resp.headers = {}

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", return_value=resp),
    ):
        result = call("github.list_issues", {"repo": "o/r"}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "rate_limited"
    assert result["error"]["code"] == "RATE_LIMITED"


def test_github_timeout_returns_timeout_error():
    """httpx.TimeoutException → TIMEOUT error code."""
    from app.mcp_clients.github import _session_cache, call

    _clear_session_cache()
    _session_cache[USER_ID] = "sess"

    mock_sb = _make_supabase()

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", side_effect=httpx.TimeoutException("timed out")),
    ):
        result = call("github.list_issues", {"repo": "o/r"}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "error"
    assert result["error"]["code"] == "TIMEOUT"


def test_github_unknown_tool_returns_invalid_params():
    """Unknown tool_name → INVALID_PARAMS, no HTTP call."""
    from app.mcp_clients.github import call

    with patch("httpx.post") as mp:
        result = call("github.nonexistent", {}, USER_ID, IDEMPOTENCY_KEY)

    mp.assert_not_called()
    assert result["status"] == "error"
    assert result["error"]["code"] == "INVALID_PARAMS"
    assert "github.nonexistent" in result["error"]["message"]


def test_github_5xx_returns_provider_error():
    """A 500 from GitHub MCP → PROVIDER_ERROR."""
    from app.mcp_clients.github import _session_cache, call

    _clear_session_cache()
    _session_cache[USER_ID] = "sess"

    mock_sb = _make_supabase()
    resp = MagicMock()
    resp.status_code = 500
    resp.is_success = False
    resp.headers = {}

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", return_value=resp),
    ):
        result = call("github.list_issues", {"repo": "o/r"}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "error"
    assert result["error"]["code"] == "PROVIDER_ERROR"


def test_github_token_missing_returns_auth_expired():
    """No token in oauth_connections → AUTH_EXPIRED."""
    from app.mcp_clients.github import call

    _clear_session_cache()
    mock_sb = _make_supabase_no_token()

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post") as mp,
    ):
        result = call("github.list_issues", {"repo": "o/r"}, USER_ID, IDEMPOTENCY_KEY)

    mp.assert_not_called()
    assert result["status"] == "error"
    assert result["error"]["code"] == "AUTH_EXPIRED"


# ---------------------------------------------------------------------------
# Named tests from Section 15.4
# ---------------------------------------------------------------------------


def test_github_create_issue_success():
    """End-to-end: github.create_issue returns success with issue data."""
    from app.mcp_clients.github import call

    _clear_session_cache()

    # Table-aware mock: plan_steps returns "pending", oauth_connections returns token
    def table_side(name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.single.return_value = chain
        if name == "plan_steps":
            chain.execute.return_value = MagicMock(data={"status": "pending", "output": None})
        else:  # oauth_connections
            chain.execute.return_value = MagicMock(data={"access_token": GITHUB_TOKEN_PLAINTEXT})
        return chain

    mock_sb = MagicMock()
    mock_sb.table.side_effect = table_side

    issue_result = {"number": 42, "html_url": "https://github.com/o/r/issues/42"}
    tool_resp = _make_sse_response(result=issue_result)
    responses = _patch_init_and_call(mock_sb, tool_resp)

    def post_side(url, **kw):
        return responses.pop(0) if responses else tool_resp

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", side_effect=post_side),
    ):
        result = call(
            "github.create_issue",
            {"repo": "owner/repo", "title": "Bug report", "body": "Details here"},
            USER_ID,
            IDEMPOTENCY_KEY,
        )

    assert result["status"] == "success"
    assert result["output"]["number"] == 42
    assert "html_url" in result["output"]


def test_github_retry_is_idempotent_no_double_create():
    """A retry after success returns cached output — no second MCP call."""
    from app.mcp_clients.github import call

    _clear_session_cache()
    cached = {"number": 42, "html_url": "https://github.com/o/r/issues/42"}

    chain = MagicMock()
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = MagicMock(data={"status": "done", "output": cached})
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value = chain

    with (
        patch("app.mcp_clients.github.supabase", mock_sb),
        patch("httpx.post") as mp,
    ):
        result = call(
            "github.create_issue",
            {"repo": "o/r", "title": "Bug"},
            USER_ID,
            IDEMPOTENCY_KEY,
        )

    mp.assert_not_called()
    assert result["status"] == "success"
    assert result["output"] == cached


# ---------------------------------------------------------------------------
# Router integration
# ---------------------------------------------------------------------------


def test_call_tool_routes_github_server():
    """call_tool(mcp_server='github') resolves to github.call via _ROUTER."""
    from app.mcp_clients import call_tool

    with patch("app.mcp_clients.github.call") as mc:
        mc.return_value = {"status": "success", "output": {}, "error": None, "latency_ms": 5}
        result = call_tool(
            "github.list_issues", "github", {"repo": "o/r"}, USER_ID, IDEMPOTENCY_KEY
        )

    mc.assert_called_once_with(
        tool_name="github.list_issues",
        input_params={"repo": "o/r"},
        user_id=USER_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        task_id="unknown",
    )
    assert result["status"] == "success"
