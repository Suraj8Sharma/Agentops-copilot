import asyncio
from unittest.mock import MagicMock, patch

import pytest

USER_ID = "user_123"
IDEMPOTENCY_KEY = "idem-k"


@pytest.mark.asyncio
async def test_d32_mcp_burst_survives_429s_across_clients():
    """
    D32 MCP load-test pattern:
    concurrent burst calls across GitHub/Gmail/Slack should all degrade to a
    clean rate_limited result instead of crashing or hanging under provider quotas.
    """

    def _make_resp(status_code: int):
        resp = MagicMock()
        resp.status_code = status_code
        resp.is_success = False
        resp.headers = {}
        return resp

    async def _run_github():
        from app.mcp_clients.github import _session_cache, call

        _session_cache.clear()
        _session_cache[USER_ID] = "sess"
        mock_sb = MagicMock()
        with (
            patch("app.mcp_clients.github.supabase", mock_sb),
            patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
            patch("httpx.post", return_value=_make_resp(429)),
        ):
            return call("github.list_issues", {"repo": "o/r"}, USER_ID, IDEMPOTENCY_KEY)

    async def _run_slack():
        from app.mcp_clients.slack import call

        mock_sb = MagicMock()
        with (
            patch("app.mcp_clients.slack.supabase", mock_sb),
            patch("app.mcp_clients.slack.settings", MagicMock(ENCRYPTION_KEY="")),
            patch("httpx.post", return_value=_make_resp(429)),
        ):
            return call("slack.list_channels", {}, USER_ID, IDEMPOTENCY_KEY)

    async def _run_gmail():
        from app.mcp_clients.gmail import call

        mock_sb = MagicMock()
        with (
            patch("app.mcp_clients.gmail.supabase", mock_sb),
            patch("app.mcp_clients.gmail.get_valid_google_token", return_value="token"),
            patch("httpx.get", return_value=_make_resp(429)),
        ):
            return call("gmail.list_messages", {}, USER_ID, IDEMPOTENCY_KEY)

    github_results, slack_results, gmail_results = await asyncio.gather(
        asyncio.gather(*[_run_github() for _ in range(4)]),
        asyncio.gather(*[_run_slack() for _ in range(4)]),
        asyncio.gather(*[_run_gmail() for _ in range(4)]),
    )

    assert all(r["status"] == "rate_limited" for r in github_results)
    assert all(r["status"] == "rate_limited" for r in slack_results)
    assert all(r["status"] == "rate_limited" for r in gmail_results)


@pytest.mark.asyncio
async def test_d32_mcp_client_429_is_cleanly_reported_for_each_provider():
    """Each provider maps HTTP 429 to a structured rate-limited status."""

    def _make_resp(status_code: int):
        resp = MagicMock()
        resp.status_code = status_code
        resp.is_success = False
        resp.headers = {}
        return resp

    from app.mcp_clients.github import call as github_call
    from app.mcp_clients.gmail import call as gmail_call
    from app.mcp_clients.slack import call as slack_call

    with (
        patch("app.mcp_clients.github.supabase", MagicMock()),
        patch("app.mcp_clients.github.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", return_value=_make_resp(429)),
    ):
        github_result = github_call("github.list_issues", {"repo": "o/r"}, USER_ID, IDEMPOTENCY_KEY)

    with (
        patch("app.mcp_clients.slack.supabase", MagicMock()),
        patch("app.mcp_clients.slack.settings", MagicMock(ENCRYPTION_KEY="")),
        patch("httpx.post", return_value=_make_resp(429)),
    ):
        slack_result = slack_call("slack.list_channels", {}, USER_ID, IDEMPOTENCY_KEY)

    with (
        patch("app.mcp_clients.gmail.supabase", MagicMock()),
        patch("app.mcp_clients.gmail.get_valid_google_token", return_value="token"),
        patch("httpx.get", return_value=_make_resp(429)),
    ):
        gmail_result = gmail_call("gmail.list_messages", {}, USER_ID, IDEMPOTENCY_KEY)

    assert github_result["status"] == "rate_limited"
    assert slack_result["status"] == "rate_limited"
    assert gmail_result["status"] == "rate_limited"
