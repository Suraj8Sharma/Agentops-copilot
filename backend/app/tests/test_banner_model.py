from unittest.mock import AsyncMock, patch

import pytest

from app.llm.types import (
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
)
from app.notifications.banner_model import (
    BANNER_MAX_CHARS,
    generate_banner,
)


@pytest.mark.asyncio
async def test_banner_model_matches_triggering_event_type():
    """
    Test that the banner model returns the correct banner and handles
    unknown event types properly.
    """
    mock_response = LLMResponse(
        text="Your agent wants to send an email - tap to review.",
        provider=LLMProvider.GROQ,
        model="llama-3.1-8b-instant",
        tokens_in=50,
        tokens_out=12,
        latency_ms=100,
        rate_limited=False,
    )

    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq, \
         patch("app.llm.router.log_llm_usage"):
        mock_groq.return_value = mock_response

        # Test valid type
        event = {
            "type": "approval_needed",
            "tool_name": "gmail_send",
            "title": "Email",
            "body": "Send email to bob",
        }
        
        banner = await generate_banner(event)
        assert banner == "Your agent wants to send an email - tap to review."

        # Test unknown type
        bad_event = {"type": "unknown_type"}
        bad_banner = await generate_banner(bad_event)
        assert bad_banner is None


@pytest.mark.asyncio
async def test_banner_model_output_length_under_limit():
    """
    Test that the banner model truncates output that is too long.
    """
    long_text = "A" * 100
    mock_response = LLMResponse(
        text=long_text,
        provider=LLMProvider.GROQ,
        model="llama-3.1-8b-instant",
        tokens_in=50,
        tokens_out=30,
        latency_ms=100,
        rate_limited=False,
    )

    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq, \
         patch("app.llm.router.log_llm_usage"):
        mock_groq.return_value = mock_response

        event = {"type": "task_completed"}
        banner = await generate_banner(event)
        
        assert banner is not None
        assert len(banner) <= BANNER_MAX_CHARS
        assert banner.endswith("...")


@pytest.mark.asyncio
async def test_banner_model_groq_fallback_to_gemini():
    """
    Test that a forced Groq failure falls back to Gemini.
    """
    groq_error = LLMRateLimitError("Groq rate limit")
    
    mock_gemini_response = LLMResponse(
        text="Fallback gemini banner.",
        provider=LLMProvider.GEMINI,
        model="gemini-1.5-flash",
        tokens_in=50,
        tokens_out=10,
        latency_ms=200,
        rate_limited=False,
    )

    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq:
        mock_groq.side_effect = groq_error
        
        with patch("app.llm.router.call_gemini", new_callable=AsyncMock) as mock_gemini:
            mock_gemini.return_value = mock_gemini_response
            
            with patch("app.llm.router.log_llm_usage") as mock_log:
                event = {"type": "digest_ready", "digest_period": "daily"}
                banner = await generate_banner(event)
                
                assert banner == "Fallback gemini banner."
                mock_groq.assert_called_once()
                mock_gemini.assert_called_once()
                
                # Check that logging was called with request_type="banner"
                # Once for the failed Groq call, once for the successful Gemini call
                assert mock_log.call_count == 2
                assert mock_log.call_args_list[0].kwargs["request_type"] == "banner"
                assert mock_log.call_args_list[1].kwargs["request_type"] == "banner"


@pytest.mark.asyncio
async def test_banner_model_all_fail():
    """
    Test that when all providers fail, the function returns None.

    The module must fail safely by returning no banner line or a minimal
    non-LLM fallback.
    """
    with patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq:
        mock_groq.side_effect = Exception("Total failure")
        
        event = {"type": "oauth_expiring"}
        banner = await generate_banner(event)
        
        assert banner is None
