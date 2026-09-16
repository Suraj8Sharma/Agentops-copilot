from unittest.mock import AsyncMock, patch

import pytest

from app.llm.router import route_llm_call
from app.llm.types import (
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    LLMRouterExhaustedError,
    LLMServerError,
)


@pytest.mark.asyncio
async def test_route_llm_call_happy_path():
    """
    Test happy path: Groq succeeds, returns response, one log line.
    """
    mock_response = LLMResponse(
        text="Hello! How can I help you?",
        provider=LLMProvider.GROQ,
        model="openai/gpt-oss-20b",
        tokens_in=10,
        tokens_out=15,
        latency_ms=250,
        rate_limited=False,
    )

    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = mock_response

        with patch("app.llm.router.log_llm_usage") as mock_log:
            response = await route_llm_call(
                prompt="Say hello in one sentence.",
                request_type="planning",
            )

        assert response == mock_response
        assert response.provider == LLMProvider.GROQ
        assert response.text == "Hello! How can I help you?"

        # Verify log was called exactly once (success)
        assert mock_log.call_count == 1
        call_args = mock_log.call_args
        assert call_args.kwargs["success"] is True
        assert call_args.kwargs["provider"] == "groq"
        assert call_args.kwargs["request_type"] == "planning"


@pytest.mark.asyncio
async def test_route_llm_call_fallback_on_rate_limit():
    """
    Test fallback path: Groq 429 -> Gemini succeeds, two log lines.
    """
    groq_error = LLMRateLimitError("Groq rate limited")

    gemini_response = LLMResponse(
        text="Hello from Gemini!",
        provider=LLMProvider.GEMINI,
        model="gemini-3.7-flash",
        tokens_in=10,
        tokens_out=15,
        latency_ms=300,
        rate_limited=True,
    )

    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq:
        mock_groq.side_effect = groq_error

        with patch("app.llm.router.call_gemini", new_callable=AsyncMock) as mock_gemini:
            mock_gemini.return_value = gemini_response

            with patch("app.llm.router.log_llm_usage") as mock_log:
                response = await route_llm_call(
                    prompt="Say hello in one sentence.",
                    request_type="planning",
                )

            assert response == gemini_response
            assert response.provider == LLMProvider.GEMINI
            assert response.text == "Hello from Gemini!"

            # Verify log was called twice (Groq failure + Gemini success)
            assert mock_log.call_count == 2

            # First log call: Groq failure
            first_call = mock_log.call_args_list[0]
            assert first_call.kwargs["success"] is False
            assert first_call.kwargs["provider"] == "groq"
            assert first_call.kwargs["rate_limit_hit"] is True

            # Second log call: Gemini success
            second_call = mock_log.call_args_list[1]
            assert second_call.kwargs["success"] is True
            assert second_call.kwargs["provider"] == "gemini"


@pytest.mark.asyncio
async def test_route_llm_call_fallback_on_server_error():
    """
    Test fallback path: Groq 5xx -> Gemini succeeds, two log lines.
    """
    groq_error = LLMServerError("Groq server error")

    gemini_response = LLMResponse(
        text="Recovered via Gemini",
        provider=LLMProvider.GEMINI,
        model="gemini-3.7-flash",
        tokens_in=10,
        tokens_out=15,
        latency_ms=350,
        rate_limited=False,
    )

    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq:
        mock_groq.side_effect = groq_error

        with patch("app.llm.router.call_gemini", new_callable=AsyncMock) as mock_gemini:
            mock_gemini.return_value = gemini_response

            with patch("app.llm.router.log_llm_usage") as mock_log:
                response = await route_llm_call(
                    prompt="Say hello in one sentence.",
                    request_type="risk_explanation",
                )

            assert response.provider == LLMProvider.GEMINI
            assert mock_log.call_count == 2


@pytest.mark.asyncio
async def test_route_llm_call_both_fail():
    """
    Test exhausted path: Groq fails -> Gemini also fails, raises LLMRouterExhaustedError.
    Two log lines (both failures).
    """
    groq_error = LLMRateLimitError("Groq rate limited")
    gemini_error = LLMRateLimitError("Gemini rate limited")

    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq:
        mock_groq.side_effect = groq_error

        with patch("app.llm.router.call_gemini", new_callable=AsyncMock) as mock_gemini:
            mock_gemini.side_effect = gemini_error

            with patch("app.llm.router.log_llm_usage") as mock_log:
                with pytest.raises(LLMRouterExhaustedError) as exc_info:
                    await route_llm_call(
                        prompt="Say hello in one sentence.",
                        request_type="planning",
                    )

                # Verify both errors are in the exception message
                assert "Both Groq and Gemini failed" in str(exc_info.value)

                # Verify two log calls per attempt (both failures), 4 attempts total -> 8 calls
                assert mock_log.call_count == 8

                first_call = mock_log.call_args_list[0]
                assert first_call.kwargs["success"] is False
                assert first_call.kwargs["provider"] == "groq"

                second_call = mock_log.call_args_list[1]
                assert second_call.kwargs["success"] is False
                assert second_call.kwargs["provider"] == "gemini"


@pytest.mark.asyncio
async def test_route_llm_call_non_rate_limit_error_propagates():
    """
    Test that non-rate-limit/non-server errors from Groq propagate immediately
    without attempting Gemini fallback.
    """
    groq_error = ValueError("Invalid API key")

    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq:
        mock_groq.side_effect = groq_error

        with patch("app.llm.router.call_gemini", new_callable=AsyncMock) as mock_gemini:
            with patch("app.llm.router.log_llm_usage"):
                with pytest.raises(ValueError, match="Invalid API key"):
                    await route_llm_call(
                        prompt="Say hello in one sentence.",
                        request_type="planning",
                    )

                # Verify Gemini was never attempted
                mock_gemini.assert_not_called()


@pytest.mark.asyncio
async def test_route_llm_call_with_custom_models():
    """
    Test that custom model names are passed through correctly.
    """
    mock_response = LLMResponse(
        text="Response",
        provider=LLMProvider.GROQ,
        model="custom-model",
        tokens_in=5,
        tokens_out=10,
        latency_ms=100,
        rate_limited=False,
    )

    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = mock_response

        with patch("app.llm.router.log_llm_usage"):
            await route_llm_call(
                prompt="Test",
                request_type="planning",
                groq_model="custom-groq-model",
                gemini_model="custom-gemini-model",
            )

        # Verify custom model was passed to call_groq
        mock_groq.assert_called_once()
        call_kwargs = mock_groq.call_args.kwargs
        assert call_kwargs["model"] == "custom-groq-model"
