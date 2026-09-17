import asyncio
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
    Log LLM usage to structured local log and the remote Supabase database (D21).
    """
    from app.db.supabase_client import supabase_admin

    payload = {
        "provider": provider,
        "model": model,
        "request_type": request_type,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "rate_limit_hit": rate_limit_hit,
    }

    _llm_logger.info(json.dumps({**payload, "success": success}))

    try:
        supabase_admin.table("llm_usage_logs").insert(payload).execute()
    except Exception:
        _llm_logger.error("Failed to write to llm_usage_logs in Supabase", exc_info=True)


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

    Includes an exponential backoff retry loop (up to 3 retries) if both
    providers fail due to rate limits or server errors.

    Args:
        prompt: The prompt to send to the LLM
        request_type: Type of request (e.g. "planning", "routing",
            "risk_explanation", "banner", "memory_extraction")
        groq_model: Groq model name (optional, falls back to env var)
        gemini_model: Gemini model name (optional, falls back to env var)

    Returns:
        LLMResponse from whichever provider succeeded

    Raises:
        LLMRouterExhaustedError: When both Groq and Gemini fail after retries
        Other exceptions: Propagate immediately from Groq if not rate-limit/server-error
    """
    max_retries = 3
    base_delay = 1.0
    groq_error = None
    gemini_error = None

    for attempt in range(max_retries + 1):
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
            gemini_error = e
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

        # If we reach here, both failed. Apply exponential backoff and retry, or raise if exhausted
        if attempt < max_retries:
            delay = base_delay * (2**attempt)
            _llm_logger.warning(
                f"Both Groq and Gemini failed (attempt {attempt + 1}/{max_retries + 1}). "
                f"Retrying in {delay} seconds..."
            )
            await asyncio.sleep(delay)
        else:
            # Raise exhausted error with both underlying errors
            error_msg = (
                f"Both Groq and Gemini failed after {max_retries + 1} attempts. "
                f"Groq: {str(groq_error)}. Gemini: {str(gemini_error)}"
            )
            raise LLMRouterExhaustedError(error_msg) from gemini_error
