import asyncio
import json
import logging

from app.core.config import settings

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

# Free-tier aware routing defaults. We intentionally keep a large gap between
# retries because Groq/Gemini developer tiers can silently reject bursts with 429
# even when the app is otherwise healthy.
_FREE_TIER_BASE_DELAY = max(float(getattr(settings, "LLM_FREE_TIER_BASE_DELAY_SECONDS", 5.0)), 2.0)
_FREE_TIER_MAX_RETRIES = max(int(getattr(settings, "LLM_FREE_TIER_MAX_RETRIES", 2)), 1)


async def _backoff_delay_for_attempt(attempt: int, *, is_free_tier: bool = True) -> float:
    """Return a conservative backoff delay in seconds for a failed provider round."""
    if not is_free_tier:
        return 0.0
    # 5s, 10s, 20s ... capped to avoid hammering the free-tier quota.
    return min(_FREE_TIER_BASE_DELAY * (2**attempt), 30.0)


async def _call_with_provider_retry(
    provider_name: str,
    call_fn,
    prompt: str,
    model: str | None,
    request_type: str,
) -> LLMResponse:
    """Call a provider once, and only retry that single provider after a free-tier delay."""
    try:
        return await call_fn(prompt, model=model)
    except (LLMRateLimitError, LLMServerError) as exc:
        log_llm_usage(
            provider=provider_name,
            model=model or "unknown",
            request_type=request_type,
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            rate_limit_hit=isinstance(exc, LLMRateLimitError),
            success=False,
        )
        if isinstance(exc, LLMRateLimitError):
            await asyncio.sleep(_FREE_TIER_BASE_DELAY)
        raise


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
    groq_error = None
    gemini_error = None

    for attempt in range(_FREE_TIER_MAX_RETRIES + 1):
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

        if attempt < _FREE_TIER_MAX_RETRIES:
            delay = await _backoff_delay_for_attempt(attempt, is_free_tier=True)
            _llm_logger.warning(
                "Both Groq and Gemini failed on attempt %s/%s; "
                "free-tier backoff for %.1fs before retry.",
                attempt + 1,
                _FREE_TIER_MAX_RETRIES + 1,
                delay,
            )
            await asyncio.sleep(delay)
        else:
            error_msg = (
                f"Both Groq and Gemini failed after {_FREE_TIER_MAX_RETRIES + 1} attempts. "
                f"Groq: {str(groq_error)}. Gemini: {str(gemini_error)}"
            )
            raise LLMRouterExhaustedError(error_msg) from gemini_error
