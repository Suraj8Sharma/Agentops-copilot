import os
import time

from groq import APIStatusError, AsyncGroq, RateLimitError

from .types import LLMProvider, LLMRateLimitError, LLMResponse, LLMServerError


async def call_groq(
    prompt: str,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> LLMResponse:
    """
    Call the Groq API asynchronously.

    Args:
        prompt: The prompt to send to Groq
        model: Model name (falls back to GROQ_MODEL_DEFAULT env var if None)
        max_tokens: Maximum tokens in response (default: 1024)
        temperature: Sampling temperature (default: 0.3)

    Returns:
        LLMResponse with the answer and metadata

    Raises:
        LLMRateLimitError: On HTTP 429
        LLMServerError: On HTTP 5xx
        Other exceptions propagate unchanged
    """
    if model is None:
        model = os.environ.get("GROQ_MODEL_DEFAULT", "openai/gpt-oss-20b")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set")

    client = AsyncGroq(api_key=api_key)

    start_time = time.time()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency_ms = int((time.time() - start_time) * 1000)

        # Extract response data
        text = response.choices[0].message.content
        tokens_in = response.usage.prompt_tokens
        tokens_out = response.usage.completion_tokens

        return LLMResponse(
            text=text,
            provider=LLMProvider.GROQ,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            rate_limited=False,
        )
    except RateLimitError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        raise LLMRateLimitError(f"Groq rate limited: {str(e)}") from e
    except APIStatusError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        if 500 <= e.status_code < 600:
            raise LLMServerError(f"Groq server error (HTTP {e.status_code}): {str(e)}") from e
        raise
