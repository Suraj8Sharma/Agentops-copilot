"""GitHub MCP client for AgentOps Copilot.

All GitHub tools route through one endpoint — the GitHub Copilot MCP server:
    https://api.githubcopilot.com/mcp/

Supported tools (D16):
    github.list_issues         — read open issues for context
    github.create_issue        — file a new issue
    github.comment_on_issue    — add comment to an existing issue
    github.create_pr_comment   — comment on a pull request

Auth: GitHub OAuth token from oauth_connections (provider='github'),
Fernet-encrypted at rest.  GitHub tokens don't expire on a schedule — the
only failure mode is revocation (401).  No retry on 401.

Transport: Streamable HTTP MCP — the server returns text/event-stream with
SSE-wrapped JSON-RPC.  Session ID from the initialize response header is
reused across calls in a task.
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

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"

_TIMEOUT = 15.0

# Maps internal tool names to tool names on the GitHub MCP server.
# These are provisional — §4 Step 3 says to confirm via tools/list.
# ponytail: hardcoded map, replace if tools/list returns different names
_TOOL_NAME_MAP: dict[str, str] = {
    "github.list_issues": "list_issues",
    "github.create_issue": "create_issue",
    "github.comment_on_issue": "add_issue_comment",
    "github.create_pr_comment": "add_pull_request_review_comment",
}

# Tools that mutate state — need idempotency precheck.
_MUTATING_TOOLS: frozenset[str] = frozenset({
    "github.create_issue",
})

# Per-user session cache: user_id → (session_id, token)
# ponytail: module-level dict, per-process TTL cache if multiprocess matters
_session_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Token fetch
# ---------------------------------------------------------------------------


def _fetch_github_token(user_id: str) -> str | None:
    """Fetch and decrypt the user's GitHub OAuth token from oauth_connections."""
    try:
        result = (
            supabase.table("oauth_connections")
            .select("access_token")
            .eq("user_id", user_id)
            .eq("provider", "github")
            .single()
            .execute()
        )
        if not result.data:
            logger.warning("github: no GitHub token found for user_id=%s", user_id)
            return None

        encrypted_token = result.data["access_token"]
        try:
            fernet = Fernet(settings.ENCRYPTION_KEY.encode())
            return fernet.decrypt(encrypted_token.encode()).decode()
        except Exception:
            # If decryption fails, token may be stored unencrypted (dev/test)
            logger.debug("github: Fernet decrypt failed, using raw token for user_id=%s", user_id)
            return encrypted_token
    except Exception:
        logger.error("github: failed to fetch token for user_id=%s", user_id, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Idempotency precheck (create_issue only)
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
            "github: idempotency precheck failed for plan_id=%s step=%d — proceeding",
            plan_id, step_index, exc_info=True,
        )
    return None


# ---------------------------------------------------------------------------
# SSE response parsing
# ---------------------------------------------------------------------------


def _parse_sse_json(response: httpx.Response) -> dict:
    """Extract the JSON-RPC payload from an SSE text/event-stream response.

    GitHub's MCP server returns text/event-stream with lines like:
        event: message
        data: {"jsonrpc":"2.0", ...}

    Falls back to response.json() if content-type is application/json.
    """
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        return response.json()

    for line in response.text.splitlines():
        if line.startswith("data: "):
            import json
            return json.loads(line[6:])

    raise ValueError("no data: line found in SSE response")


# ---------------------------------------------------------------------------
# MCP session lifecycle
# ---------------------------------------------------------------------------


