"""Gmail REST client for AgentOps Copilot.

Previously the read/draft path talked to Google's Gmail MCP Developer Preview
server (gmailmcp.googleapis.com/mcp/v1) via JSON-RPC.  That server is
unstable in developer mode.  This revision replaces those calls with direct
Gmail REST API (v1) calls, authenticated with the same per-user OAuth token.

All four tools now use the Gmail REST API:

    gmail.list_messages   → GET  /users/me/threads          (search equivalent)
    gmail.get_message     → GET  /users/me/messages/{id}
    gmail.create_draft    → POST /users/me/drafts
    gmail.send_message    → POST /users/me/messages/send    (unchanged from Rev. 2)

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

from app.db.supabase_client import supabase
from app.mcp_clients.google_token_refresh import get_valid_google_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gmail REST API endpoints
# ---------------------------------------------------------------------------

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GMAIL_SEND_URL = f"{_GMAIL_BASE}/messages/send"
_THREADS_URL = f"{_GMAIL_BASE}/threads"
_MESSAGES_URL = f"{_GMAIL_BASE}/messages"
_DRAFTS_URL = f"{_GMAIL_BASE}/drafts"

# ---------------------------------------------------------------------------
# Tool routing tables
# ---------------------------------------------------------------------------

# Tools handled by Gmail REST read/draft endpoints (not the send endpoint).
_REST_READ_TOOLS: frozenset[str] = frozenset(
    {"gmail.list_messages", "gmail.get_message", "gmail.create_draft"}
)

# Tools routed to the Gmail REST API directly (MCP server has no send capability).
_SEND_TOOLS: frozenset[str] = frozenset({"gmail.send_message"})

# HTTP timeout for all outbound calls (seconds).
_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Token fetch
# ---------------------------------------------------------------------------


def _fetch_google_token(user_id: str) -> str | None:
    """Return a valid (possibly auto-refreshed) Google OAuth access token for Gmail.

    Delegates to ``google_token_refresh.get_valid_google_token`` which:
    - Returns the stored token immediately if it is not yet expired.
    - Calls Google's token endpoint to refresh it if it is expired or within
      5 minutes of expiry, persists the new token to the DB, and returns it.
    - Returns ``None`` if no token exists or the refresh fails (revoked, etc.).

    Note: The callback stores Gmail tokens under provider='gmail' (not 'google'),
    since one Google consent yields two rows — 'google_calendar' and 'gmail'.
    """
    token = get_valid_google_token(user_id, "gmail")
    if token is None:
        logger.warning("gmail: no valid Google token for user_id=%s", user_id)
    return token


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
# Execution log helper
# ---------------------------------------------------------------------------


def _log_event_gmail(
    task_id: str,
    event_type: str,
    payload: dict[str, Any],
    step_id: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Write one row to execution_logs for a Gmail MCP event (best-effort)."""
    try:
        row: dict[str, Any] = {
            "task_id": task_id,
            "agent_name": "mcp_gmail",
            "event_type": event_type,
            "payload": payload,
        }
        if step_id is not None:
            row["step_id"] = step_id
        if latency_ms is not None:
            row["latency_ms"] = latency_ms
        supabase.table("execution_logs").insert(row).execute()
    except Exception:
        logger.warning(
            "execution_logs write failed [mcp_gmail task_id=%s event_type=%s]",
            task_id,
            event_type,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Internal: shared HTTP error handler for Gmail REST read/draft path
# ---------------------------------------------------------------------------


def _handle_gmail_http_error(
    response: httpx.Response,
    tool_name: str,
    user_id: str,
    task_id: str,
    latency_ms: int,
) -> dict[str, Any] | None:
    """Return an error envelope for non-2xx responses, or None if OK."""
    if response.status_code == 429:
        logger.warning("gmail: rate limited [tool=%s user=%s]", tool_name, user_id)
        _log_event_gmail(task_id=task_id, event_type="error", latency_ms=latency_ms,
                         payload={"tool_name": tool_name, "error_code": "RATE_LIMITED", "message": "rate limited"})
        return {"status": "rate_limited", "output": None, "error": "rate_limited", "latency_ms": latency_ms}

    if response.status_code == 401:
        logger.warning("gmail: 401 unauthorized [tool=%s user=%s]", tool_name, user_id)
        _log_event_gmail(task_id=task_id, event_type="error", latency_ms=latency_ms,
                         payload={"tool_name": tool_name, "error_code": "AUTH_EXPIRED", "message": "unauthorized — token expired or revoked"})
        return {"status": "error", "output": None, "error": "unauthorized — token expired or revoked", "latency_ms": latency_ms}

    if response.status_code == 403:
        logger.warning("gmail: 403 forbidden [tool=%s user=%s]", tool_name, user_id)
        _log_event_gmail(task_id=task_id, event_type="error", latency_ms=latency_ms,
                         payload={"tool_name": tool_name, "error_code": "INSUFFICIENT_SCOPE",
                                  "message": "insufficient scope — user must reconnect Google with mail-send permission"})
        return {"status": "error", "output": None,
                "error": "insufficient scope — user must reconnect Google with mail-send permission",
                "latency_ms": latency_ms}

    if not response.is_success:
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:
            detail = ""
        msg = f"Gmail API returned HTTP {response.status_code}: {detail}".strip(": ")
        logger.error("gmail: HTTP %d [tool=%s user=%s] %s", response.status_code, tool_name, user_id, detail)
        _log_event_gmail(task_id=task_id, event_type="error", latency_ms=latency_ms,
                         payload={"tool_name": tool_name, "error_code": "PROVIDER_ERROR", "message": msg})
        return {"status": "error", "output": None, "error": msg, "latency_ms": latency_ms}

    return None  # response is OK


def _auth_headers_gmail(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Internal: Gmail REST read/draft path (replaces _call_gmail_mcp)
# ---------------------------------------------------------------------------


def _call_list_messages(
    input_params: dict[str, Any],
    token: str,
    tool_name: str,
    user_id: str,
    task_id: str,
    t0: float,
) -> dict[str, Any]:
    """GET /users/me/threads — search/list threads (replaces search_threads MCP tool)."""
    params: dict[str, Any] = {}
    if "q" in input_params:
        params["q"] = input_params["q"]
    if "maxResults" in input_params:
        params["maxResults"] = input_params["maxResults"]
    if "pageToken" in input_params:
        params["pageToken"] = input_params["pageToken"]
    if "labelIds" in input_params:
        params["labelIds"] = input_params["labelIds"]

    try:
        response = httpx.get(_THREADS_URL, params=params, headers=_auth_headers_gmail(token), timeout=_TIMEOUT)
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("gmail: timeout [tool=%s user=%s]", tool_name, user_id)
        _log_event_gmail(task_id=task_id, event_type="error", latency_ms=latency_ms,
                         payload={"tool_name": tool_name, "error_code": "TIMEOUT", "message": "timeout"})
        return {"status": "error", "output": None, "error": "timeout", "latency_ms": latency_ms}
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("gmail: network error [tool=%s]: %s", tool_name, exc)
        _log_event_gmail(task_id=task_id, event_type="error", latency_ms=latency_ms,
                         payload={"tool_name": tool_name, "error_code": "NETWORK_ERROR", "message": str(exc)})
        return {"status": "error", "output": None, "error": f"network error: {exc}", "latency_ms": latency_ms}

    latency_ms = int((time.monotonic() - t0) * 1000)
    err = _handle_gmail_http_error(response, tool_name, user_id, task_id, latency_ms)
    if err:
        return err
    return {"status": "success", "output": response.json(), "error": None, "latency_ms": latency_ms}


def _call_get_message(
    input_params: dict[str, Any],
    token: str,
    tool_name: str,
    user_id: str,
    task_id: str,
    t0: float,
) -> dict[str, Any]:
    """GET /users/me/messages/{id} — fetch a single message."""
    message_id = input_params.get("id") or input_params.get("messageId")
    if not message_id:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"status": "error", "output": None, "error": "missing required param: id", "latency_ms": latency_ms}

    params: dict[str, Any] = {}
    if "format" in input_params:
        params["format"] = input_params["format"]

    url = f"{_MESSAGES_URL}/{message_id}"
    try:
        response = httpx.get(url, params=params, headers=_auth_headers_gmail(token), timeout=_TIMEOUT)
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("gmail: timeout [tool=%s user=%s]", tool_name, user_id)
        _log_event_gmail(task_id=task_id, event_type="error", latency_ms=latency_ms,
                         payload={"tool_name": tool_name, "error_code": "TIMEOUT", "message": "timeout"})
        return {"status": "error", "output": None, "error": "timeout", "latency_ms": latency_ms}
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("gmail: network error [tool=%s]: %s", tool_name, exc)
        _log_event_gmail(task_id=task_id, event_type="error", latency_ms=latency_ms,
                         payload={"tool_name": tool_name, "error_code": "NETWORK_ERROR", "message": str(exc)})
        return {"status": "error", "output": None, "error": f"network error: {exc}", "latency_ms": latency_ms}

    latency_ms = int((time.monotonic() - t0) * 1000)
    err = _handle_gmail_http_error(response, tool_name, user_id, task_id, latency_ms)
    if err:
        return err
    return {"status": "success", "output": response.json(), "error": None, "latency_ms": latency_ms}


def _call_create_draft(
    input_params: dict[str, Any],
    token: str,
    tool_name: str,
    user_id: str,
    task_id: str,
    t0: float,
) -> dict[str, Any]:
    """POST /users/me/drafts — create an email draft."""
    # Build RFC 2822 MIME message body from input_params.
    to_field = input_params.get("to", [])
    to_str = ", ".join(to_field) if isinstance(to_field, list) else str(to_field)

    from email.mime.text import MIMEText  # already imported at top-level; safe to re-import
    msg = MIMEText(input_params.get("body", ""), "plain")
    msg["To"] = to_str
    msg["Subject"] = input_params.get("subject", "")

    import base64
    raw_b64 = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    body = {"message": {"raw": raw_b64}}

    try:
        response = httpx.post(_DRAFTS_URL, json=body, headers=_auth_headers_gmail(token), timeout=_TIMEOUT)
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("gmail: timeout [tool=%s user=%s]", tool_name, user_id)
        _log_event_gmail(task_id=task_id, event_type="error", latency_ms=latency_ms,
                         payload={"tool_name": tool_name, "error_code": "TIMEOUT", "message": "timeout"})
        return {"status": "error", "output": None, "error": "timeout", "latency_ms": latency_ms}
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("gmail: network error [tool=%s]: %s", tool_name, exc)
        _log_event_gmail(task_id=task_id, event_type="error", latency_ms=latency_ms,
                         payload={"tool_name": tool_name, "error_code": "NETWORK_ERROR", "message": str(exc)})
        return {"status": "error", "output": None, "error": f"network error: {exc}", "latency_ms": latency_ms}

    latency_ms = int((time.monotonic() - t0) * 1000)
    err = _handle_gmail_http_error(response, tool_name, user_id, task_id, latency_ms)
    if err:
        return err
    return {"status": "success", "output": response.json(), "error": None, "latency_ms": latency_ms}


# ---------------------------------------------------------------------------
# Internal: Gmail REST send path
# ---------------------------------------------------------------------------


def _call_gmail_send(
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
    task_id: str = "unknown",
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

    # 4. Log tool_called before any external effect
    _log_event_gmail(
        task_id=task_id,
        event_type="tool_called",
        payload={
            "tool_name": "gmail.send_message",
            "mcp_server": "gmail",
            "to": to_str,
            "subject": input_params.get("subject", ""),
        },  # noqa: E501
    )

    # 5. POST to the Gmail REST API
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
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning("gmail: send timeout [user=%s]", user_id)
        _log_event_gmail(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": "gmail.send_message",
                "mcp_server": "gmail",
                "error_code": "TIMEOUT",
                "message": "timeout",
            },  # noqa: E501
            latency_ms=latency_ms,
        )
        return {"status": "error", "output": None, "error": "timeout", "latency_ms": latency_ms}
    except httpx.RequestError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("gmail: send network error: %s", exc)
        _log_event_gmail(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": "gmail.send_message",
                "mcp_server": "gmail",
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

    # 6. Handle response
    if response.status_code == 429:
        logger.warning("gmail: send rate limited [user=%s]", user_id)
        _log_event_gmail(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": "gmail.send_message",
                "mcp_server": "gmail",
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
        }

    if response.status_code == 401:
        logger.warning("gmail: send 401 unauthorized [user=%s]", user_id)
        _log_event_gmail(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": "gmail.send_message",
                "mcp_server": "gmail",
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
        }

    if response.status_code == 403:
        logger.warning("gmail: send 403 insufficient scope [user=%s]", user_id)
        _log_event_gmail(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": "gmail.send_message",
                "mcp_server": "gmail",
                "error_code": "INSUFFICIENT_SCOPE",
                "message": (
                    "insufficient scope — user must reconnect Google with mail-send permission"
                ),
            },
            latency_ms=latency_ms,
        )
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
        _log_event_gmail(
            task_id=task_id,
            event_type="error",
            payload={
                "tool_name": "gmail.send_message",
                "mcp_server": "gmail",
                "error_code": "PROVIDER_ERROR",
                "message": f"Gmail API returned HTTP {response.status_code}: {detail}".strip(": "),
            },  # noqa: E501
            latency_ms=latency_ms,
        )
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
    _log_event_gmail(
        task_id=task_id,
        event_type="tool_result",
        payload={
            "tool_name": "gmail.send_message",
            "mcp_server": "gmail",
            "status": "success",
            "output": output,
        },  # noqa: E501
        latency_ms=latency_ms,
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
    task_id: str = "unknown",
) -> dict[str, Any]:
    """Route a Gmail tool call to the correct REST endpoint.

    Args:
        tool_name:        Internal tool name e.g. ``gmail.send_message``.
        input_params:     Tool arguments from the plan step.
        user_id:          UUID of the acting user.
        idempotency_key:  ``plan_id:step_index`` for deduplication.
        task_id:          UUID of the task execution.

    Returns:
        Standard AgentOps MCP envelope::

            {
                "status":     "success" | "error" | "rate_limited",
                "output":     dict | None,
                "error":      str | None,
                "latency_ms": int,
            }
    """
    # --- Send path (unchanged) -----------------------------------------------
    if tool_name in _SEND_TOOLS:
        return _call_gmail_send(input_params, user_id, idempotency_key, task_id=task_id)

    # --- Read / draft path — direct Gmail REST API ---------------------------
    if tool_name in _REST_READ_TOOLS:
        t0 = time.monotonic()

        # Fetch token (shared with send path)
        token = _fetch_google_token(user_id)
        if not token:
            return {
                "status": "error",
                "output": None,
                "error": "no Gmail OAuth token for user — user must reconnect Google account",
                "latency_ms": int((time.monotonic() - t0) * 1000),
            }

        # Log before any external effect
        _log_event_gmail(
            task_id=task_id,
            event_type="tool_called",
            payload={"tool_name": tool_name, "mcp_server": "gmail", "input_params": input_params},
        )

        if tool_name == "gmail.list_messages":
            result = _call_list_messages(input_params, token, tool_name, user_id, task_id, t0)
        elif tool_name == "gmail.get_message":
            result = _call_get_message(input_params, token, tool_name, user_id, task_id, t0)
        else:  # gmail.create_draft
            result = _call_create_draft(input_params, token, tool_name, user_id, task_id, t0)

        # Log success outcome
        if result["status"] == "success":
            latency_ms = result.get("latency_ms", 0)
            logger.info("gmail: success [tool=%s user=%s latency=%dms]", tool_name, user_id, latency_ms)
            _log_event_gmail(
                task_id=task_id,
                event_type="tool_result",
                payload={"tool_name": tool_name, "status": "success", "output": result["output"]},
                latency_ms=latency_ms,
            )

        return result

    # --- Unknown tool --------------------------------------------------------
    logger.error("gmail: unknown tool_name=%s", tool_name)
    return {
        "status": "error",
        "output": None,
        "error": f"unknown tool: {tool_name}",
        "latency_ms": 0,
    }
