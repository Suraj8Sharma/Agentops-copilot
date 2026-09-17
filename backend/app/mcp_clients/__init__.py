"""MCP client router for AgentOps Copilot.

Single entry point for the execute node. Routes a tool call to the correct
provider client based on the ``mcp_server`` field of the plan step.

Usage::

    from app.mcp_clients import call_tool

    result = call_tool(
        tool_name="calendar.create_event_internal_only",
        mcp_server="calendar",
        input_params={...},
        user_id="uuid",
        idempotency_key="plan_id:0",
    )

Returns the standard AgentOps MCP envelope:
    { status, output, error, latency_ms }

Adding a new provider (D15 Gmail, D16 GitHub/Slack):
    1. Create app/mcp_clients/<provider>.py with a call() function.
    2. Import it here and add an entry to _ROUTER.
    The execute node needs no changes.
"""

from __future__ import annotations

import logging
from typing import Any

from app.mcp_clients import calendar, github, gmail, slack

logger = logging.getLogger(__name__)

# Maps mcp_server field → provider client module.
_ROUTER = {
    "calendar": calendar,
    "gmail": gmail,
    "github": github,
    "slack": slack,
}


def call_tool(
    tool_name: str,
    mcp_server: str,
    input_params: dict[str, Any],
    user_id: str,
    idempotency_key: str,
    task_id: str = "unknown",
) -> dict[str, Any]:
    """Route a tool call to the correct MCP provider client.

    Args:
        tool_name:        Internal tool name e.g. ``calendar.list_events``.
        mcp_server:       Provider key e.g. ``"calendar"``.
        input_params:     Tool arguments from the plan step.
        user_id:          UUID of the acting user.
        idempotency_key:  ``plan_id:step_index`` for deduplication.
        task_id:          UUID of the parent task — forwarded to the client so
                          it can write execution_logs rows with the correct FK.

    Returns:
        Standard envelope: ``{ status, output, error, latency_ms }``
    """
    client = _ROUTER.get(mcp_server)
    if client is None:
        logger.error(
            "mcp_clients: no client registered for mcp_server=%s [tool=%s]",
            mcp_server,
            tool_name,
        )
        return {
            "status": "error",
            "output": None,
            "error": f"no MCP client registered for provider '{mcp_server}'",
            "latency_ms": 0,
        }

    return client.call(
        tool_name=tool_name,
        input_params=input_params,
        user_id=user_id,
        idempotency_key=idempotency_key,
        task_id=task_id,
    )
