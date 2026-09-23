"""Google Calendar REST client for AgentOps Copilot.

Previously this module talked to Google's Calendar MCP Developer Preview
server (calendarmcp.googleapis.com/mcp/v1) via JSON-RPC.  That server is
unstable in developer mode and has no per-request idempotency support.

This revision replaces every MCP call with a direct Google Calendar REST API
(v3) call, authenticated with the same per-user OAuth token.  The public
``call()`` interface, envelope shape, logging, and error handling are
identical — only the HTTP layer changes.

Tool → REST endpoint mapping
─────────────────────────────
  calendar.list_events                → GET  /calendars/primary/events
  calendar.find_free_slots            → POST /freeBusy
  calendar.create_event_internal_only → POST /calendars/primary/events
  calendar.create_event_external_attendee → POST /calendars/primary/events
  calendar.update_event               → PATCH /calendars/primary/events/{eventId}
  calendar.delete_event               → DELETE /calendars/primary/events/{eventId}

The planner and risk gate never import this module directly — the execute node
calls it via the provider router in mcp_clients/__init__.py.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.db.supabase_client import supabase_admin
from app.mcp_clients.google_token_refresh import get_valid_google_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Google Calendar REST API base
# ---------------------------------------------------------------------------

_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
_CALENDAR_EVENTS_URL = f"{_CALENDAR_BASE}/calendars/primary/events"
_FREEBUSY_URL = f"{_CALENDAR_BASE}/freeBusy"

# HTTP timeout for all outbound calls (seconds).
_TIMEOUT = 15.0

# Set of known tool names — used for unknown-tool guard.
_KNOWN_TOOLS: frozenset[str] = frozenset(
    {
        "calendar.list_events",
        "calendar.find_free_slots",
        "calendar.create_event_internal_only",
        "calendar.create_event_external_attendee",
        "calendar.update_event",
        "calendar.delete_event",
    }
)


# ---------------------------------------------------------------------------
# Token fetch
# ---------------------------------------------------------------------------


def _fetch_user_token(user_id: str) -> str | None:
    """Return a valid (possibly auto-refreshed) Google OAuth access token.

    Delegates to ``google_token_refresh.get_valid_google_token`` which:
    - Returns the stored token immediately if it is not yet expired.
    - Calls Google's token endpoint to refresh it if it is expired or within
      5 minutes of expiry, persists the new token to the DB, and returns it.
    - Returns ``None`` if no token exists or the refresh fails (revoked, etc.).
    """
    token = get_valid_google_token(user_id, "google_calendar")
    if token is None:
        logger.warning("calendar: no valid Google token for user_id=%s", user_id)
    return token


# ---------------------------------------------------------------------------
# Execution log helper
# ---------------------------------------------------------------------------


def _log_event_calendar(
    task_id: str,
    event_type: str,
    payload: dict[str, Any],
    step_id: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Write one row to execution_logs for a Calendar event (best-effort)."""
    try:
        row: dict[str, Any] = {
            "task_id": task_id,
            "agent_name": "mcp_calendar",
            "event_type": event_type,
            "payload": payload,
        }
        if step_id is not None:
            row["step_id"] = step_id
        if latency_ms is not None:
            row["latency_ms"] = latency_ms
        supabase_admin.table("execution_logs").insert(row).execute()
    except Exception:
        logger.warning(
            "execution_logs write failed [mcp_calendar task_id=%s event_type=%s]",
            task_id,
            event_type,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Error envelope helpers
# ---------------------------------------------------------------------------


def _error(msg: str, latency_ms: int, code: str = "PROVIDER_ERROR") -> dict[str, Any]:
    return {"status": "error", "output": None, "error": msg, "latency_ms": latency_ms}


def _rate_limited(latency_ms: int) -> dict[str, Any]:
    return {
        "status": "rate_limited",
        "output": None,
        "error": "rate_limited",
        "latency_ms": latency_ms,
    }


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _handle_http_error(
    response: httpx.Response,
    tool_name: str,
    user_id: str,
    task_id: str,
    latency_ms: int,
) -> dict[str, Any] | None:
    """Return an error envelope for non-2xx responses, or None if the response is OK."""
    if response.status_code == 429:
        logger.warning("calendar: rate limited [tool=%s user=%s]", tool_name, user_id)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": tool_name,
                "error_code": "RATE_LIMITED",
                "message": "rate limited",
            },
            latency_ms=latency_ms,
        )
        return _rate_limited(latency_ms)

    if response.status_code == 401:
        logger.warning("calendar: 401 unauthorized [tool=%s user=%s]", tool_name, user_id)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": tool_name,
                "error_code": "AUTH_EXPIRED",
                "message": "unauthorized — token expired or revoked",
            },
            latency_ms=latency_ms,
        )
        return _error("unauthorized — token expired or revoked", latency_ms)

    if response.status_code == 403:
        logger.warning("calendar: 403 forbidden [tool=%s user=%s]", tool_name, user_id)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": tool_name,
                "error_code": "INSUFFICIENT_SCOPE",
                "message": "insufficient scope — user must reconnect Google account",
            },
            latency_ms=latency_ms,
        )
        return _error("insufficient scope — user must reconnect Google account", latency_ms)

    if not response.is_success:
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:
            detail = ""
        msg = f"Calendar API returned HTTP {response.status_code}: {detail}".strip(": ")
        logger.error(
            "calendar: HTTP %d [tool=%s user=%s] %s",
            response.status_code,
            tool_name,
            user_id,
            detail,
        )
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "PROVIDER_ERROR", "message": msg},
            latency_ms=latency_ms,
        )
        return _error(msg, latency_ms)

    return None  # response is OK


