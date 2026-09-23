"""Tests for the Gmail REST client (updated from D15 MCP client).

All external calls (Supabase, httpx) are mocked - no live DB or network needed.

Read/draft tools (list_messages, get_message, create_draft) now use the Gmail
REST API directly.  send_message was already REST and is unchanged.

Test map vs. spec acceptance criteria (d15-gmail-mcp-client.md):
  test_gmail_client_routes_send_to_gmail_api           -> AC-1
  test_gmail_client_routes_read_to_rest_api            -> AC-2 (updated: REST not MCP)
  test_gmail_list_messages_uses_threads_endpoint       -> AC-3 (updated: threads GET not RPC)
  test_gmail_send_uses_recipient_own_token             -> AC-4
  test_gmail_send_skips_duplicate_if_step_already_done -> AC-5
  test_gmail_send_403_returns_clear_reauth_error       -> AC-6
  test_gmail_draft_email_success                       -> AC-7 (updated: REST response shape)
  test_gmail_send_respects_approval_gate               -> AC-8
  test_gmail_mcp_token_missing_returns_error           -> AC-9
  test_gmail_mcp_401_returns_error                     -> AC-10 (updated: uses httpx.get)
  test_gmail_mcp_429_returns_rate_limited              -> AC-11 (updated: uses httpx.get)
  test_gmail_unknown_tool_returns_error                -> AC-12
  test_call_tool_routes_gmail_server                   -> AC-13
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

TASK_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())
PLAN_ID = str(uuid.uuid4())
STEP_ID = str(uuid.uuid4())
GOOGLE_TOKEN = "ya29.test_gmail_token"
IDEMPOTENCY_KEY = f"{PLAN_ID}:0"


REFRESH_PATCH = "app.mcp_clients.google_token_refresh.supabase_admin"


def _make_token_supabase(token=GOOGLE_TOKEN):
    mock = MagicMock()
    chain = MagicMock()
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = MagicMock(
        data=[
            {
                "access_token": token,
                "refresh_token": None,
                "expires_at": "2099-01-01T00:00:00+00:00",
            }
        ]
        if token
        else []
    )
    mock.table.return_value.select.return_value = chain
    return mock


def _make_supabase_no_token():
    return _make_token_supabase(token=None)


def _make_httpx_mcp_success():
    resp = MagicMock()
    resp.status_code = 200
    resp.is_success = True
    resp.json.return_value = {"jsonrpc": "2.0", "id": IDEMPOTENCY_KEY, "result": {"threads": []}}
    return resp


def _make_httpx_response(status_code, json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_body or {}
    return resp


def _make_state(plan=None, risk_flags=None, error=None, plan_id=PLAN_ID):
    return {
        "task_id": TASK_ID,
        "user_id": USER_ID,
        "raw_input": "send email",
        "input_type": "text",
        "intent": "send_email",
        "plan": plan or [],
        "plan_id": plan_id,
        "risk_flags": risk_flags or {},
        "current_step_index": 0,
        "step_results": {},
        "retries": {},
        "error": error,
    }


# AC-1
def test_gmail_client_routes_send_to_gmail_api():
    """gmail.send_message must POST to GMAIL_SEND_URL, not any MCP endpoint."""
    from app.mcp_clients.gmail import GMAIL_SEND_URL, call

    mock_sb = _make_token_supabase()
    send_resp = _make_httpx_response(200, {"id": "msg123", "threadId": "t1"})
    posted_urls = []

    def post_side(url, **kw):
        posted_urls.append(url)
        return send_resp

    with (
        patch("app.mcp_clients.gmail.supabase", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.post", side_effect=post_side),
    ):
        result = call(
            "gmail.send_message",
            {"to": ["t@e.com"], "subject": "Hi", "body": "B"},
            USER_ID,
            IDEMPOTENCY_KEY,
        )
    assert result["status"] == "success"
    assert GMAIL_SEND_URL in posted_urls
    # Ensure we only hit the send endpoint, not any MCP server
    assert all("mcp" not in url for url in posted_urls)


# AC-2
def test_gmail_client_routes_read_to_rest_api():
    """gmail.list_messages must GET the Gmail REST threads endpoint, not any MCP server."""
    from app.mcp_clients.gmail import _THREADS_URL, GMAIL_SEND_URL, call

    mock_sb = _make_token_supabase()
    threads_resp = _make_httpx_response(200, {"threads": [], "resultSizeEstimate": 0})
    got_urls = []

    def get_side(url, **kw):
        got_urls.append(url)
        return threads_resp

    with (
        patch("app.mcp_clients.gmail.supabase", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.get", side_effect=get_side),
    ):
        result = call("gmail.list_messages", {"q": "is:unread"}, USER_ID, IDEMPOTENCY_KEY)
    assert result["status"] == "success"
    assert _THREADS_URL in got_urls
    assert GMAIL_SEND_URL not in got_urls
    assert all("mcp" not in url for url in got_urls)


# AC-3
def test_gmail_list_messages_uses_threads_endpoint():
    """gmail.list_messages GETs /users/me/threads with the q param forwarded."""
    from app.mcp_clients.gmail import call

    mock_sb = _make_token_supabase()
    threads_resp = _make_httpx_response(200, {"threads": [{"id": "t1"}], "resultSizeEstimate": 1})

    with (
        patch("app.mcp_clients.gmail.supabase", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.get", return_value=threads_resp) as mg,
    ):
        call("gmail.list_messages", {"q": "is:unread", "maxResults": 10}, USER_ID, IDEMPOTENCY_KEY)
    # Verify the q param was forwarded, not a JSON-RPC envelope
    call_kwargs = mg.call_args
    assert call_kwargs.kwargs.get("params", {}).get("q") == "is:unread"
    assert call_kwargs.kwargs.get("params", {}).get("maxResults") == 10


# AC-4
def test_gmail_send_uses_recipient_own_token():
    """_call_gmail_send uses the token from oauth_connections, not a static key."""
    from app.mcp_clients.gmail import call

    user_token = "ya29.user_specific_token"
    mock_sb = _make_token_supabase(user_token)
    captured = {}

    def post_side(url, **kw):
        captured.update(kw.get("headers", {}))
        return _make_httpx_response(200, {"id": "m1", "threadId": "t1"})

    with (
        patch("app.mcp_clients.gmail.supabase", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.post", side_effect=post_side),
    ):
        result = call(
            "gmail.send_message",
            {"to": ["r@e.com"], "subject": "T", "body": "B"},
            USER_ID,
            IDEMPOTENCY_KEY,
        )
    assert user_token in captured.get("Authorization", "")
    assert result["status"] == "success"


# AC-5
def test_gmail_send_skips_duplicate_if_step_already_done():
    """If plan_steps.status=done for this step, no HTTP call is made."""
    from app.mcp_clients.gmail import call

    cached = {"id": "msg_cached", "threadId": "thread_cached"}
    chain = MagicMock()
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = MagicMock(data={"status": "done", "output": cached})
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value = chain
    with patch("app.mcp_clients.gmail.supabase", mock_sb), patch("httpx.post") as mp:
        result = call(
            "gmail.send_message",
            {"to": ["r@e.com"], "subject": "H", "body": "B"},
            USER_ID,
            IDEMPOTENCY_KEY,
        )
    mp.assert_not_called()
    assert result["status"] == "success"
    assert result["output"] == cached


# AC-6
def test_gmail_send_403_returns_clear_reauth_error():
    """A 403 from GMAIL_SEND_URL returns a distinct insufficient-scope message."""
    from app.mcp_clients.gmail import call

    mock_sb = _make_token_supabase()
    resp403 = _make_httpx_response(403)
    resp403.is_success = False
    with (
        patch("app.mcp_clients.gmail.supabase", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.post", return_value=resp403),
    ):
        result = call(
            "gmail.send_message",
            {"to": ["r@e.com"], "subject": "H", "body": "B"},
            USER_ID,
            IDEMPOTENCY_KEY,
        )
    assert result["status"] == "error"
    assert "insufficient scope" in result["error"]
    assert "unauthorized" not in result["error"]


# AC-7
def test_gmail_draft_email_success():
    """gmail.create_draft returns success envelope with output and latency_ms."""
    from app.mcp_clients.gmail import call

    mock_sb = _make_token_supabase()
    # Gmail REST API /drafts returns the draft object directly, not a JSON-RPC envelope
    draft_resp = _make_httpx_response(
        200,
        {"id": "draft_abc", "message": {"id": "msg_abc", "threadId": "t1", "labelIds": ["DRAFT"]}},
    )
    with (
        patch("app.mcp_clients.gmail.supabase", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.post", return_value=draft_resp),
    ):
        result = call(
            "gmail.create_draft",
            {"to": ["a@b.com"], "subject": "D", "body": "B"},
            USER_ID,
            IDEMPOTENCY_KEY,
        )
    assert result["status"] == "success"
    assert result["output"]["id"] == "draft_abc"
    assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0


# AC-8
def test_gmail_send_respects_approval_gate():
    """High-risk steps like gmail.send_message must route to approval_gate."""
    from app.agents.nodes import route_step
    from app.agents.state import Step

    step = Step(
        tool_name="gmail.send_message",
        mcp_server="gmail",
        input_params={"to": ["r@e.com"], "subject": "H", "body": "B"},
    )
    state = _make_state(
        plan=[step],
        risk_flags={
            0: {"risk_tier": "high", "requires_approval": True, "rationale": "irreversible"}
        },
    )

    next_node = route_step(state)
    assert next_node == "approval_gate"


# AC-9
def test_gmail_mcp_token_missing_returns_error():
    """gmail.call returns error and makes no HTTP call when token is absent."""
    from app.mcp_clients.gmail import call

    mock_sb = _make_supabase_no_token()
    with (
        patch("app.mcp_clients.gmail.supabase", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.post") as mp,
        patch("httpx.get") as mg,
    ):
        result = call("gmail.list_messages", {}, USER_ID, IDEMPOTENCY_KEY)
    mp.assert_not_called()
    mg.assert_not_called()
    assert result["status"] == "error"
    assert "token" in result["error"]


# AC-10
def test_gmail_mcp_401_returns_error():
    """A 401 from Gmail REST maps to status=error with unauthorized message."""
    from app.mcp_clients.gmail import call

    mock_sb = _make_token_supabase()
    r = _make_httpx_response(401)
    r.is_success = False
    with (
        patch("app.mcp_clients.gmail.supabase", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.get", return_value=r),  # list_messages uses GET
    ):
        result = call("gmail.list_messages", {}, USER_ID, IDEMPOTENCY_KEY)
    assert result["status"] == "error"
    assert "unauthorized" in result["error"]


# AC-11
def test_gmail_mcp_429_returns_rate_limited():
    """A 429 from Gmail REST maps to status=rate_limited."""
    from app.mcp_clients.gmail import call

    mock_sb = _make_token_supabase()
    r = _make_httpx_response(429)
    r.is_success = False
    with (
        patch("app.mcp_clients.gmail.supabase", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.get", return_value=r),  # list_messages uses GET
    ):
        result = call("gmail.list_messages", {}, USER_ID, IDEMPOTENCY_KEY)
    assert result["status"] == "rate_limited"


# AC-12
def test_gmail_unknown_tool_returns_error():
    """gmail.call with an unrecognised tool_name returns a clean error."""
    from app.mcp_clients.gmail import call

    with patch("httpx.post") as mp:
        result = call("gmail.nonexistent", {}, USER_ID, IDEMPOTENCY_KEY)
    mp.assert_not_called()
    assert result["status"] == "error"
    assert "unknown tool" in result["error"]
    assert "gmail.nonexistent" in result["error"]


# AC-13
def test_call_tool_routes_gmail_server():
    """call_tool(mcp_server='gmail') resolves to gmail.call via _ROUTER."""
    from app.mcp_clients import call_tool

    with patch("app.mcp_clients.gmail.call") as mc:
        mc.return_value = {"status": "success", "output": {}, "error": None, "latency_ms": 10}
        result = call_tool(
            "gmail.list_messages", "gmail", {"query": "is:unread"}, USER_ID, IDEMPOTENCY_KEY
        )
    mc.assert_called_once_with(
        tool_name="gmail.list_messages",
        input_params={"query": "is:unread"},
        user_id=USER_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        task_id="unknown",
    )
    assert result["status"] == "success"