def _initialize_session(token: str) -> tuple[str, str] | None:
    """Run the MCP initialize handshake. Returns (session_id, protocol_version) or None."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "agentops-backend", "version": "0.1"},
        },
    }
    try:
        resp = httpx.post(GITHUB_MCP_URL, json=payload, headers=headers, timeout=_TIMEOUT)
    except Exception:
        logger.error("github: initialize failed", exc_info=True)
        return None

    if not resp.is_success:
        logger.error("github: initialize returned HTTP %d", resp.status_code)
        return None

    session_id = resp.headers.get("mcp-session-id", "")
    if not session_id:
        logger.warning("github: no mcp-session-id in initialize response")
        return None

    # Send notifications/initialized (fire-and-forget, no response expected)
    try:
        notify_headers = {**headers, "Mcp-Session-Id": session_id}
        httpx.post(
            GITHUB_MCP_URL,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers=notify_headers,
            timeout=_TIMEOUT,
        )
    except Exception:
        logger.debug("github: notifications/initialized failed (non-fatal)")

    return session_id, "2025-06-18"


def _get_session_id(user_id: str, token: str) -> str | None:
    """Get or create an MCP session for this user."""
    cached = _session_cache.get(user_id)
    if cached:
        return cached

    result = _initialize_session(token)
    if result is None:
        return None

    session_id, _ = result
    _session_cache[user_id] = session_id
    return session_id


def _invalidate_session(user_id: str) -> None:
    """Drop cached session so next call re-initializes."""
    _session_cache.pop(user_id, None)


# ---------------------------------------------------------------------------
# Execution log stub
# ---------------------------------------------------------------------------


async def _log_execution(event_type: str, payload: dict, latency_ms: int) -> None:
    """Log to execution_logs table.

    The table exists (migration 20260909000009), but the insert helper isn't
    wired yet.  Stub with debug logging for now.
    """
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


def _call_github_mcp(
    tool_name: str,
    mcp_tool: str,
    input_params: dict[str, Any],
    user_id: str,
    token: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Call a GitHub tool via the MCP server."""
    t0 = time.monotonic()

    # Get or create session
    session_id = _get_session_id(user_id, token)
    if not session_id:
        return _make_error("SESSION_EXPIRED", "failed to initialize MCP session", 0)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Mcp-Session-Id": session_id,
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
        response = httpx.post(GITHUB_MCP_URL, json=payload, headers=headers, timeout=_TIMEOUT)
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _make_error("TIMEOUT", "timeout calling GitHub MCP server", latency_ms)
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _make_error("PROVIDER_ERROR", f"network error: {exc}", latency_ms)

    latency_ms = int((time.monotonic() - t0) * 1000)

    # HTTP-level errors
    if response.status_code == 401:
        _invalidate_session(user_id)
        return _make_error("AUTH_EXPIRED", "token revoked or expired — user must reconnect GitHub", latency_ms)

    if response.status_code == 429:
        return {"status": "rate_limited", "output": None, "error": {"code": "RATE_LIMITED", "message": "rate limited"}, "latency_ms": latency_ms}

    # Session rejected — retry once with fresh session
    if response.status_code in (404, 410):
        _invalidate_session(user_id)
        session_id = _get_session_id(user_id, token)
        if not session_id:
            return _make_error("SESSION_EXPIRED", "session expired and re-init failed", latency_ms)
        headers["Mcp-Session-Id"] = session_id
        try:
            response = httpx.post(GITHUB_MCP_URL, json=payload, headers=headers, timeout=_TIMEOUT)
        except Exception:
            return _make_error("SESSION_EXPIRED", "session retry failed", latency_ms)
        latency_ms = int((time.monotonic() - t0) * 1000)

    if not response.is_success:
        return _make_error("PROVIDER_ERROR", f"GitHub MCP returned HTTP {response.status_code}", latency_ms)

    # Parse SSE response
    try:
        body = _parse_sse_json(response)
    except Exception:
        logger.error("github: failed to parse response [tool=%s]", tool_name)
        return _make_error("PROVIDER_ERROR", "invalid response from GitHub MCP server", latency_ms)

    if "error" in body:
        rpc_error = body["error"]
        code = str(rpc_error.get("code", "PROVIDER_ERROR"))
        msg = rpc_error.get("message", "unknown MCP error")
        # Check for invalid params
        if rpc_error.get("code") == -32602:
            return _make_error("INVALID_PARAMS", msg, latency_ms)
        return _make_error("PROVIDER_ERROR", msg, latency_ms)

    result = body.get("result", {})
    logger.info("github: success [tool=%s user=%s latency=%dms]", tool_name, user_id, latency_ms)
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
    """Route a GitHub tool call to the MCP server.

    Args:
        tool_name:        Internal tool name e.g. ``github.create_issue``.
        input_params:     Tool arguments from the plan step.
        user_id:          UUID of the acting user.
        idempotency_key:  ``plan_id:step_index`` for deduplication.

    Returns:
        Standard AgentOps MCP envelope::

            {
                "status":     "success" | "error" | "rate_limited",
                "output":     dict | None,
                "error":      dict | None,   # {"code": ..., "message": ...}
                "latency_ms": int,
            }
    """
    # 1. Resolve tool name
    mcp_tool = _TOOL_NAME_MAP.get(tool_name)
    if mcp_tool is None:
        logger.error("github: unknown tool_name=%s", tool_name)
        return _make_error("INVALID_PARAMS", f"unknown tool: {tool_name}", 0)

    # 2. Idempotency precheck for mutating tools
    if tool_name in _MUTATING_TOOLS:
        try:
            plan_id, step_index_str = idempotency_key.split(":", 1)
            cached = _already_done(plan_id, int(step_index_str))
            if cached is not None:
                logger.info("github: skipped — step already done [key=%s]", idempotency_key)
                return {"status": "success", "output": cached, "error": None, "latency_ms": 0}
        except (ValueError, AttributeError):
            logger.warning("github: bad idempotency_key=%r — skipping precheck", idempotency_key)

    # 3. Fetch token
    token = _fetch_github_token(user_id)
    if not token:
        return _make_error("AUTH_EXPIRED", "no GitHub OAuth token — user must connect GitHub", 0)

    # 4. Call MCP
    return _call_github_mcp(tool_name, mcp_tool, input_params, user_id, token, idempotency_key)
