import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.router import route_llm_call
from app.llm.types import LLMProvider, LLMRateLimitError, LLMResponse


@pytest.mark.asyncio
async def test_d32_free_tier_concurrent_load_backoff_and_fallback():
    """
    D32 exact load-test pattern:
    - many concurrent requests hit the free-tier LLM stack together
    - both providers briefly rate-limit
    - router backs off and retries
    - all requests still succeed via fallback without hammering providers
    """
    gemini_calls = {"count": 0}

    def gemini_response_factory():
        return LLMResponse(
            text="Recovered under D32 concurrent free-tier load",
            provider=LLMProvider.GEMINI,
            model="gemini-3.7-flash",
            tokens_in=12,
            tokens_out=18,
            latency_ms=220,
            rate_limited=False,
        )

    async def mock_groq(*args, **kwargs):
        raise LLMRateLimitError("Groq rate limited under concurrent burst")

    async def mock_gemini(*args, **kwargs):
        gemini_calls["count"] += 1
        if gemini_calls["count"] == 1:
            raise LLMRateLimitError("Gemini rate limited under concurrent burst")
        return gemini_response_factory()

    with patch("app.llm.router.call_groq", new_callable=AsyncMock, side_effect=mock_groq):
        with patch("app.llm.router.call_gemini", new_callable=AsyncMock, side_effect=mock_gemini):
            with patch("app.llm.router.log_llm_usage"):
                with patch("app.llm.router.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                    results = await asyncio.gather(
                        *[
                            route_llm_call(
                                prompt=f"D32 burst request {i}",
                                request_type="planning",
                            )
                            for i in range(12)
                        ]
                    )

    assert len(results) == 12
    assert all(r.provider == LLMProvider.GEMINI for r in results)
    assert mock_sleep.await_count >= 1
    assert any(call.args[0] >= 5.0 for call in mock_sleep.await_args_list)


@pytest.mark.asyncio
async def test_d32_exhaustion_stays_fail_closed_after_free_tier_retry_budget():
    """
    If both providers stay rate-limited through the retry budget, the router must
    fail closed instead of silently pretending the request succeeded.
    """
    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq:
        mock_groq.side_effect = LLMRateLimitError("Groq rate limited")

        with patch("app.llm.router.call_gemini", new_callable=AsyncMock) as mock_gemini:
            mock_gemini.side_effect = LLMRateLimitError("Gemini rate limited")

            with patch("app.llm.router.log_llm_usage"):
                with patch("app.llm.router.asyncio.sleep", new_callable=AsyncMock):
                    with pytest.raises(Exception):
                        await route_llm_call(
                            prompt="D32 exhaustion replay",
                            request_type="planning",
                        )

    assert mock_groq.call_count >= 1
    assert mock_gemini.call_count >= 1
