"""Tests for the D17 Slack MCP client.

All external calls (Supabase, httpx) are mocked — no live DB or network needed.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import httpx

USER_ID = str(uuid.uuid4())
PLAN_ID = str(uuid.uuid4())
SLACK_TOKEN_PLAINTEXT = "xoxb-test-token"
IDEMPOTENCY_KEY = f"{PLAN_ID}:0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_supabase(token=SLACK_TOKEN_PLAINTEXT):
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


def _make_json_response(status_code, json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.headers = {"content-type": "application/json"}
    resp.json.return_value = json_body or {}
    resp.text = ""
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_slack_call_routes_to_mcp_endpoint():
    """All slack.* tools POST to SLACK_MCP_URL."""
    from app.mcp_clients.slack import SLACK_MCP_URL, call

    mock_sb = _make_supabase()
    tool_resp = _make_json_response(200, {"jsonrpc": "2.0", "result": {"channels": []}})
    posted_urls = []

    def post_side(url, **kw):
        posted_urls.append(url)
        return tool_resp

    with (
        patch("app.mcp_clients.slack.supabase", mock_sb),
        patch("app.mcp_clients.slack.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", side_effect=post_side),
    ):
        result = call("slack.list_channels", {}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "success"
    assert all(url == SLACK_MCP_URL for url in posted_urls)


def test_slack_token_fernet_decrypted():
    """_fetch_slack_token decrypts with Fernet when ENCRYPTION_KEY is set."""
    from cryptography.fernet import Fernet

    from app.mcp_clients.slack import _fetch_slack_token

    key = Fernet.generate_key().decode()
    fernet = Fernet(key.encode())
    encrypted = fernet.encrypt(SLACK_TOKEN_PLAINTEXT.encode()).decode()

    mock_sb = _make_supabase(token=encrypted)
    mock_settings = MagicMock(ENCRYPTION_KEY=key)

    with (
        patch("app.mcp_clients.slack.supabase", mock_sb),
        patch("app.mcp_clients.slack.settings", mock_settings),
    ):
        token = _fetch_slack_token(USER_ID)

    assert token == SLACK_TOKEN_PLAINTEXT


def test_slack_tool_name_mapping():
    """Test that slack.post_message_dm maps to post_message correctly."""
    from app.mcp_clients.slack import call

    mock_sb = _make_supabase()
    tool_resp = _make_json_response(200, {"jsonrpc": "2.0", "result": {"ok": True}})
    posted_bodies = []

    def post_side(url, **kw):
        posted_bodies.append(kw.get("json"))
        return tool_resp

    # We must patch table properly for _already_done precheck to return None
    def table_side(name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.single.return_value = chain
        if name == "plan_steps":
            chain.execute.return_value = MagicMock(data=None)  # No cached result
        else:
            chain.execute.return_value = MagicMock(data={"access_token": SLACK_TOKEN_PLAINTEXT})
        return chain

    mock_sb.table.side_effect = table_side

    with (
        patch("app.mcp_clients.slack.supabase", mock_sb),
        patch("app.mcp_clients.slack.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", side_effect=post_side),
    ):
        call("slack.post_message_dm", {"channel": "C123", "text": "hi"}, USER_ID, IDEMPOTENCY_KEY)

    assert len(posted_bodies) == 1
    body = posted_bodies[0]
    assert body["params"]["name"] == "post_message"
    assert body["params"]["arguments"]["channel"] == "C123"


def test_slack_idempotency_precheck():
    """If plan_steps shows done for a mutating tool, no MCP call is made."""
    from app.mcp_clients.slack import call

    cached_output = {"ts": "12345.678"}

    chain = MagicMock()
    chain.eq.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = MagicMock(data={"status": "done", "output": cached_output})
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value = chain

    with (
        patch("app.mcp_clients.slack.supabase", mock_sb),
        patch("httpx.post") as mp,
    ):
        result = call(
            "slack.post_message_channel", {"channel": "C1", "text": "t"}, USER_ID, IDEMPOTENCY_KEY
        )

    mp.assert_not_called()
    assert result["status"] == "success"
    assert result["output"] == cached_output


def test_slack_401_returns_auth_expired():
    """A 401 returns AUTH_EXPIRED error."""
    from app.mcp_clients.slack import call

    mock_sb = _make_supabase()
    resp_401 = _make_json_response(401)

    with (
        patch("app.mcp_clients.slack.supabase", mock_sb),
        patch("app.mcp_clients.slack.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", return_value=resp_401),
    ):
        result = call("slack.list_channels", {}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "error"
    assert result["error"]["code"] == "AUTH_EXPIRED"


def test_slack_429_returns_rate_limited():
    """429 from Slack MCP → status=rate_limited, code=RATE_LIMITED."""
    from app.mcp_clients.slack import call

    mock_sb = _make_supabase()
    resp_429 = _make_json_response(429)

    with (
        patch("app.mcp_clients.slack.supabase", mock_sb),
        patch("app.mcp_clients.slack.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", return_value=resp_429),
    ):
        result = call("slack.list_channels", {}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "rate_limited"
    assert result["error"]["code"] == "RATE_LIMITED"


def test_slack_timeout_returns_timeout_error():
    """httpx.TimeoutException → TIMEOUT error code."""
    from app.mcp_clients.slack import call

    mock_sb = _make_supabase()

    with (
        patch("app.mcp_clients.slack.supabase", mock_sb),
        patch("app.mcp_clients.slack.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", side_effect=httpx.TimeoutException("timed out")),
    ):
        result = call("slack.list_channels", {}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "error"
    assert result["error"]["code"] == "TIMEOUT"


def test_slack_unknown_tool_returns_invalid_params():
    """Unknown tool_name → INVALID_PARAMS, no HTTP call."""
    from app.mcp_clients.slack import call

    with patch("httpx.post") as mp:
        result = call("slack.nonexistent", {}, USER_ID, IDEMPOTENCY_KEY)

    mp.assert_not_called()
    assert result["status"] == "error"
    assert result["error"]["code"] == "INVALID_PARAMS"
    assert "slack.nonexistent" in result["error"]["message"]


def test_slack_5xx_returns_provider_error():
    """A 500 from Slack MCP → PROVIDER_ERROR."""
    from app.mcp_clients.slack import call

    mock_sb = _make_supabase()
    resp_500 = _make_json_response(500)

    with (
        patch("app.mcp_clients.slack.supabase", mock_sb),
        patch("app.mcp_clients.slack.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", return_value=resp_500),
    ):
        result = call("slack.list_channels", {}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "error"
    assert result["error"]["code"] == "PROVIDER_ERROR"


def test_slack_token_missing_returns_auth_expired():
    """No token in oauth_connections → AUTH_EXPIRED."""
    from app.mcp_clients.slack import call

    mock_sb = _make_supabase_no_token()

    with (
        patch("app.mcp_clients.slack.supabase", mock_sb),
        patch("app.mcp_clients.slack.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post") as mp,
    ):
        result = call("slack.list_channels", {}, USER_ID, IDEMPOTENCY_KEY)

    mp.assert_not_called()
    assert result["status"] == "error"
    assert result["error"]["code"] == "AUTH_EXPIRED"


# ---------------------------------------------------------------------------
# Router integration
# ---------------------------------------------------------------------------


def test_call_tool_routes_slack_server():
    """call_tool(mcp_server='slack') resolves to slack.call via _ROUTER."""
    from app.mcp_clients import call_tool

    with patch("app.mcp_clients.slack.call") as mc:
        mc.return_value = {"status": "success", "output": {}, "error": None, "latency_ms": 5}
        result = call_tool("slack.list_channels", "slack", {}, USER_ID, IDEMPOTENCY_KEY)

    mc.assert_called_once_with(
        tool_name="slack.list_channels",
        input_params={},
        user_id=USER_ID,
        idempotency_key=IDEMPOTENCY_KEY,
    )
    assert result["status"] == "success"