# ---------------------------------------------------------------------------
# Per-tool REST implementations
# ---------------------------------------------------------------------------


def _list_events(
    input_params: dict[str, Any],
    token: str,
    tool_name: str,
    user_id: str,
    task_id: str,
    t0: float,
) -> dict[str, Any]:
    """GET /calendars/primary/events — list calendar events."""
    params: dict[str, Any] = {}
    if "timeMin" in input_params:
        params["timeMin"] = input_params["timeMin"]
    if "timeMax" in input_params:
        params["timeMax"] = input_params["timeMax"]
    if "maxResults" in input_params:
        params["maxResults"] = input_params["maxResults"]
    if "q" in input_params:
        params["q"] = input_params["q"]
    params.setdefault("singleEvents", True)
    params.setdefault("orderBy", "startTime")

    try:
        response = httpx.get(
            _CALENDAR_EVENTS_URL,
            params=params,
            headers=_auth_headers(token),
            timeout=_TIMEOUT,
        )
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("calendar: timeout [tool=%s user=%s]", tool_name, user_id)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "TIMEOUT", "message": "timeout"},
            latency_ms=latency_ms,
        )
        return _error("timeout", latency_ms)
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("calendar: network error [tool=%s]: %s", tool_name, exc)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "NETWORK_ERROR", "message": str(exc)},
            latency_ms=latency_ms,
        )
        return _error(f"network error: {exc}", latency_ms)

    latency_ms = int((time.monotonic() - t0) * 1000)
    err = _handle_http_error(response, tool_name, user_id, task_id, latency_ms)
    if err:
        return err

    result = response.json()
    return {"status": "success", "output": result, "error": None, "latency_ms": latency_ms}


def _find_free_slots(
    input_params: dict[str, Any],
    token: str,
    tool_name: str,
    user_id: str,
    task_id: str,
    t0: float,
) -> dict[str, Any]:
    """POST /freeBusy — find free/busy windows."""
    body: dict[str, Any] = {
        "timeMin": input_params.get("timeMin", ""),
        "timeMax": input_params.get("timeMax", ""),
        "items": input_params.get("items", [{"id": "primary"}]),
    }
    if "timeZone" in input_params:
        body["timeZone"] = input_params["timeZone"]

    try:
        response = httpx.post(
            _FREEBUSY_URL,
            json=body,
            headers=_auth_headers(token),
            timeout=_TIMEOUT,
        )
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("calendar: timeout [tool=%s user=%s]", tool_name, user_id)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "TIMEOUT", "message": "timeout"},
            latency_ms=latency_ms,
        )
        return _error("timeout", latency_ms)
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("calendar: network error [tool=%s]: %s", tool_name, exc)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "NETWORK_ERROR", "message": str(exc)},
            latency_ms=latency_ms,
        )
        return _error(f"network error: {exc}", latency_ms)

    latency_ms = int((time.monotonic() - t0) * 1000)
    err = _handle_http_error(response, tool_name, user_id, task_id, latency_ms)
    if err:
        return err

    result = response.json()
    return {"status": "success", "output": result, "error": None, "latency_ms": latency_ms}


