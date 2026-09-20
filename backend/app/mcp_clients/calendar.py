"""Google Calendar MCP client for AgentOps Copilot.

Connects to Google's official hosted remote MCP server for Google Calendar:
    https://calendarmcp.googleapis.com/mcp/v1

Every tool call:
  1. Fetches the user's Google OAuth token from the oauth_connections table.
  2. POSTs a standard MCP JSON-RPC ``tools/call`` request to Google's endpoint,
     passing the user's token as a Bearer token in the Authorization header.
  3. Returns the standard AgentOps MCP envelope:
     { status, output, error, latency_ms }

The planner and risk gate never import this module directly — the execute node
calls it via the provider router in mcp_clients/__init__.py.

Supported tools (D14):
    calendar.list_events
    calendar.find_free_slots
    calendar.create_event_internal_only
    calendar.create_event_external_attendee
    calendar.update_event
    calendar.delete_event
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from cryptography.fernet import Fernet

from app.core.config import settings
from app.db.supabase_client import supabase_admin

logger = logging.getLogger(__name__)

# Google's official hosted Calendar MCP endpoint (Developer Preview).
CALENDAR_MCP_URL = "https://calendarmcp.googleapis.com/mcp/v1"

# Maps our internal tool names (with the "calendar." prefix) to the exact
# tool names the Google Calendar MCP server exposes.
_TOOL_NAME_MAP: dict[str, str] = {
    "calendar.list_events": "list_events",
    "calendar.find_free_slots": "find_free_slots",
    "calendar.create_event_internal_only": "create_event",
    "calendar.create_event_external_attendee": "create_event",
    "calendar.update_event": "update_event",
    "calendar.delete_event": "delete_event",
}

# HTTP timeout for MCP calls (seconds).
_TIMEOUT = 15.0


def _fetch_user_token(user_id: str) -> str | None:
    """Fetch and decrypt the user's Google OAuth access token from oauth_connections."""
    try:
        result = (
            supabase_admin.table("oauth_connections")
            .select("access_token")
            .eq("user_id", user_id)
            .eq("provider", "google_calendar")
            .limit(1)
            .execute()
        )
        if not result.data:
            logger.warning("calendar: no Google token found for user_id=%s", user_id)
            return None

        encrypted_token = result.data[0]["access_token"]
        try:
            fernet = Fernet(settings.ENCRYPTION_KEY.encode())
            return fernet.decrypt(encrypted_token.encode()).decode()
        except Exception:
            logger.debug("calendar: Fernet decrypt failed, using raw token for user_id=%s", user_id)
            return encrypted_token
    except Exception:
        logger.error(
            "calendar: failed to fetch token for user_id=%s",
            user_id,
            exc_info=True,
        )
        return None


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
    """Write one row to execution_logs for a Calendar MCP event (best-effort)."""
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


