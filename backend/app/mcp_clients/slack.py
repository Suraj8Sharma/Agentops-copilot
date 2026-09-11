"""Slack MCP client for AgentOps Copilot.

All Slack tools route through the official Slack MCP server:
    https://mcp.slack.com/mcp

Supported tools:
    slack.list_channels
    slack.post_message_dm
    slack.post_message_channel
    slack.add_reaction

Auth: Slack bot token from oauth_connections (provider='slack'),
Fernet-encrypted at rest.

Transport: Plain JSON-RPC over HTTP.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from cryptography.fernet import Fernet

from app.core.config import settings
from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoint & config
# ---------------------------------------------------------------------------

SLACK_MCP_URL = "https://mcp.slack.com/mcp"
_TIMEOUT = 15.0

_TOOL_NAME_MAP: dict[str, str] = {
    "slack.list_channels": "list_channels",
    "slack.post_message_dm": "post_message",
    "slack.post_message_channel": "post_message",
    "slack.add_reaction": "add_reaction",
}

# Tools that mutate state — need idempotency precheck.
_MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "slack.post_message_dm",
        "slack.post_message_channel",
        "slack.add_reaction",
    }
)


# ---------------------------------------------------------------------------
# Token fetch
# ---------------------------------------------------------------------------


def _fetch_slack_token(user_id: str) -> str | None:
    """Fetch and decrypt the user's Slack token from oauth_connections."""
    try:
        result = (
            supabase.table("oauth_connections")
            .select("access_token")
            .eq("user_id", user_id)
            .eq("provider", "slack")
            .single()
            .execute()
        )
        if not result.data:
            logger.warning("slack: no Slack token found for user_id=%s", user_id)
            return None

        encrypted_token = result.data["access_token"]
        try:
            fernet = Fernet(settings.ENCRYPTION_KEY.encode())
            return fernet.decrypt(encrypted_token.encode()).decode()
        except Exception:
            logger.debug("slack: Fernet decrypt failed, using raw token for user_id=%s", user_id)
            return encrypted_token
    except Exception:
        logger.error("slack: failed to fetch token for user_id=%s", user_id, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Idempotency precheck
# ---------------------------------------------------------------------------


def _already_done(plan_id: str, step_index: int) -> dict | None:
    """Return cached output if this step already completed successfully."""
    try:
        result = (
            supabase.table("plan_steps")
            .select("status, output")
            .eq("plan_id", plan_id)
            .eq("step_index", step_index)
            .single()
            .execute()
        )
        if result.data and result.data.get("status") == "done" and result.data.get("output"):
            return result.data["output"]
    except Exception:
        logger.warning(
            "slack: idempotency precheck failed for plan_id=%s step=%d — proceeding",
            plan_id,
            step_index,
            exc_info=True,
        )
    return None


# ---------------------------------------------------------------------------
# Execution log stub
# ---------------------------------------------------------------------------


async def _log_execution(event_type: str, payload: dict, latency_ms: int) -> None:
    """Log to execution_logs table."""
    # TODO(D22): wire to real execution_logs insert via supabase service role.
    logger.debug("[execution_log-stub] %s: %s (%dms)", event_type, payload, latency_ms)


# ---------------------------------------------------------------------------
# Core tool call
# ---------------------------------------------------------------------------


def _make_error(code: str, message: str, latency_ms: int) -> dict[str, Any]:
    return {
        "status": "error",
        "output": None,
        "error": {"code": code, "message": message},
        "latency_ms": latency_ms,
    }


def _call_slack_mcp(
    tool_name: str,
    mcp_tool: str,
    input_params: dict[str, Any],
    user_id: str,
    token: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Call a Slack tool via the MCP server."""
    t0 = time.monotonic()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": idempotency_key,
        "method": "tools/call",
        "params": {
            "name": mcp_tool,
            "arguments": input_params,
        },
    }

    try:
        response = httpx.post(SLACK_MCP_URL, json=payload, headers=headers, timeout=_TIMEOUT)
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _make_error("TIMEOUT", "timeout calling Slack MCP server", latency_ms)
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _make_error("PROVIDER_ERROR", f"network error: {exc}", latency_ms)

    latency_ms = int((time.monotonic() - t0) * 1000)

    # HTTP-level errors
    if response.status_code == 401:
        return _make_error(
            "AUTH_EXPIRED", "token revoked or expired — user must reconnect Slack", latency_ms
        )

    if response.status_code == 429:
        return {
            "status": "rate_limited",
            "output": None,
            "error": {"code": "RATE_LIMITED", "message": "rate limited"},
            "latency_ms": latency_ms,
        }

    if not response.is_success:
        return _make_error(
            "PROVIDER_ERROR", f"Slack MCP returned HTTP {response.status_code}", latency_ms
        )

    # Parse JSON response
    try:
        body = response.json()
    except Exception:
        logger.error("slack: failed to parse JSON response [tool=%s]", tool_name)
        return _make_error("PROVIDER_ERROR", "invalid response from Slack MCP server", latency_ms)

    if "error" in body:
        rpc_error = body["error"]
        msg = rpc_error.get("message", "unknown MCP error")
        # Check for invalid params
        if rpc_error.get("code") == -32602:
            return _make_error("INVALID_PARAMS", msg, latency_ms)
        return _make_error("PROVIDER_ERROR", msg, latency_ms)

    result = body.get("result", {})
    logger.info("slack: success [tool=%s user=%s latency=%dms]", tool_name, user_id, latency_ms)
    return {"status": "success", "output": result, "error": None, "latency_ms": latency_ms}


# ---------------------------------------------------------------------------
# Public entrypoint — called by mcp_clients/__init__.py
# ---------------------------------------------------------------------------


def call(
    tool_name: str,
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Route a Slack tool call to the MCP server."""
    # 1. Resolve tool name
    mcp_tool = _TOOL_NAME_MAP.get(tool_name)
    if mcp_tool is None:
        logger.error("slack: unknown tool_name=%s", tool_name)
        return _make_error("INVALID_PARAMS", f"unknown tool: {tool_name}", 0)

    # 2. Idempotency precheck for mutating tools
    if tool_name in _MUTATING_TOOLS:
        try:
            plan_id, step_index_str = idempotency_key.split(":", 1)
            cached = _already_done(plan_id, int(step_index_str))
            if cached is not None:
                logger.info("slack: skipped — step already done [key=%s]", idempotency_key)
                return {"status": "success", "output": cached, "error": None, "latency_ms": 0}
        except (ValueError, AttributeError):
            logger.warning("slack: bad idempotency_key=%r — skipping precheck", idempotency_key)

    # 3. Fetch token
    token = _fetch_slack_token(user_id)
    if not token:
        return _make_error("AUTH_EXPIRED", "no Slack OAuth token — user must connect Slack", 0)

    # 4. Call MCP
    return _call_slack_mcp(tool_name, mcp_tool, input_params, user_id, token, idempotency_key)
