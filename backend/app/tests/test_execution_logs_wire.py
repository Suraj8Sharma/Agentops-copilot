"""Tests for D22 — execution_logs wire-up across all 4 MCP clients.

All external calls (Supabase, httpx) are mocked — no live DB or network needed.

Test map vs. spec acceptance criteria (d22-execution-logs-wire.md §7):

  Calendar
    test_calendar_tool_called_writes_log              -> tool_called row on happy path
    test_calendar_tool_result_writes_log              -> tool_result row on success
    test_calendar_error_writes_log                    -> error row on 401
    test_calendar_log_failure_does_not_crash_call     -> log exception doesn't propagate

  Gmail (MCP path)
    test_gmail_tool_called_writes_log                 -> tool_called row on happy path
    test_gmail_tool_result_writes_log                 -> tool_result row on success
    test_gmail_error_writes_log                       -> error row on 401
    test_gmail_log_failure_does_not_crash_call        -> best-effort

  Gmail (send / REST path)
    test_gmail_send_tool_called_writes_log            -> tool_called before POST
    test_gmail_send_tool_result_writes_log            -> tool_result on 200
    test_gmail_send_error_writes_log                  -> error row on 403

  GitHub
    test_github_tool_called_writes_log                -> tool_called row
    test_github_tool_result_writes_log                -> tool_result row on success
    test_github_error_writes_log                      -> error row on 401
    test_github_log_failure_does_not_crash_call       -> best-effort

  Slack
    test_slack_tool_called_writes_log                 -> tool_called row
    test_slack_tool_result_writes_log                 -> tool_result row on success
    test_slack_error_writes_log                       -> error row on 429
    test_slack_log_failure_does_not_crash_call        -> best-effort

  Router integration
    test_call_tool_passes_task_id_to_calendar         -> task_id flows through __init__.call_tool
    test_call_tool_passes_task_id_to_gmail            -> task_id flows through __init__.call_tool
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import httpx

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TASK_ID = str(uuid.uuid4())
PLAN_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())
IDEMPOTENCY_KEY = f"{PLAN_ID}:0"

GOOGLE_TOKEN = "ya29.test_google_token"
GITHUB_TOKEN = "gho_test_github_token"
SLACK_TOKEN = "xoxb-test-slack-token"


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------


def _supabase_with_token(token: str) -> MagicMock:
    """Supabase mock that returns ``token`` from oauth_connections and
    accepts any table().insert().execute() call without error."""
    mock = MagicMock()

    # Select chain (for token fetch)
    sel = MagicMock()
    sel.eq.return_value = sel
    sel.single.return_value = sel
    sel.execute.return_value = MagicMock(data={"access_token": token})
    mock.table.return_value.select.return_value = sel

    # Insert chain (for execution_logs writes)
    ins = MagicMock()
    ins.execute.return_value = MagicMock(data=[{"id": str(uuid.uuid4())}])
    mock.table.return_value.insert.return_value = ins

    return mock


def _supabase_with_no_token() -> MagicMock:
    mock = MagicMock()
    sel = MagicMock()
    sel.eq.return_value = sel
    sel.single.return_value = sel
    sel.execute.return_value = MagicMock(data=None)
    mock.table.return_value.select.return_value = sel
    ins = MagicMock()
    ins.execute.return_value = MagicMock(data=[])
    mock.table.return_value.insert.return_value = ins
    return mock


def _supabase_insert_raises() -> MagicMock:
    """Supabase mock where token fetch succeeds but insert raises."""
    mock = MagicMock()
    sel = MagicMock()
    sel.eq.return_value = sel
    sel.single.return_value = sel
    sel.execute.return_value = MagicMock(data={"access_token": GOOGLE_TOKEN})
    mock.table.return_value.select.return_value = sel

    ins = MagicMock()
    ins.execute.side_effect = RuntimeError("DB unavailable")
    mock.table.return_value.insert.return_value = ins
    return mock


def _json_response(status_code: int = 200, body: dict | None = None) -> MagicMock:
    """Plain JSON httpx response mock (used by calendar / gmail)."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = body or {}
    return resp


