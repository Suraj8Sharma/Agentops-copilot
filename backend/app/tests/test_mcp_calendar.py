"""MCP integration and unit tests for Google Calendar REST client.

Manual §14, §15.4 (D29, Suraj): MCP integration test suite.
Satisfies the three calendar named tests from Manual §15.4:
  - test_calendar_create_event_success
  - test_calendar_list_events_returns_expected_range
  - test_calendar_invalid_params_returns_clear_error

All external calls (Supabase, httpx) are mocked — 100% offline, zero live network/secrets.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import httpx

from app.mcp_clients.calendar import call

USER_ID = str(uuid.uuid4())
TASK_ID = str(uuid.uuid4())
PLAN_ID = str(uuid.uuid4())
IDEMPOTENCY_KEY = f"{PLAN_ID}:0"
GOOGLE_TOKEN = "ya29.test_valid_calendar_token"

REFRESH_PATCH = "app.mcp_clients.google_token_refresh.supabase_admin"


def _make_supabase_mock(token: str = GOOGLE_TOKEN) -> MagicMock:
    """Build a mock Supabase client for calendar token retrieval and execution logs."""
    mock = MagicMock()

    def table_side_effect(name: str):
        t = MagicMock()

        def select_side_effect(*args, **kwargs):
            s = MagicMock()
            s.eq.return_value = s
            s.limit.return_value = s
            s.execute.return_value = MagicMock(
                data=[
                    {
                        "access_token": token,
                        "refresh_token": None,
                        "expires_at": "2099-01-01T00:00:00+00:00",
                        "status": "active",
                    }
                ]
            )
            return s

        def insert_side_effect(payload: dict[str, Any]):
            i = MagicMock()
            i.execute.return_value = MagicMock(data=[{"id": str(uuid.uuid4())}])
            return i

        t.select.side_effect = select_side_effect
        t.insert.side_effect = insert_side_effect
        return t

    mock.table.side_effect = table_side_effect
    return mock


def _make_httpx_response(status_code: int = 200, json_body: dict | None = None) -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_body or {}
    return resp


# ---------------------------------------------------------------------------
# Manual §15.4 Named Test 1
# ---------------------------------------------------------------------------


def test_calendar_create_event_success():
    """Manual §15.4 named test: calendar.create_event_internal_only returns success.

    Asserts:
      - Dispatches POST to Google Calendar REST API v3
      - Forwards Bearer token and X-Idempotency-Token header
      - Returns status 'success', populated output, and latency_ms >= 0
    """
    mock_sb = _make_supabase_mock()
    event_payload = {
        "id": "evt_d29_001",
        "status": "confirmed",
        "summary": "Team Sync",
        "htmlLink": "https://calendar.google.com/event?eid=evt_d29_001",
    }
    mock_post_resp = _make_httpx_response(200, event_payload)

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.post", return_value=mock_post_resp) as mock_post,
    ):
        result = call(
            tool_name="calendar.create_event_internal_only",
            input_params={
                "summary": "Team Sync",
                "description": "Weekly status meeting",
                "start": {"dateTime": "2026-09-25T10:00:00Z"},
                "end": {"dateTime": "2026-09-25T10:30:00Z"},
            },
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )

    assert result["status"] == "success"
    assert result["output"]["id"] == "evt_d29_001"
    assert result["output"]["status"] == "confirmed"
    assert result["error"] is None
    assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"] == f"Bearer {GOOGLE_TOKEN}"
    assert kwargs["headers"]["X-Idempotency-Token"] == IDEMPOTENCY_KEY
    assert kwargs["json"]["summary"] == "Team Sync"


# ---------------------------------------------------------------------------
# Manual §15.4 Named Test 2
# ---------------------------------------------------------------------------


def test_calendar_list_events_returns_expected_range():
    """Manual §15.4 named test: calendar.list_events queries range and returns items.

    Asserts:
      - Dispatches GET to /calendars/primary/events
      - Forwards timeMin, timeMax, and maxResults query parameters
      - Returns status 'success', items list, and latency_ms >= 0
    """
    mock_sb = _make_supabase_mock()
    list_payload = {
        "kind": "calendar#events",
        "items": [
            {"id": "ev_01", "summary": "Morning Standup"},
            {"id": "ev_02", "summary": "1:1 Review"},
        ],
    }
    mock_get_resp = _make_httpx_response(200, list_payload)

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.get", return_value=mock_get_resp) as mock_get,
    ):
        result = call(
            tool_name="calendar.list_events",
            input_params={
                "timeMin": "2026-09-25T00:00:00Z",
                "timeMax": "2026-09-25T23:59:59Z",
                "maxResults": 10,
            },
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )

    assert result["status"] == "success"
    assert len(result["output"]["items"]) == 2
    assert result["output"]["items"][0]["id"] == "ev_01"
    assert result["error"] is None
    assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0

    mock_get.assert_called_once()
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["timeMin"] == "2026-09-25T00:00:00Z"
    assert kwargs["params"]["timeMax"] == "2026-09-25T23:59:59Z"
    assert kwargs["params"]["maxResults"] == 10
    assert kwargs["headers"]["Authorization"] == f"Bearer {GOOGLE_TOKEN}"


# ---------------------------------------------------------------------------
# Manual §15.4 Named Test 3
# ---------------------------------------------------------------------------


def test_calendar_invalid_params_returns_clear_error():
    """Manual §15.4 named test: missing required params return clear error envelope.

    Asserts:
      - delete_event without eventId returns clear missing param error
      - update_event without eventId returns clear missing param error
      - unknown tool name returns unknown tool error
      - Zero outbound HTTP requests made
      - Never raises uncaught exceptions
    """
    mock_sb = _make_supabase_mock()

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.delete") as mock_delete,
        patch("httpx.patch") as mock_patch,
        patch("httpx.post") as mock_post,
    ):
        # 1. delete_event missing eventId
        del_res = call(
            tool_name="calendar.delete_event",
            input_params={},
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )
        assert del_res["status"] == "error"
        assert del_res["output"] is None
        assert "missing required param: eventId" in del_res["error"]

        # 2. update_event missing eventId
        upd_res = call(
            tool_name="calendar.update_event",
            input_params={"summary": "Updated"},
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )
        assert upd_res["status"] == "error"
        assert upd_res["output"] is None
        assert "missing required param: eventId" in upd_res["error"]

        # 3. Unknown calendar tool
        unknown_res = call(
            tool_name="calendar.nonexistent_operation",
            input_params={},
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )
        assert unknown_res["status"] == "error"
        assert unknown_res["output"] is None
        assert "unknown tool: calendar.nonexistent_operation" in unknown_res["error"]

    mock_delete.assert_not_called()
    mock_patch.assert_not_called()
    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Extended Provider Unit & Contract Cases
# ---------------------------------------------------------------------------


def test_calendar_create_event_external_attendee_send_updates():
    """calendar.create_event_external_attendee sets sendUpdates='all'."""
    mock_sb = _make_supabase_mock()
    mock_post_resp = _make_httpx_response(200, {"id": "evt_ext_1", "status": "confirmed"})

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.post", return_value=mock_post_resp) as mock_post,
    ):
        result = call(
            tool_name="calendar.create_event_external_attendee",
            input_params={
                "summary": "External Demo",
                "attendees": [{"email": "client@external.com"}],
                "start": {"dateTime": "2026-09-25T14:00:00Z"},
                "end": {"dateTime": "2026-09-25T15:00:00Z"},
            },
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )

    assert result["status"] == "success"
    _, kwargs = mock_post.call_args
    assert kwargs["params"]["sendUpdates"] == "all"


def test_calendar_find_free_slots_success():
    """calendar.find_free_slots posts to /freeBusy endpoint."""
    mock_sb = _make_supabase_mock()
    freebusy_payload = {
        "kind": "calendar#freeBusy",
        "calendars": {"primary": {"busy": []}},
    }
    mock_post_resp = _make_httpx_response(200, freebusy_payload)

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.post", return_value=mock_post_resp) as mock_post,
    ):
        result = call(
            tool_name="calendar.find_free_slots",
            input_params={
                "timeMin": "2026-09-25T09:00:00Z",
                "timeMax": "2026-09-25T17:00:00Z",
            },
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )

    assert result["status"] == "success"
    assert "calendars" in result["output"]
    _, kwargs = mock_post.call_args
    assert "freeBusy" in mock_post.call_args[0][0]


def test_calendar_update_event_success():
    """calendar.update_event sends PATCH with eventId."""
    mock_sb = _make_supabase_mock()
    mock_patch_resp = _make_httpx_response(200, {"id": "evt_update_1", "summary": "New Title"})

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.patch", return_value=mock_patch_resp) as mock_patch,
    ):
        result = call(
            tool_name="calendar.update_event",
            input_params={"eventId": "evt_update_1", "summary": "New Title"},
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )

    assert result["status"] == "success"
    assert result["output"]["summary"] == "New Title"
    mock_patch.assert_called_once()
    assert "evt_update_1" in mock_patch.call_args[0][0]


def test_calendar_delete_event_success():
    """calendar.delete_event sends DELETE and returns success with 204."""
    mock_sb = _make_supabase_mock()
    mock_del_resp = _make_httpx_response(204)

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.delete", return_value=mock_del_resp) as mock_delete,
    ):
        result = call(
            tool_name="calendar.delete_event",
            input_params={"eventId": "evt_del_1"},
            user_id=USER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            task_id=TASK_ID,
        )

    assert result["status"] == "success"
    assert result["output"]["deleted"] is True
    assert result["output"]["eventId"] == "evt_del_1"
    mock_delete.assert_called_once()
    assert "evt_del_1" in mock_delete.call_args[0][0]


def test_calendar_403_returns_insufficient_scope():
    """calendar.call returns distinct error on HTTP 403."""
    mock_sb = _make_supabase_mock()
    resp_403 = _make_httpx_response(403)
    resp_403.is_success = False

    with (
        patch("app.mcp_clients.calendar.supabase_admin", mock_sb),
        patch(REFRESH_PATCH, mock_sb),
        patch("httpx.get", return_value=resp_403),
    ):
        result = call("calendar.list_events", {}, USER_ID, IDEMPOTENCY_KEY)

    assert result["status"] == "error"
    assert "insufficient scope" in result["error"]
