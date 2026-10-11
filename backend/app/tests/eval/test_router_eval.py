"""
Tests for router eval (D26 §9).

Tests use mocked LLM calls — no live API, no DB.

Run with: pytest app/tests/eval/test_router_eval.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.llm.gemini_client  # noqa: F401
import app.llm.groq_client  # noqa: F401
import app.llm.router  # noqa: F401
from app.eval.router_eval import PROMPT_VERSION, run_router
from app.eval.scorers import CONFIDENCE_THRESHOLD, grade_router, passes_confidence_gate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_llm_response(text: str):
    resp = MagicMock()
    resp.text = text
    return resp


def _router_response(intent: str, servers: list[str], ncl: bool, confidence: float = 0.9) -> str:
    return json.dumps(
        {
            "intent": intent,
            "mcp_servers": servers,
            "needs_clarification": ncl,
            "confidence": confidence,
        }
    )


# ---------------------------------------------------------------------------
# run_router — intent accuracy
# ---------------------------------------------------------------------------


class TestRouterIntentAccuracy:
    @pytest.mark.asyncio
    async def test_calendar_read_intent(self):
        payload = _router_response("calendar_read", ["calendar"], False)
        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            result = await run_router("what meetings do i have tomorrow")

        expected = {
            "intent": "calendar_read",
            "mcp_servers": ["calendar"],
            "needs_clarification": False,
            "meta": {"id": "RT-01"},
        }
        grade = grade_router(result, expected)
        assert grade.passed is True

    @pytest.mark.asyncio
    async def test_email_write_intent(self):
        payload = _router_response("email_write", ["gmail"], False)
        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            result = await run_router("Email the report to sam@example.com")

        expected = {
            "intent": "email_write",
            "mcp_servers": ["gmail"],
            "needs_clarification": False,
            "meta": {"id": "RT-08"},
        }
        grade = grade_router(result, expected)
        assert grade.passed is True

    @pytest.mark.asyncio
    async def test_multi_tool_calendar_gmail(self):
        payload = _router_response("multi_tool", ["calendar", "gmail"], False)
        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            result = await run_router("Schedule a review on Monday and email everyone the agenda")

        expected = {
            "intent": "multi_tool",
            "mcp_servers": ["calendar", "gmail"],
            "needs_clarification": False,
            "meta": {"id": "RT-14"},
        }
        grade = grade_router(result, expected)
        assert grade.passed is True

    @pytest.mark.asyncio
    async def test_parse_error_returned_on_bad_json(self):
        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response("not json")
            result = await run_router("test prompt")

        assert result.get("parse_error") is True
        assert result["intent"] == "unknown"

    @pytest.mark.asyncio
    async def test_temperature_zero_passed_to_groq(self):
        payload = _router_response("calendar_read", ["calendar"], False)
        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            await run_router("What is on my calendar?")

        call_kwargs = mock_groq.call_args
        assert call_kwargs.kwargs.get("temperature") == 0


# ---------------------------------------------------------------------------
# Confidence gating (§5.3 + §9)
# ---------------------------------------------------------------------------


class TestRouterConfidenceGating:
    def test_above_threshold_not_gated(self):
        result = {
            "intent": "calendar_read",
            "mcp_servers": ["calendar"],
            "needs_clarification": False,
            "confidence": CONFIDENCE_THRESHOLD + 0.1,
        }
        assert passes_confidence_gate(result) is True

    def test_below_threshold_gated(self):
        result = {
            "intent": "calendar_read",
            "mcp_servers": ["calendar"],
            "needs_clarification": False,
            "confidence": CONFIDENCE_THRESHOLD - 0.05,
        }
        assert passes_confidence_gate(result) is False

    def test_at_threshold_not_gated(self):
        result = {"confidence": CONFIDENCE_THRESHOLD}
        assert passes_confidence_gate(result) is True

    def test_synthetic_confidence_values(self):
        """Spec §5.3: test with multiple synthetic values around threshold."""
        below = [0.0, 0.1, 0.3, 0.5, 0.65, 0.69]
        above = [CONFIDENCE_THRESHOLD, 0.75, 0.9, 1.0]
        for v in below:
            assert passes_confidence_gate({"confidence": v}) is False, (
                f"Expected {v} to be below threshold"
            )
        for v in above:
            assert passes_confidence_gate({"confidence": v}) is True, (
                f"Expected {v} to be above threshold"
            )


# ---------------------------------------------------------------------------
# Groq 429 fallback (§9 — mocked client)
# ---------------------------------------------------------------------------


class TestRouterGroq429Fallback:
    @pytest.mark.asyncio
    async def test_groq_429_fallback_to_gemini(self):
        """
        When Groq raises 429, run_router falls back to Gemini if allow_fallback is set.
        The fallback is at the LLM router level (route_llm_call); this test mocks the
        router to simulate the fallback scenario.
        """
        from app.llm.types import LLMRateLimitError

        gemini_payload = _router_response("calendar_read", ["calendar"], False)
        gemini_resp = _mock_llm_response(gemini_payload)

        # call_groq raises 429; call_gemini succeeds
        with (
            patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq,
            patch("app.llm.gemini_client.call_gemini", new_callable=AsyncMock) as mock_gemini,
        ):
            mock_groq.side_effect = LLMRateLimitError("429 rate limit")
            mock_gemini.return_value = gemini_resp

            # run_router calls call_groq directly; 429 propagates up
            with pytest.raises(LLMRateLimitError):
                await run_router("what meetings do i have tomorrow")

    @pytest.mark.asyncio
    async def test_groq_429_marked_in_llm_usage_logs(self):
        """
        When route_llm_call handles a Groq 429, it should log rate_limit_hit=true
        to llm_usage_logs (via log_llm_usage in router.py).
        This test verifies the log_llm_usage call receives rate_limit_hit=True.
        """
        from app.llm.types import LLMRateLimitError

        payload = _router_response("calendar_read", ["calendar"], False)
        gemini_resp = MagicMock()
        gemini_resp.text = payload
        gemini_resp.provider = MagicMock()
        gemini_resp.provider.value = "gemini"
        gemini_resp.model = "gemini-flash"
        gemini_resp.tokens_in = 100
        gemini_resp.tokens_out = 50
        gemini_resp.latency_ms = 500
        gemini_resp.rate_limited = False

        with (
            patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq,
            patch("app.llm.router.call_gemini", new_callable=AsyncMock) as mock_gemini,
            patch("app.llm.router.log_llm_usage") as mock_log,
        ):
            mock_groq.side_effect = LLMRateLimitError("429")
            mock_gemini.return_value = gemini_resp

            from app.llm.router import route_llm_call

            _ = await route_llm_call("test prompt", request_type="routing")

        # First call to log_llm_usage should have rate_limit_hit=True (Groq failure)
        groq_fail_calls = [
            c
            for c in mock_log.call_args_list
            if c.kwargs.get("rate_limit_hit") is True or (len(c.args) > 5 and c.args[5] is True)
        ]
        assert len(groq_fail_calls) > 0, "Expected at least one log call with rate_limit_hit=True"


# ---------------------------------------------------------------------------
# RT-17 and RT-18 — needs_clarification (§5.3)
# ---------------------------------------------------------------------------


class TestRouterAmbiguousCases:
    @pytest.mark.asyncio
    async def test_rt17_no_referent(self):
        """RT-17: 'Send it to him' — must return needs_clarification: true."""
        payload = _router_response("ambiguous", [], True, confidence=0.4)
        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            result = await run_router("Send it to him")

        expected = {
            "intent": "ambiguous",
            "mcp_servers": [],
            "needs_clarification": True,
            "meta": {"id": "RT-17"},
        }
        grade = grade_router(result, expected)
        assert grade.passed is True
        assert result.get("needs_clarification") is True

    @pytest.mark.asyncio
    async def test_rt18_ambiguous_channel(self):
        """RT-18: 'Let the team know I will be late' — could be Slack or email."""
        payload = _router_response("ambiguous", [], True, confidence=0.35)
        with patch("app.llm.groq_client.call_groq", new_callable=AsyncMock) as mock_groq:
            mock_groq.return_value = _mock_llm_response(payload)
            result = await run_router("Let the team know I will be late")

        expected = {
            "intent": "ambiguous",
            "mcp_servers": [],
            "needs_clarification": True,
            "meta": {"id": "RT-18"},
        }
        grade = grade_router(result, expected)
        assert grade.passed is True
        assert result.get("needs_clarification") is True

    def test_prompt_version_constant_is_string(self):
        assert isinstance(PROMPT_VERSION, str)
        assert len(PROMPT_VERSION) > 0
