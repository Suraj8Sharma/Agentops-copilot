import json
import logging

from .gemini_client import call_gemini
from .groq_client import call_groq
from .types import (
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    LLMRouterExhaustedError,
    LLMServerError,
)

_llm_logger = logging.getLogger("llm_usage")


def log_llm_usage(
    provider: str,
    model: str,
    request_type: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    rate_limit_hit: bool,
    success: bool,
) -> None:
    """
    Log LLM usage to structured local log.

    # TODO(D21): Replace this function body with a real insert into the
    # llm_usage_logs table once that table exists. Use the exact column names
    # from Section 7, Group F of the manual. Call sites in router.py should
    # not need to change on D21 — only this function's body.
    """
    _llm_logger.info(
        json.dumps(
            {
                "provider": provider,
                "model": model,
                "request_type": request_type,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "rate_limit_hit": rate_limit_hit,
                "success": success,
            }
        )
    )


async def route_llm_call(
    prompt: str,
    request_type: str,
    groq_model: str | None = None,
    gemini_model: str | None = None,
) -> LLMResponse:
    """
    Route an LLM call to Groq with automatic fallback to Gemini.

    Tries Groq first. On rate-limit (429) or server error (5xx), falls back to Gemini.
    Any other Groq exception propagates immediately without attempting Gemini.
    Every attempt (success or failure) is logged.

    Args:
        prompt: The prompt to send to the LLM
        request_type: Type of request (e.g. "planning", "routing",
            "risk_explanation", "banner", "memory_extraction")
        groq_model: Groq model name (optional, falls back to env var)
        gemini_model: Gemini model name (optional, falls back to env var)

    Returns:
        LLMResponse from whichever provider succeeded

    Raises:
        LLMRouterExhaustedError: When both Groq and Gemini fail
        Other exceptions: Propagate immediately from Groq if not rate-limit/server-error
    """
    groq_error = None

    # Step 1: Try Groq
    try:
        response = await call_groq(prompt, model=groq_model)
        log_llm_usage(
            provider=response.provider.value,
            model=response.model,
            request_type=request_type,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            latency_ms=response.latency_ms,
            rate_limit_hit=response.rate_limited,
            success=True,
        )
        return response
    except (LLMRateLimitError, LLMServerError) as e:
        # Log the failure and prepare for fallback
        groq_error = e
        log_llm_usage(
            provider=LLMProvider.GROQ.value,
            model=groq_model or "unknown",
            request_type=request_type,
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            rate_limit_hit=isinstance(e, LLMRateLimitError),
            success=False,
        )

    # Step 2: Fallback to Gemini
    try:
        response = await call_gemini(prompt, model=gemini_model)
        log_llm_usage(
            provider=response.provider.value,
            model=response.model,
            request_type=request_type,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            latency_ms=response.latency_ms,
            rate_limit_hit=response.rate_limited,
            success=True,
        )
        return response
    except (LLMRateLimitError, LLMServerError) as e:
        # Both providers failed
        log_llm_usage(
            provider=LLMProvider.GEMINI.value,
            model=gemini_model or "unknown",
            request_type=request_type,
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            rate_limit_hit=isinstance(e, LLMRateLimitError),
            success=False,
        )

        # Raise exhausted error with both underlying errors
        error_msg = f"Both Groq and Gemini failed. Groq: {str(groq_error)}. Gemini: {str(e)}"
        raise LLMRouterExhaustedError(error_msg) from e