def _sse_response(
    status_code: int = 200, result: dict | None = None, error: dict | None = None
) -> MagicMock:  # noqa: E501
    """SSE-style httpx response mock (used by github)."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.headers = {"Mcp-Session-Id": "sess-test"}

    rpc: dict = {"jsonrpc": "2.0", "id": "1"}
    if error:
        rpc["error"] = error
    else:
        rpc["result"] = result or {}

    sse_line = f"data: {json.dumps(rpc)}\n\n"
    resp.text = sse_line
    resp.iter_lines.return_value = iter(sse_line.splitlines())
    resp.content = sse_line.encode()
    return resp


# ===========================================================================
# CALENDAR
# ===========================================================================


class TestCalendarExecutionLogs:
    """calendar.py — _log_event_calendar wired into call()."""

    MCP_SUCCESS_BODY = {
        "jsonrpc": "2.0",
        "id": IDEMPOTENCY_KEY,
        "result": {"events": []},
    }

    def test_tool_called_writes_log(self):
        """tool_called row is inserted before the HTTP call."""
        mock_supabase = _supabase_with_token(GOOGLE_TOKEN)
        http_resp = _json_response(200, self.MCP_SUCCESS_BODY)

        with (
            patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import calendar

            calendar.call(
                tool_name="calendar.list_events",
                input_params={"date_range": "this_week"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        inserts = [c for c in mock_supabase.table.return_value.insert.call_args_list]
        payloads = [c.args[0] for c in inserts]
        tool_called_rows = [p for p in payloads if p.get("event_type") == "tool_called"]

        assert len(tool_called_rows) >= 1
        row = tool_called_rows[0]
        assert row["task_id"] == TASK_ID
        assert row["agent_name"] == "mcp_calendar"
        assert row["payload"]["tool_name"] == "calendar.list_events"
        assert row["payload"]["mcp_server"] == "calendar"

    def test_tool_result_writes_log(self):
        """tool_result row is inserted on success."""
        mock_supabase = _supabase_with_token(GOOGLE_TOKEN)
        http_resp = _json_response(200, self.MCP_SUCCESS_BODY)

        with (
            patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import calendar

            result = calendar.call(
                tool_name="calendar.list_events",
                input_params={"date_range": "this_week"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "success"

        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        result_rows = [p for p in inserts if p.get("event_type") == "tool_result"]
        assert len(result_rows) >= 1
        assert result_rows[0]["agent_name"] == "mcp_calendar"
        assert result_rows[0]["payload"]["status"] == "success"

    def test_error_writes_log(self):
        """error row is inserted on 401."""
        mock_supabase = _supabase_with_token(GOOGLE_TOKEN)
        http_resp = _json_response(401)

        with (
            patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import calendar

            result = calendar.call(
                tool_name="calendar.list_events",
                input_params={},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "error"

        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        error_rows = [p for p in inserts if p.get("event_type") == "error"]
        assert len(error_rows) >= 1
        assert error_rows[0]["payload"]["error_code"] == "AUTH_EXPIRED"

    def test_log_failure_does_not_crash_call(self):
        """If the Supabase insert raises, the MCP result is still returned."""
        mock_supabase = _supabase_insert_raises()
        http_resp = _json_response(200, self.MCP_SUCCESS_BODY)

        with (
            patch("app.mcp_clients.calendar.supabase_admin", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import calendar

            result = calendar.call(
                tool_name="calendar.list_events",
                input_params={},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        # Despite the insert raising, call() must not propagate
        assert result["status"] == "success"


# ===========================================================================
# GMAIL — MCP path
# ===========================================================================


class TestGmailMcpExecutionLogs:
    """gmail.py — _call_gmail_mcp path (_log_event_gmail)."""

    MCP_SUCCESS_BODY = {
        "jsonrpc": "2.0",
        "id": IDEMPOTENCY_KEY,
        "result": {"threads": []},
    }

    def test_tool_called_writes_log(self):
        mock_supabase = _supabase_with_token(GOOGLE_TOKEN)
        http_resp = _json_response(200, self.MCP_SUCCESS_BODY)

        with (
            patch("app.mcp_clients.gmail.supabase", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import gmail

            gmail.call(
                tool_name="gmail.list_messages",
                input_params={"query": "is:unread"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        tool_called = [p for p in inserts if p.get("event_type") == "tool_called"]
        assert len(tool_called) >= 1
        assert tool_called[0]["task_id"] == TASK_ID
        assert tool_called[0]["agent_name"] == "mcp_gmail"
        assert tool_called[0]["payload"]["mcp_server"] == "gmail"

    def test_tool_result_writes_log(self):
        mock_supabase = _supabase_with_token(GOOGLE_TOKEN)
        http_resp = _json_response(200, self.MCP_SUCCESS_BODY)

        with (
            patch("app.mcp_clients.gmail.supabase", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import gmail

            result = gmail.call(
                tool_name="gmail.list_messages",
                input_params={"query": "is:unread"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "success"
        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        result_rows = [p for p in inserts if p.get("event_type") == "tool_result"]
        assert len(result_rows) >= 1
        assert result_rows[0]["payload"]["status"] == "success"

    def test_error_writes_log(self):
        mock_supabase = _supabase_with_token(GOOGLE_TOKEN)
        http_resp = _json_response(401)

        with (
            patch("app.mcp_clients.gmail.supabase", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import gmail

            result = gmail.call(
                tool_name="gmail.list_messages",
                input_params={},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "error"
        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        error_rows = [p for p in inserts if p.get("event_type") == "error"]
        assert len(error_rows) >= 1
        assert error_rows[0]["payload"]["error_code"] == "AUTH_EXPIRED"

    def test_log_failure_does_not_crash_call(self):
        mock_supabase = _supabase_insert_raises()
        http_resp = _json_response(200, self.MCP_SUCCESS_BODY)

        with (
            patch("app.mcp_clients.gmail.supabase", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import gmail

            result = gmail.call(
                tool_name="gmail.list_messages",
                input_params={},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "success"


# ===========================================================================
# GMAIL — send / REST path
# ===========================================================================


class TestGmailSendExecutionLogs:
    """gmail.py — _call_gmail_send path."""

    def _make_send_supabase(self):
        """Supabase where both token fetch and no-cached-step return correctly."""
        mock = MagicMock()

        # Token fetch chain
        sel = MagicMock()
        sel.eq.return_value = sel
        sel.single.return_value = sel
        sel.execute.return_value = MagicMock(data={"access_token": GOOGLE_TOKEN})
        mock.table.return_value.select.return_value = sel

        # plan_steps status check (idempotency) — no cached result
        # The chain is the same mock so status check returns empty
        sel.execute.return_value = MagicMock(data=None)

        # Insert chain for execution_logs
        ins = MagicMock()
        ins.execute.return_value = MagicMock(data=[{"id": str(uuid.uuid4())}])
        mock.table.return_value.insert.return_value = ins

        return mock

    def test_send_tool_called_writes_log(self):
        mock_supabase = _supabase_with_token(GOOGLE_TOKEN)
        http_resp = _json_response(200, {"id": "msg-abc", "threadId": "thread-1"})

        with (
            patch("app.mcp_clients.gmail.supabase", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import gmail

            gmail.call(
                tool_name="gmail.send_message",
                input_params={"to": ["test@example.com"], "subject": "Hi", "body": "Hello"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        tool_called = [p for p in inserts if p.get("event_type") == "tool_called"]
        assert len(tool_called) >= 1
        assert tool_called[0]["agent_name"] == "mcp_gmail"
        assert tool_called[0]["payload"]["tool_name"] == "gmail.send_message"

    def test_send_tool_result_writes_log(self):
        mock_supabase = _supabase_with_token(GOOGLE_TOKEN)
        http_resp = _json_response(200, {"id": "msg-abc", "threadId": "thread-1"})

        with (
            patch("app.mcp_clients.gmail.supabase", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import gmail

            result = gmail.call(
                tool_name="gmail.send_message",
                input_params={"to": ["test@example.com"], "subject": "Hi", "body": "Hello"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "success"
        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        result_rows = [p for p in inserts if p.get("event_type") == "tool_result"]
        assert len(result_rows) >= 1
        assert result_rows[0]["payload"]["output"]["id"] == "msg-abc"

    def test_send_error_writes_log(self):
        """403 insufficient scope → error row with INSUFFICIENT_SCOPE."""
        mock_supabase = _supabase_with_token(GOOGLE_TOKEN)
        http_resp = _json_response(403)

        with (
            patch("app.mcp_clients.gmail.supabase", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import gmail

            result = gmail.call(
                tool_name="gmail.send_message",
                input_params={"to": ["x@y.com"], "subject": "test", "body": "test"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "error"
        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        error_rows = [p for p in inserts if p.get("event_type") == "error"]
        assert len(error_rows) >= 1
        assert error_rows[0]["payload"]["error_code"] == "INSUFFICIENT_SCOPE"


# ===========================================================================
# GITHUB
# ===========================================================================


def _github_supabase(token: str = GITHUB_TOKEN) -> MagicMock:
    """GitHub needs extra chains: oauth_connections select + plan_steps select (idempotency)."""
    mock = MagicMock()

    sel = MagicMock()
    sel.eq.return_value = sel
    sel.single.return_value = sel
    sel.execute.return_value = MagicMock(data={"access_token": token})
    mock.table.return_value.select.return_value = sel

    ins = MagicMock()
    ins.execute.return_value = MagicMock(data=[{"id": str(uuid.uuid4())}])
    mock.table.return_value.insert.return_value = ins

    return mock


def _github_sse_success() -> MagicMock:
    body = {
        "jsonrpc": "2.0",
        "id": IDEMPOTENCY_KEY,
        "result": {"number": 42, "url": "https://github.com/x/y/issues/42"},
    }
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.is_success = True
    resp.headers = {"Mcp-Session-Id": "sess-github-1"}
    sse = f"data: {json.dumps(body)}\n\n"
    resp.text = sse
    resp.iter_lines.return_value = iter(sse.splitlines())
    resp.content = sse.encode()
    return resp


class TestGitHubExecutionLogs:
    def _init_resp(self) -> MagicMock:
        """Mock for the GitHub MCP initialize handshake — must have mcp-session-id header."""
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.is_success = True
        resp.headers = {"mcp-session-id": "sess-github-1"}  # lowercase — matches resp.headers.get()
        resp.text = ""
        resp.content = b""
        resp.iter_lines.return_value = iter([])
        return resp

    def test_tool_called_writes_log(self):
        mock_supabase = _github_supabase()
        # post is called 3 times: initialize, notifications/initialized, tool call
        with (
            patch("app.mcp_clients.github.supabase", mock_supabase),
            patch("app.mcp_clients.github._session_cache", {}),
            patch(
                "httpx.post", side_effect=[self._init_resp(), MagicMock(), _github_sse_success()]
            ),  # noqa: E501
        ):
            from app.mcp_clients import github

            github.call(
                tool_name="github.create_issue",
                input_params={"repo": "owner/repo", "title": "Bug", "body": "Details"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        tool_called = [p for p in inserts if p.get("event_type") == "tool_called"]
        assert len(tool_called) >= 1
        assert tool_called[0]["task_id"] == TASK_ID
        assert tool_called[0]["agent_name"] == "mcp_github"

    def test_tool_result_writes_log(self):
        mock_supabase = _github_supabase()
        with (
            patch("app.mcp_clients.github.supabase", mock_supabase),
            patch("app.mcp_clients.github._session_cache", {}),
            patch(
                "httpx.post", side_effect=[self._init_resp(), MagicMock(), _github_sse_success()]
            ),  # noqa: E501
        ):
            from app.mcp_clients import github

            result = github.call(
                tool_name="github.create_issue",
                input_params={"repo": "owner/repo", "title": "Bug", "body": "Details"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "success"
        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        result_rows = [p for p in inserts if p.get("event_type") == "tool_result"]
        assert len(result_rows) >= 1
        assert result_rows[0]["payload"]["status"] == "success"

    def test_error_writes_log(self):
        """401 from GitHub MCP → error row with AUTH_EXPIRED."""
        mock_supabase = _github_supabase()
        auth_fail = MagicMock(spec=httpx.Response)
        auth_fail.status_code = 401
        auth_fail.is_success = False

        with (
            patch("app.mcp_clients.github.supabase", mock_supabase),
            patch("app.mcp_clients.github._session_cache", {}),
            patch("httpx.post", side_effect=[self._init_resp(), MagicMock(), auth_fail]),
        ):
            from app.mcp_clients import github

            result = github.call(
                tool_name="github.create_issue",
                input_params={"repo": "owner/repo", "title": "Bug", "body": "Details"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "error"
        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        error_rows = [p for p in inserts if p.get("event_type") == "error"]
        assert len(error_rows) >= 1
        assert error_rows[0]["payload"]["error_code"] == "AUTH_EXPIRED"

    def test_log_failure_does_not_crash_call(self):
        """If the execution_logs insert raises, the MCP result still comes back."""
        mock_supabase = _github_supabase()
        ins = MagicMock()
        ins.execute.side_effect = RuntimeError("DB down")
        mock_supabase.table.return_value.insert.return_value = ins

        with (
            patch("app.mcp_clients.github.supabase", mock_supabase),
            patch("app.mcp_clients.github._session_cache", {}),
            patch(
                "httpx.post", side_effect=[self._init_resp(), MagicMock(), _github_sse_success()]
            ),  # noqa: E501
        ):
            from app.mcp_clients import github

            result = github.call(
                tool_name="github.create_issue",
                input_params={"repo": "owner/repo", "title": "Bug", "body": "Details"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "success"


# ===========================================================================
# SLACK
# ===========================================================================


def _slack_supabase(token: str = SLACK_TOKEN) -> MagicMock:
    mock = MagicMock()
    sel = MagicMock()
    sel.eq.return_value = sel
    sel.single.return_value = sel
    sel.execute.return_value = MagicMock(data={"access_token": token})
    mock.table.return_value.select.return_value = sel

    ins = MagicMock()
    ins.execute.return_value = MagicMock(data=[{"id": str(uuid.uuid4())}])
    mock.table.return_value.insert.return_value = ins

    return mock


def _slack_success_resp() -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.is_success = True
    resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": IDEMPOTENCY_KEY,
        "result": {"ok": True, "ts": "1234.5678"},
    }  # noqa: E501
    return resp


class TestSlackExecutionLogs:
    def test_tool_called_writes_log(self):
        mock_supabase = _slack_supabase()

        with (
            patch("app.mcp_clients.slack.supabase", mock_supabase),
            patch("httpx.post", return_value=_slack_success_resp()),
        ):
            from app.mcp_clients import slack

            slack.call(
                tool_name="slack.post_message_channel",
                input_params={"channel": "#general", "text": "Hello"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        tool_called = [p for p in inserts if p.get("event_type") == "tool_called"]
        assert len(tool_called) >= 1
        assert tool_called[0]["task_id"] == TASK_ID
        assert tool_called[0]["agent_name"] == "mcp_slack"
        assert tool_called[0]["payload"]["mcp_server"] == "slack"

    def test_tool_result_writes_log(self):
        mock_supabase = _slack_supabase()

        with (
            patch("app.mcp_clients.slack.supabase", mock_supabase),
            patch("httpx.post", return_value=_slack_success_resp()),
        ):
            from app.mcp_clients import slack

            result = slack.call(
                tool_name="slack.post_message_channel",
                input_params={"channel": "#general", "text": "Hello"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "success"
        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        result_rows = [p for p in inserts if p.get("event_type") == "tool_result"]
        assert len(result_rows) >= 1
        assert result_rows[0]["payload"]["status"] == "success"

    def test_error_writes_log(self):
        """429 rate limit → error row with RATE_LIMITED."""
        mock_supabase = _slack_supabase()
        http_resp = MagicMock(spec=httpx.Response)
        http_resp.status_code = 429
        http_resp.is_success = False

        with (
            patch("app.mcp_clients.slack.supabase", mock_supabase),
            patch("httpx.post", return_value=http_resp),
        ):
            from app.mcp_clients import slack

            result = slack.call(
                tool_name="slack.post_message_channel",
                input_params={"channel": "#general", "text": "Hello"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "rate_limited"
        inserts = [c.args[0] for c in mock_supabase.table.return_value.insert.call_args_list]
        error_rows = [p for p in inserts if p.get("event_type") == "error"]
        assert len(error_rows) >= 1
        assert error_rows[0]["payload"]["error_code"] == "RATE_LIMITED"

    def test_log_failure_does_not_crash_call(self):
        mock_supabase = _slack_supabase()
        ins = MagicMock()
        ins.execute.side_effect = RuntimeError("DB down")
        mock_supabase.table.return_value.insert.return_value = ins

        with (
            patch("app.mcp_clients.slack.supabase", mock_supabase),
            patch("httpx.post", return_value=_slack_success_resp()),
        ):
            from app.mcp_clients import slack

            result = slack.call(
                tool_name="slack.post_message_channel",
                input_params={"channel": "#general", "text": "Hello"},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        assert result["status"] == "success"


# ===========================================================================
# ROUTER INTEGRATION — task_id flows through call_tool()
# ===========================================================================


class TestCallToolTaskIdThreading:
    """Verify __init__.call_tool forwards task_id to the correct client."""

    def test_call_tool_passes_task_id_to_calendar(self):
        mock_cal = MagicMock()
        mock_cal.call.return_value = {
            "status": "success",
            "output": {},
            "error": None,
            "latency_ms": 5,
        }  # noqa: E501

        import app.mcp_clients as router_mod

        with patch.dict(router_mod._ROUTER, {"calendar": mock_cal}):
            router_mod.call_tool(
                tool_name="calendar.list_events",
                mcp_server="calendar",
                input_params={},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        mock_cal.call.assert_called_once_with(
            tool_name="calendar.list_events",
            input_params={},
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )

    def test_call_tool_passes_task_id_to_gmail(self):
        mock_gmail = MagicMock()
        mock_gmail.call.return_value = {
            "status": "success",
            "output": {},
            "error": None,
            "latency_ms": 5,
        }  # noqa: E501

        import app.mcp_clients as router_mod

        with patch.dict(router_mod._ROUTER, {"gmail": mock_gmail}):
            router_mod.call_tool(
                tool_name="gmail.send_message",
                mcp_server="gmail",
                input_params={},
                user_id=USER_ID,
                idempotency_key=IDEMPOTENCY_KEY,
                task_id=TASK_ID,
            )

        mock_gmail.call.assert_called_once_with(
            tool_name="gmail.send_message",
            input_params={},
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )
