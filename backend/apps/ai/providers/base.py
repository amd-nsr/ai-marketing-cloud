"""Provider-independent AI contract.

Business logic depends only on this module. Providers translate it to a vendor SDK
and normalize the vendor's responses and errors back into these types.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class Capability(StrEnum):
    STRUCTURED_OUTPUT = "structured_output"
    IMAGE_GENERATION = "image_generation"


@dataclass(frozen=True)
class StructuredRequest(Generic[T]):
    """Ask for output conforming to ``schema`` (a Pydantic model)."""

    operation: str  # e.g. "marketing_plan.generate"; used for usage accounting
    system: str
    prompt: str
    schema: type[T]
    max_tokens: int = 16000
    #: Relative reasoning effort; providers map it to their own controls or ignore it.
    effort: str = "medium"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True)
class StructuredResult(Generic[T]):
    output: T
    provider: str
    model: str
    usage: Usage
    latency_ms: int
    request_id: str | None = None
    #: True when the vendor served the request with a fallback model.
    served_by_fallback: bool = False
    is_mock: bool = False
    raw_metadata: dict[str, object] = field(default_factory=dict)


# --- Normalized errors ------------------------------------------------------------


class AIProviderError(Exception):
    """Base class. ``retryable`` tells callers whether a later retry may succeed."""

    code = "ai_error"
    retryable = False
    user_message = "The AI service could not complete this request."

    def __init__(self, message: str = "", *, request_id: str | None = None) -> None:
        super().__init__(message or self.user_message)
        self.request_id = request_id


class ProviderNotConfigured(AIProviderError):
    code = "ai_not_configured"
    user_message = "AI generation is not configured for this environment."


class UnsupportedCapability(AIProviderError):
    code = "ai_unsupported"
    user_message = "The configured AI provider does not support this operation."


class ProviderAuthError(AIProviderError):
    code = "ai_auth_failed"
    user_message = (
        "The AI provider rejected our credentials. An administrator must fix the configuration."
    )


class ProviderBadRequest(AIProviderError):
    code = "ai_bad_request"


class ProviderRateLimited(AIProviderError):
    code = "ai_rate_limited"
    retryable = True
    user_message = "The AI service is busy. Please try again in a minute."


class ProviderTimeout(AIProviderError):
    code = "ai_timeout"
    retryable = True
    user_message = "The AI service took too long to respond. Please try again."


class ProviderUnavailable(AIProviderError):
    code = "ai_unavailable"
    retryable = True
    user_message = "The AI service is temporarily unavailable. Please try again shortly."


class ProviderRefused(AIProviderError):
    code = "ai_refused"
    user_message = (
        "The AI declined this request. Try rephrasing or adjusting your business details."
    )


class ProviderOutputInvalid(AIProviderError):
    code = "ai_invalid_output"
    retryable = True
    user_message = "The AI returned an incomplete or invalid result. Please try again."


class AIProvider(Protocol):
    name: str
    model: str
    capabilities: frozenset[Capability]
    is_mock: bool

    def generate_structured(self, request: StructuredRequest[T]) -> StructuredResult[T]: ...