def call(
    tool_name: str,
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
    task_id: str = "unknown",
) -> dict[str, Any]:
    """Call a Google Calendar tool via the official MCP remote server.

    Args:
        tool_name:        Internal tool name e.g. ``calendar.create_event``.
        input_params:     Tool-specific arguments from the plan step.
        user_id:          UUID of the user — used to fetch their OAuth token.
        idempotency_key:  ``plan_id:step_index`` — passed as a request header
                          to prevent duplicate creates on retry.
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

    # --- 1. Resolve tool name -------------------------------------------------
    mcp_tool = _TOOL_NAME_MAP.get(tool_name)
    if mcp_tool is None:
        logger.error("calendar: unknown tool_name=%s", tool_name)
        return {
            "status": "error",
            "output": None,
            "error": f"unknown tool: {tool_name}",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    # --- 2. Fetch user token --------------------------------------------------
    token = _fetch_user_token(user_id)
    if not token:
        return {
            "status": "error",
            "output": None,
            "error": "no Google OAuth token for user — user must reconnect Google account",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    # --- 3. Build MCP JSON-RPC request ----------------------------------------
    payload = {
        "jsonrpc": "2.0",
        "id": idempotency_key,
        "method": "tools/call",
        "params": {
            "name": mcp_tool,
            "arguments": input_params,
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        # Pass idempotency key so Google's server can deduplicate retries.
        "X-Idempotency-Key": idempotency_key,
    }

    # --- 4. Log tool_called before any external effect ------------------------
    _log_event_calendar(
        task_id=task_id,
        event_type="tool_called",
        payload={"tool_name": tool_name, "mcp_server": "calendar", "input_params": input_params},
    )

    # --- 5. Call the remote MCP server ----------------------------------------
    try:
        response = httpx.post(
            CALENDAR_MCP_URL,
            json=payload,
            headers=headers,
            timeout=_TIMEOUT,
        )
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "calendar: timeout calling %s [tool=%s user=%s]",
            CALENDAR_MCP_URL,
            tool_name,
            user_id,
        )
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": tool_name,
                "mcp_server": "calendar",
                "error_code": "TIMEOUT",
                "message": "timeout",
            },  # noqa: E501
            latency_ms=latency_ms,
        )
        return {"status": "error", "output": None, "error": "timeout", "latency_ms": latency_ms}
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("calendar: network error [tool=%s]: %s", tool_name, exc)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": tool_name,
                "mcp_server": "calendar",
                "error_code": "NETWORK_ERROR",
                "message": str(exc),
            },  # noqa: E501
            latency_ms=latency_ms,
        )
        return {
            "status": "error",
            "output": None,
            "error": f"network error: {exc}",
            "latency_ms": latency_ms,
        }  # noqa: E501

    latency_ms = int((time.monotonic() - t0) * 1000)

    # --- 6. Handle HTTP-level errors ------------------------------------------
    if response.status_code == 429:
        logger.warning("calendar: rate limited [tool=%s user=%s]", tool_name, user_id)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": tool_name,
                "mcp_server": "calendar",
                "error_code": "RATE_LIMITED",
                "message": "rate limited",
            },  # noqa: E501
            latency_ms=latency_ms,
        )
        return {
            "status": "rate_limited",
            "output": None,
            "error": "rate_limited",
            "latency_ms": latency_ms,
        }  # noqa: E501

    if response.status_code == 401:
        logger.warning(
            "calendar: 401 unauthorized [tool=%s user=%s] — token may be expired",
            tool_name,
            user_id,
        )
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": tool_name,
                "mcp_server": "calendar",
                "error_code": "AUTH_EXPIRED",
                "message": "unauthorized — token expired or revoked",
            },  # noqa: E501
            latency_ms=latency_ms,
        )
        return {
            "status": "error",
            "output": None,
            "error": "unauthorized — token expired or revoked",
            "latency_ms": latency_ms,
        }  # noqa: E501

    if not response.is_success:
        logger.error(
            "calendar: HTTP %d from MCP server [tool=%s user=%s]",
            response.status_code,
            tool_name,
            user_id,
        )
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": tool_name,
                "mcp_server": "calendar",
                "error_code": "PROVIDER_ERROR",
                "message": f"MCP server returned HTTP {response.status_code}",
            },  # noqa: E501
            latency_ms=latency_ms,
        )
        return {
            "status": "error",
            "output": None,
            "error": f"MCP server returned HTTP {response.status_code}",
            "latency_ms": latency_ms,
        }  # noqa: E501

    # --- 7. Parse MCP JSON-RPC response ---------------------------------------
    try:
        body = response.json()
    except Exception:
        logger.error("calendar: non-JSON response from MCP server [tool=%s]", tool_name)
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": tool_name,
                "mcp_server": "calendar",
                "error_code": "PROVIDER_ERROR",
                "message": "invalid JSON from MCP server",
            },  # noqa: E501
            latency_ms=latency_ms,
        )
        return {
            "status": "error",
            "output": None,
            "error": "invalid JSON from MCP server",
            "latency_ms": latency_ms,
        }  # noqa: E501

    if "error" in body:
        rpc_error = body["error"]
        logger.warning(
            "calendar: MCP RPC error [tool=%s code=%s msg=%s]",
            tool_name,
            rpc_error.get("code"),
            rpc_error.get("message"),
        )
        _log_event_calendar(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": tool_name,
                "mcp_server": "calendar",
                "error_code": str(rpc_error.get("code")),
                "message": rpc_error.get("message", "unknown MCP error"),
            },  # noqa: E501
            latency_ms=latency_ms,
        )
        return {
            "status": "error",
            "output": None,
            "error": rpc_error.get("message", "unknown MCP error"),
            "latency_ms": latency_ms,
        }  # noqa: E501

    result = body.get("result", {})
    logger.info(
        "calendar: success [tool=%s user=%s latency=%dms]",
        tool_name,
        user_id,
        latency_ms,
    )
    _log_event_calendar(
        task_id=task_id,
        event_type="tool_result",
        payload={
            "tool_name": tool_name,
            "mcp_server": "calendar",
            "status": "success",
            "output": result,
        },  # noqa: E501
        latency_ms=latency_ms,
    )
    return {"status": "success", "output": result, "error": None, "latency_ms": latency_ms}
