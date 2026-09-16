from dataclasses import dataclass
from enum import Enum


class LLMProvider(str, Enum):
    GROQ = "groq"
    GEMINI = "gemini"


@dataclass
class LLMResponse:
    text: str
    provider: LLMProvider
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    rate_limited: bool = False


class LLMProviderError(Exception):
    """Base class for all provider-level failures."""

    pass


class LLMRateLimitError(LLMProviderError):
    """Raised on a 429 from either provider."""

    pass


class LLMServerError(LLMProviderError):
    """Raised on a 5xx from either provider."""

    pass


class LLMRouterExhaustedError(Exception):
    """Raised when both Groq and Gemini have failed for the same request."""

    pass
