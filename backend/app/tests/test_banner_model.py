from unittest.mock import AsyncMock, patch

import pytest

from app.llm.types import (  # noqa: E402
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
)
from app.notifications.banner_model import (  # noqa: E402
    BANNER_COPY_RULES,
    BANNER_MAX_CHARS,
    build_banner_user_prompt,
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

    with (
        patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq,
        patch("app.llm.router.log_llm_usage"),
    ):
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

    with (
        patch("app.llm.router.call_groq", new_callable=AsyncMock) as mock_groq,
        patch("app.llm.router.log_llm_usage"),
    ):
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
    Verify that banner generation fails safely when the LLM route fails.

    The specification permits returning no banner line or a minimal
    non-LLM fallback. The current implementation returns None.
    """
    with patch(
        "app.llm.router.call_groq",
        new_callable=AsyncMock,
    ) as mock_groq:
        mock_groq.side_effect = Exception("Total failure")

        event = {"type": "oauth_expiring"}
        banner = await generate_banner(event)

        assert banner is None


def test_copy_rules_cover_each_contract_type_and_are_distinguishable():
    assert set(BANNER_COPY_RULES) == {
        "approval_needed",
        "task_completed",
        "digest_ready",
        "oauth_expiring",
    }
    examples = {rule["example_output"] for rule in BANNER_COPY_RULES.values()}
    assert len(examples) == 4
    assert all(
        rule["max_length"] <= BANNER_MAX_CHARS for rule in BANNER_COPY_RULES.values()
    )


def test_prompt_includes_type_specific_rules_and_approval_guardrail():
    approval_prompt = build_banner_user_prompt(
        {"type": "approval_needed", "title": "Review", "body": "Send email"}
    )
    oauth_prompt = build_banner_user_prompt(
        {"type": "oauth_expiring", "title": "Reconnect", "body": "Google"}
    )

    assert "recommend approve or reject" in approval_prompt
    assert "provider" in oauth_prompt.lower()
    assert "Maximum length: 80 characters" in approval_prompt