def _create_event(
    input_params: dict[str, Any],
    token: str,
    tool_name: str,
    user_id: str,
    task_id: str,
    t0: float,
    idempotency_key: str,
) -> dict[str, Any]:
    """POST /calendars/primary/events — create a calendar event."""
    # Build the event body from input_params.
    # Accepts either a ready-made 'event' dict or individual fields.
    event_body: dict[str, Any] = input_params.get("event", {})
    if not event_body:
        # Construct from flat fields
        event_body = {}
        if "summary" in input_params:
            event_body["summary"] = input_params["summary"]
        if "description" in input_params:
            event_body["description"] = input_params["description"]
        if "start" in input_params:
            event_body["start"] = input_params["start"]
        if "end" in input_params:
            event_body["end"] = input_params["end"]
        if "attendees" in input_params:
            event_body["attendees"] = input_params["attendees"]
        if "location" in input_params:
            event_body["location"] = input_params["location"]

    params: dict[str, Any] = {}
    if "sendUpdates" in input_params:
        params["sendUpdates"] = input_params["sendUpdates"]
    elif tool_name == "calendar.create_event_external_attendee":
        params["sendUpdates"] = "all"

    # Pass idempotency key as a header — Google Calendar supports
    # duplicate suppression via X-Idempotency-Token on inserts.
    headers = {**_auth_headers(token), "X-Idempotency-Token": idempotency_key}

    try:
        response = httpx.post(
            _CALENDAR_EVENTS_URL,
            json=event_body,
            params=params,
            headers=headers,
            timeout=_TIMEOUT,
        )
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("calendar: timeout [tool=%s user=%s]", tool_name, user_id)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "TIMEOUT", "message": "timeout"},
            latency_ms=latency_ms,
        )
        return _error("timeout", latency_ms)
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("calendar: network error [tool=%s]: %s", tool_name, exc)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "NETWORK_ERROR", "message": str(exc)},
            latency_ms=latency_ms,
        )
        return _error(f"network error: {exc}", latency_ms)

    latency_ms = int((time.monotonic() - t0) * 1000)
    err = _handle_http_error(response, tool_name, user_id, task_id, latency_ms)
    if err:
        return err

    result = response.json()
    return {"status": "success", "output": result, "error": None, "latency_ms": latency_ms}


def _update_event(
    input_params: dict[str, Any],
    token: str,
    tool_name: str,
    user_id: str,
    task_id: str,
    t0: float,
) -> dict[str, Any]:
    """PATCH /calendars/primary/events/{eventId} — partial update a calendar event."""
    event_id = input_params.get("eventId") or input_params.get("event_id")
    if not event_id:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _error("missing required param: eventId", latency_ms)

    patch_body: dict[str, Any] = input_params.get("event", {})
    if not patch_body:
        patch_body = {k: v for k, v in input_params.items() if k not in ("eventId", "event_id")}

    params: dict[str, Any] = {}
    if "sendUpdates" in input_params:
        params["sendUpdates"] = input_params["sendUpdates"]

    url = f"{_CALENDAR_EVENTS_URL}/{event_id}"
    try:
        response = httpx.patch(
            url,
            json=patch_body,
            params=params,
            headers=_auth_headers(token),
            timeout=_TIMEOUT,
        )
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("calendar: timeout [tool=%s user=%s]", tool_name, user_id)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "TIMEOUT", "message": "timeout"},
            latency_ms=latency_ms,
        )
        return _error("timeout", latency_ms)
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("calendar: network error [tool=%s]: %s", tool_name, exc)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "NETWORK_ERROR", "message": str(exc)},
            latency_ms=latency_ms,
        )
        return _error(f"network error: {exc}", latency_ms)

    latency_ms = int((time.monotonic() - t0) * 1000)
    err = _handle_http_error(response, tool_name, user_id, task_id, latency_ms)
    if err:
        return err

    result = response.json()
    return {"status": "success", "output": result, "error": None, "latency_ms": latency_ms}


