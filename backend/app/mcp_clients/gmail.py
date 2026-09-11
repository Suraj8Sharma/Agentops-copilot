"""Gmail MCP client for AgentOps Copilot.

Two integrations, one envelope:

    gmail.list_messages   → Gmail MCP server  (search_threads)
    gmail.get_message     → Gmail MCP server  (get_message)
    gmail.create_draft    → Gmail MCP server  (create_draft)
    gmail.send_message    → Gmail REST API    (users.messages.send)

All four tools authenticate using the user's own Google OAuth token stored in
oauth_connections (provider='gmail').  There is no shared sender address and
no third-party relay — sent mail arrives from and is owned by the user's own
Google account.

The send path includes an application-level idempotency precheck against
plan_steps.status because the Gmail REST API has no idempotency-key header —
a retried call after a timeout would otherwise send a duplicate email from
the user's real account.

The planner and risk gate never import this module directly.  The execute
node calls it via call_tool() in mcp_clients/__init__.py.
"""

from __future__ import annotations

import base64
import logging
import time
from email.mime.text import MIMEText
from typing import Any

import httpx
from cryptography.fernet import Fernet

from app.core.config import settings
from app.db.supabase_client import supabase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

GMAIL_MCP_URL = "https://gmailmcp.googleapis.com/mcp/v1"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# ---------------------------------------------------------------------------
# Tool routing tables
# ---------------------------------------------------------------------------

# Maps our internal tool names to the actual tool names on the Gmail MCP server.
# Verified against the official Google Gmail MCP Developer Preview docs.
_MCP_TOOL_MAP: dict[str, str] = {
    "gmail.list_messages": "search_threads",  # MCP server has no list_messages tool
    "gmail.get_message": "get_message",
    "gmail.create_draft": "create_draft",
}

# Tools routed to the Gmail REST API directly (MCP server has no send capability).
_SEND_TOOLS: frozenset[str] = frozenset({"gmail.send_message"})

# HTTP timeout for all outbound calls (seconds).
_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Token fetch
# ---------------------------------------------------------------------------


