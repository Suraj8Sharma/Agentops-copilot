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

from app.db.supabase_client import supabase

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
    """Fetch the user's decrypted Google OAuth access token from oauth_connections."""
    try:
        result = (
            supabase.table("oauth_connections")
            .select("access_token")
            .eq("user_id", user_id)
            .eq("provider", "google")
            .single()
            .execute()
        )
        if result.data:
            return result.data["access_token"]
        logger.warning("calendar: no Google token found for user_id=%s", user_id)
        return None
    except Exception:
        logger.error(
            "calendar: failed to fetch token for user_id=%s",
            user_id,
            exc_info=True,
        )
        return None


def call(
    tool_name: str,
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Call a Google Calendar tool via the official MCP remote server.

    Args:
        tool_name:        Internal tool name e.g. ``calendar.create_event``.
        input_params:     Tool-specific arguments from the plan step.
        user_id:          UUID of the user — used to fetch their OAuth token.
        idempotency_key:  ``plan_id:step_index`` — passed as a request header
                          to prevent duplicate creates on retry.

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

    # --- 4. Call the remote MCP server ----------------------------------------
    try:
        response = httpx.post(
            CALENDAR_MCP_URL,
            json=payload,
            headers=headers,
            timeout=_TIMEOUT,
        )
    except httpx.TimeoutException:
        logger.warning(
            "calendar: timeout calling %s [tool=%s user=%s]",
            CALENDAR_MCP_URL,
            tool_name,
            user_id,
        )
        return {
            "status": "error",
            "output": None,
            "error": "timeout",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }
    except httpx.RequestError as exc:
        logger.error("calendar: network error [tool=%s]: %s", tool_name, exc)
        return {
            "status": "error",
            "output": None,
            "error": f"network error: {exc}",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    latency_ms = int((time.monotonic() - t0) * 1000)

    # --- 5. Handle HTTP-level errors ------------------------------------------
    if response.status_code == 429:
        logger.warning("calendar: rate limited [tool=%s user=%s]", tool_name, user_id)
        return {
            "status": "rate_limited",
            "output": None,
            "error": "rate_limited",
            "latency_ms": latency_ms,
        }

    if response.status_code == 401:
        logger.warning(
            "calendar: 401 unauthorized [tool=%s user=%s] — token may be expired",
            tool_name,
            user_id,
        )
        return {
            "status": "error",
            "output": None,
            "error": "unauthorized — token expired or revoked",
            "latency_ms": latency_ms,
        }

    if not response.is_success:
        logger.error(
            "calendar: HTTP %d from MCP server [tool=%s user=%s]",
            response.status_code,
            tool_name,
            user_id,
        )
        return {
            "status": "error",
            "output": None,
            "error": f"MCP server returned HTTP {response.status_code}",
            "latency_ms": latency_ms,
        }

    # --- 6. Parse MCP JSON-RPC response ---------------------------------------
    try:
        body = response.json()
    except Exception:
        logger.error("calendar: non-JSON response from MCP server [tool=%s]", tool_name)
        return {
            "status": "error",
            "output": None,
            "error": "invalid JSON from MCP server",
            "latency_ms": latency_ms,
        }

    if "error" in body:
        rpc_error = body["error"]
        logger.warning(
            "calendar: MCP RPC error [tool=%s code=%s msg=%s]",
            tool_name,
            rpc_error.get("code"),
            rpc_error.get("message"),
        )
        return {
            "status": "error",
            "output": None,
            "error": rpc_error.get("message", "unknown MCP error"),
            "latency_ms": latency_ms,
        }

    result = body.get("result", {})
    logger.info(
        "calendar: success [tool=%s user=%s latency=%dms]",
        tool_name,
        user_id,
        latency_ms,
    )
    return {"status": "success", "output": result, "error": None, "latency_ms": latency_ms}