def _delete_event(
    input_params: dict[str, Any],
    token: str,
    tool_name: str,
    user_id: str,
    task_id: str,
    t0: float,
) -> dict[str, Any]:
    """DELETE /calendars/primary/events/{eventId} — delete a calendar event."""
    event_id = input_params.get("eventId") or input_params.get("event_id")
    if not event_id:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _error("missing required param: eventId", latency_ms)

    url = f"{_CALENDAR_EVENTS_URL}/{event_id}"
    params: dict[str, Any] = {}
    if "sendUpdates" in input_params:
        params["sendUpdates"] = input_params["sendUpdates"]

    try:
        response = httpx.delete(
            url,
            params=params,
            headers=_auth_headers(token),
            timeout=_TIMEOUT,
        )
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("calendar: timeout [tool=%s user=%s]", tool_name, user_id)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "TIMEOUT", "message": "timeout"},
            latency_ms=latency_ms,
        )
        return _error("timeout", latency_ms)
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("calendar: network error [tool=%s]: %s", tool_name, exc)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={"tool_name": tool_name, "error_code": "NETWORK_ERROR", "message": str(exc)},
            latency_ms=latency_ms,
        )
        return _error(f"network error: {exc}", latency_ms)

    latency_ms = int((time.monotonic() - t0) * 1000)
    err = _handle_http_error(response, tool_name, user_id, task_id, latency_ms)
    if err:
        return err

    # Successful DELETE returns 204 No Content — no body to parse.
    return {
        "status": "success",
        "output": {"deleted": True, "eventId": event_id},
        "error": None,
        "latency_ms": latency_ms,
    }


# ---------------------------------------------------------------------------
# Public entrypoint — called by mcp_clients/__init__.py
# ---------------------------------------------------------------------------


def call(
    tool_name: str,
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
    task_id: str = "unknown",
) -> dict[str, Any]:
    """Route a Google Calendar tool call to the correct REST endpoint.

    Args:
        tool_name:        Internal tool name e.g. ``calendar.create_event_internal_only``.
        input_params:     Tool-specific arguments from the plan step.
        user_id:          UUID of the user — used to fetch their OAuth token.
        idempotency_key:  ``plan_id:step_index`` — passed as X-Idempotency-Token
                          for create calls to prevent duplicate events on retry.
        task_id:          UUID of the parent task — used for execution_logs rows.

    Returns:
        Standard AgentOps MCP envelope::

            {
                "status":      "success" | "error" | "rate_limited",
                "output":      dict | None,
                "error":       str | None,
                "latency_ms":  int,
            }
    """
    t0 = time.monotonic()

    # --- Unknown tool guard ---------------------------------------------------
    if tool_name not in _KNOWN_TOOLS:
        logger.error("calendar: unknown tool_name=%s", tool_name)
        return {
            "status": "error",
            "output": None,
            "error": f"unknown tool: {tool_name}",
            "latency_ms": 0,
        }

    # --- Fetch token ---------------------------------------------------------
    token = _fetch_user_token(user_id)
    if not token:
        return {
            "status": "error",
            "output": None,
            "error": "no Google OAuth token for user — user must reconnect Google account",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    # --- Log tool_called before any external effect --------------------------
    _log_event_calendar(
        task_id=task_id,
        event_type="tool_called",
        payload={"tool_name": tool_name, "mcp_server": "calendar", "input_params": input_params},
    )

    # --- Dispatch to per-tool REST handler -----------------------------------
    if tool_name == "calendar.list_events":
        result = _list_events(input_params, token, tool_name, user_id, task_id, t0)

    elif tool_name == "calendar.find_free_slots":
        result = _find_free_slots(input_params, token, tool_name, user_id, task_id, t0)

    elif tool_name in (
        "calendar.create_event_internal_only",
        "calendar.create_event_external_attendee",
    ):
        result = _create_event(
            input_params, token, tool_name, user_id, task_id, t0, idempotency_key
        )

    elif tool_name == "calendar.update_event":
        result = _update_event(input_params, token, tool_name, user_id, task_id, t0)

    elif tool_name == "calendar.delete_event":
        result = _delete_event(input_params, token, tool_name, user_id, task_id, t0)

    else:
        # Should be unreachable due to the guard above, but keeps mypy happy.
        result = _error(f"unknown tool: {tool_name}", 0)

    # --- Log outcome ---------------------------------------------------------
    latency_ms = result.get("latency_ms", 0)
    if result["status"] == "success":
        logger.info(
            "calendar: success [tool=%s user=%s latency=%dms]", tool_name, user_id, latency_ms
        )
        _log_event_calendar(
            task_id=task_id,
            event_type="tool_result",
            payload={
                "tool_name": tool_name,
                "mcp_server": "calendar",
                "status": "success",
                "output": result["output"],
            },
            latency_ms=latency_ms,
        )

    return result
