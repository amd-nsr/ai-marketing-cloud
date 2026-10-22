"""Selects the configured provider. Switching providers is configuration, not code."""

from functools import lru_cache

from django.conf import settings

from .base import AIProvider, ProviderNotConfigured


@lru_cache(maxsize=1)
def get_provider() -> AIProvider:
    name = settings.AI_PROVIDER
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            model=settings.AI_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            timeout_seconds=settings.AI_TIMEOUT_SECONDS,
            max_retries=settings.AI_MAX_RETRIES,
            use_fallbacks=settings.AI_USE_REFUSAL_FALLBACK,
        )
    if name == "mock":
        from .mock import MockProvider

        return MockProvider()
    raise ProviderNotConfigured(f"Unknown AI_PROVIDER '{name}'.")


def reset_provider_cache() -> None:
    get_provider.cache_clear()
