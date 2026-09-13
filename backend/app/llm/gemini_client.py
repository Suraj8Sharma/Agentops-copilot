import os
import time

from google import genai

from .types import LLMProvider, LLMRateLimitError, LLMResponse, LLMServerError


async def call_gemini(
    prompt: str,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> LLMResponse:
    """
    Call the Gemini API asynchronously.
    
    Args:
        prompt: The prompt to send to Gemini
        model: Model name (falls back to GEMINI_MODEL_DEFAULT env var if None)
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
        model = os.environ.get("GEMINI_MODEL_DEFAULT", "gemini-3.7-flash")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    
    client = genai.Client(api_key=api_key)
    
    start_time = time.time()
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Extract response data
        text = response.text
        # Gemini may not always provide token counts in the response
        # Default to 0 if not available
        if hasattr(response, "usage_metadata"):
            tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0)
            tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0)
        else:
            tokens_in = 0
            tokens_out = 0
        
        return LLMResponse(
            text=text,
            provider=LLMProvider.GEMINI,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            rate_limited=False,
        )
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_str = str(e).lower()
        
        # Check for rate limit errors (429)
        if "429" in error_str or "rate" in error_str or "quota" in error_str:
            raise LLMRateLimitError(f"Gemini rate limited: {str(e)}") from e
        
        # Check for server errors (5xx)
        server_error_codes = ["500", "502", "503", "504", "5xx", "server", "internal"]
        if any(code in error_str for code in server_error_codes):
            raise LLMServerError(f"Gemini server error: {str(e)}") from e
        
        # Re-raise other exceptions
        raise
