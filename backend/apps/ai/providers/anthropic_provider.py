"""Anthropic (Claude) provider."""

import logging
import time
from typing import cast

import anthropic
from anthropic.types.beta import BetaOutputConfigParam
from pydantic import ValidationError

from .base import (
    AIProviderError,
    Capability,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderNotConfigured,
    ProviderOutputInvalid,
    ProviderRateLimited,
    ProviderRefused,
    ProviderTimeout,
    ProviderUnavailable,
    StructuredRequest,
    StructuredResult,
    T,
    Usage,
)

logger = logging.getLogger(__name__)

# Server-side refusal fallback: a declined request is re-run on Anthropic's recommended
# model for that refusal category within the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


class AnthropicProvider:
    name = "anthropic"
    capabilities = frozenset({Capability.STRUCTURED_OUTPUT})
    is_mock = False

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
        max_retries: int,
        use_fallbacks: bool = True,
    ) -> None:
        if not api_key:
            raise ProviderNotConfigured("ANTHROPIC_API_KEY is not set.")
        self.model = model
        self.use_fallbacks = use_fallbacks
        # The SDK retries 408/409/429/5xx and connection errors with backoff.
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )

    def generate_structured(self, request: StructuredRequest[T]) -> StructuredResult[T]:
        started = time.monotonic()
        output_config = cast(
            BetaOutputConfigParam,
            {"effort": request.effort if request.effort in _EFFORTS else "medium"},
        )
        extra: dict[str, object] = {}
        if self.use_fallbacks:
            extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        try:
            response = self._client.beta.messages.parse(
                model=self.model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.prompt}],
                output_format=request.schema,
                output_config=output_config,
                **extra,  # type: ignore[arg-type]
            )
        except anthropic.APIError as exc:
            raise _normalize(exc) from exc
        except ValidationError as exc:
            raise ProviderOutputInvalid(
                f"Output failed schema validation: {exc.error_count()} errors"
            ) from exc

        request_id = getattr(response, "_request_id", None)
        if response.stop_reason == "refusal":
            category = getattr(getattr(response, "stop_details", None), "category", None)
            raise ProviderRefused(f"Refused (category={category})", request_id=request_id)
        if response.stop_reason == "max_tokens":
            raise ProviderOutputInvalid(
                "Output was truncated at max_tokens.", request_id=request_id
            )
        parsed = response.parsed_output
        if parsed is None:
            raise ProviderOutputInvalid("No structured output returned.", request_id=request_id)

        usage = response.usage
        iterations = getattr(usage, "iterations", None) or []
        return StructuredResult(
            output=parsed,
            provider=self.name,
            model=response.model,
            usage=Usage(
                input_tokens=usage.input_tokens or 0,
                output_tokens=usage.output_tokens or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", None) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None) or 0,
            ),
            latency_ms=int((time.monotonic() - started) * 1000),
            request_id=request_id,
            served_by_fallback=any(
                getattr(i, "type", "") == "fallback_message" for i in iterations
            ),
        )


def _normalize(exc: anthropic.APIError) -> AIProviderError:
    response = getattr(exc, "response", None)
    request_id = response.headers.get("request-id") if response is not None else None
    # Most specific first.
    if isinstance(exc, anthropic.APITimeoutError):
        return ProviderTimeout(str(exc), request_id=request_id)
    if isinstance(exc, anthropic.APIConnectionError):
        return ProviderUnavailable(str(exc), request_id=request_id)
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return ProviderAuthError(str(exc), request_id=request_id)
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderRateLimited(str(exc), request_id=request_id)
    if isinstance(exc, (anthropic.BadRequestError, anthropic.NotFoundError)):
        return ProviderBadRequest(str(exc), request_id=request_id)
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return ProviderUnavailable(str(exc), request_id=request_id)
    logger.warning("Unclassified Anthropic error", extra={"error_type": type(exc).__name__})
    return AIProviderError(str(exc), request_id=request_id)