def _fetch_google_token(user_id: str) -> str | None:
    """Fetch and decrypt the user's Google OAuth access token from oauth_connections.

    Note: The callback stores Gmail tokens under provider='gmail' (not 'google'),
    since one Google consent yields two rows — 'google_calendar' and 'gmail'.
    """
    try:
        result = (
            supabase.table("oauth_connections")
            .select("access_token")
            .eq("user_id", user_id)
            .eq("provider", "gmail")
            .single()
            .execute()
        )
        if not result.data:
            logger.warning("gmail: no Gmail token found for user_id=%s", user_id)
            return None

        encrypted_token = result.data["access_token"]
        try:
            fernet = Fernet(settings.ENCRYPTION_KEY.encode())
            return fernet.decrypt(encrypted_token.encode()).decode()
        except Exception:
            logger.debug("gmail: Fernet decrypt failed, using raw token for user_id=%s", user_id)
            return encrypted_token
    except Exception:
        logger.error(
            "gmail: failed to fetch token for user_id=%s",
            user_id,
            exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# Idempotency precheck (send path only)
# ---------------------------------------------------------------------------


def _already_sent(plan_id: str, step_index: int) -> dict | None:
    """Return the cached output if this send step already completed successfully.

    The Gmail REST API has no idempotency-key header, so we guard at the
    application level: if plan_steps already shows status='done' with a
    non-null output for this exact step, we return that output immediately
    without making any HTTP call.

    Returns the cached output dict, or None if the step has not yet succeeded.
    """
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
        # If the precheck itself fails, let the call proceed — a duplicate
        # send is preferable to silently dropping a user-requested action.
        logger.warning(
            "gmail: idempotency precheck failed for plan_id=%s step=%d — proceeding",
            plan_id,
            step_index,
            exc_info=True,
        )
    return None


# ---------------------------------------------------------------------------
# Internal: Gmail MCP path
# ---------------------------------------------------------------------------


def _call_gmail_mcp(
    tool_name: str,
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Call a Gmail read/draft tool via the official Gmail MCP remote server."""
    t0 = time.monotonic()

    # 1. Resolve MCP tool name
    mcp_tool = _MCP_TOOL_MAP.get(tool_name)
    if mcp_tool is None:
        return {
            "status": "error",
            "output": None,
            "error": f"unknown tool: {tool_name}",
            "latency_ms": 0,
        }

    # 2. Fetch user token
    token = _fetch_google_token(user_id)
    if not token:
        return {
            "status": "error",
            "output": None,
            "error": "no Gmail OAuth token for user — user must reconnect Google account",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    # 3. Build MCP JSON-RPC payload
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
        "X-Idempotency-Key": idempotency_key,
    }

    # 4. Call the MCP server
    try:
        response = httpx.post(GMAIL_MCP_URL, json=payload, headers=headers, timeout=_TIMEOUT)
    except httpx.TimeoutException:
        logger.warning("gmail: timeout calling MCP server [tool=%s user=%s]", tool_name, user_id)
        return {
            "status": "error",
            "output": None,
            "error": "timeout",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }
    except httpx.RequestError as exc:
        logger.error("gmail: network error [tool=%s]: %s", tool_name, exc)
        return {
            "status": "error",
            "output": None,
            "error": f"network error: {exc}",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    latency_ms = int((time.monotonic() - t0) * 1000)

    # 5. Handle HTTP-level errors
    if response.status_code == 429:
        logger.warning("gmail: rate limited [tool=%s user=%s]", tool_name, user_id)
        return {
            "status": "rate_limited",
            "output": None,
            "error": "rate_limited",
            "latency_ms": latency_ms,
        }

    if response.status_code == 401:
        logger.warning("gmail: 401 unauthorized [tool=%s user=%s]", tool_name, user_id)
        return {
            "status": "error",
            "output": None,
            "error": "unauthorized — token expired or revoked",
            "latency_ms": latency_ms,
        }

    if not response.is_success:
        logger.error(
            "gmail: HTTP %d from MCP server [tool=%s user=%s]",
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

    # 6. Parse JSON-RPC response
    try:
        body = response.json()
    except Exception:
        logger.error("gmail: non-JSON response from MCP server [tool=%s]", tool_name)
        return {
            "status": "error",
            "output": None,
            "error": "invalid JSON from MCP server",
            "latency_ms": latency_ms,
        }

    if "error" in body:
        rpc_error = body["error"]
        logger.warning(
            "gmail: MCP RPC error [tool=%s code=%s msg=%s]",
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
    logger.info("gmail: success [tool=%s user=%s latency=%dms]", tool_name, user_id, latency_ms)
    return {"status": "success", "output": result, "error": None, "latency_ms": latency_ms}


# ---------------------------------------------------------------------------
# Internal: Gmail REST send path
# ---------------------------------------------------------------------------


def _call_gmail_send(
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Send an email via the Gmail REST API using the user's own OAuth token.

    Sending from the user's own account means:
    - The From address is the user's real Google address (set by Gmail automatically).
    - Replies land in the user's own inbox naturally.
    - No shared sender domain, no third-party relay.

    Idempotency is enforced at the application level via _already_sent():
    the Gmail REST API has no idempotency-key header.
    """
    t0 = time.monotonic()

    # 0. Idempotency precheck — parse plan_id and step_index from the key
    try:
        plan_id, step_index_str = idempotency_key.split(":", 1)
        step_index = int(step_index_str)
        cached = _already_sent(plan_id, step_index)
        if cached is not None:
            logger.info(
                "gmail: send skipped — step already done [plan_id=%s step=%d]",
                plan_id,
                step_index,
            )
            return {
                "status": "success",
                "output": cached,
                "error": None,
                "latency_ms": int((time.monotonic() - t0) * 1000),
            }
    except (ValueError, AttributeError):
        # Malformed idempotency_key — proceed without the precheck rather than
        # dropping the send entirely.
        logger.warning(
            "gmail: could not parse idempotency_key=%r — skipping precheck",
            idempotency_key,
        )

    # 1. Fetch user token
    token = _fetch_google_token(user_id)
    if not token:
        return {
            "status": "error",
            "output": None,
            "error": "no Gmail OAuth token for user — user must reconnect Google account",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    # 2. Build RFC 2822 MIME message
    # Gmail fills in the From address automatically from the authenticated account.
    to_field = input_params.get("to", [])
    if isinstance(to_field, list):
        to_str = ", ".join(to_field)
    else:
        to_str = str(to_field)

    msg = MIMEText(input_params.get("body", ""), "plain")
    msg["To"] = to_str
    msg["Subject"] = input_params.get("subject", "")

    # 3. Base64url-encode the raw MIME bytes (Gmail API requirement)
    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("ascii")

    # 4. POST to the Gmail REST API
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        response = httpx.post(
            GMAIL_SEND_URL,
            json={"raw": raw_b64},
            headers=headers,
            timeout=_TIMEOUT,
        )
    except httpx.TimeoutException:
        logger.warning("gmail: send timeout [user=%s]", user_id)
        return {
            "status": "error",
            "output": None,
            "error": "timeout",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }
    except httpx.RequestError as exc:
        logger.error("gmail: send network error: %s", exc)
        return {
            "status": "error",
            "output": None,
            "error": f"network error: {exc}",
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    latency_ms = int((time.monotonic() - t0) * 1000)

    # 5. Handle response
    if response.status_code == 429:
        logger.warning("gmail: send rate limited [user=%s]", user_id)
        return {
            "status": "rate_limited",
            "output": None,
            "error": "rate_limited",
            "latency_ms": latency_ms,
        }

    if response.status_code == 401:
        logger.warning("gmail: send 401 unauthorized [user=%s]", user_id)
        return {
            "status": "error",
            "output": None,
            "error": "unauthorized — token expired or revoked",
            "latency_ms": latency_ms,
        }

    if response.status_code == 403:
        logger.warning("gmail: send 403 insufficient scope [user=%s]", user_id)
        return {
            "status": "error",
            "output": None,
            "error": "insufficient scope — user must reconnect Google with mail-send permission",
            "latency_ms": latency_ms,
        }

    if not response.is_success:
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:
            detail = ""
        logger.error("gmail: send HTTP %d [user=%s] %s", response.status_code, user_id, detail)
        return {
            "status": "error",
            "output": None,
            "error": f"Gmail API returned HTTP {response.status_code}: {detail}".strip(": "),
            "latency_ms": latency_ms,
        }

    try:
        body = response.json()
    except Exception:
        body = {}

    output = {"id": body.get("id"), "threadId": body.get("threadId")}
    logger.info(
        "gmail: send success [user=%s msg_id=%s latency=%dms]",
        user_id,
        output.get("id"),
        latency_ms,
    )
    return {"status": "success", "output": output, "error": None, "latency_ms": latency_ms}


# ---------------------------------------------------------------------------
# Public entrypoint — called by mcp_clients/__init__.py
# ---------------------------------------------------------------------------


def call(
    tool_name: str,
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Route a Gmail tool call to the correct integration.

    Args:
        tool_name:        Internal tool name e.g. ``gmail.send_message``.
        input_params:     Tool arguments from the plan step.
        user_id:          UUID of the acting user.
        idempotency_key:  ``plan_id:step_index`` for deduplication.

    Returns:
        Standard AgentOps MCP envelope::

            {
                "status":     "success" | "error" | "rate_limited",
                "output":     dict | None,
                "error":      str | None,
                "latency_ms": int,
            }
    """
    if tool_name in _SEND_TOOLS:
        return _call_gmail_send(input_params, user_id, idempotency_key)

    if tool_name in _MCP_TOOL_MAP:
        return _call_gmail_mcp(tool_name, input_params, user_id, idempotency_key)

    logger.error("gmail: unknown tool_name=%s", tool_name)
    return {
        "status": "error",
        "output": None,
        "error": f"unknown tool: {tool_name}",
        "latency_ms": 0,
    }
