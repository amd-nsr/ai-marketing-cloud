"""Adapter selection. Real and simulation adapters are chosen explicitly, never swapped."""

from django.conf import settings

from .base import NotConfigured, SocialAdapter
from .facebook import FacebookAdapter
from .mock import MockAdapter


def real_adapter(platform: str) -> SocialAdapter:
    if platform == "facebook":
        return FacebookAdapter(
            app_id=settings.META_APP_ID,
            app_secret=settings.META_APP_SECRET,
            graph_version=settings.META_GRAPH_VERSION,
            timeout_seconds=settings.SOCIAL_HTTP_TIMEOUT_SECONDS,
        )
    if platform == "instagram":
        from .instagram import InstagramAdapter

        return InstagramAdapter(
            app_id=settings.META_APP_ID,
            app_secret=settings.META_APP_SECRET,
            graph_version=settings.META_GRAPH_VERSION,
            timeout_seconds=settings.SOCIAL_HTTP_TIMEOUT_SECONDS,
        )
    if platform == "tiktok":
        from .tiktok import TikTokAdapter

        return TikTokAdapter(
            client_key=settings.TIKTOK_CLIENT_KEY,
            client_secret=settings.TIKTOK_CLIENT_SECRET,
            timeout_seconds=settings.SOCIAL_HTTP_TIMEOUT_SECONDS,
        )
    raise NotConfigured(f"Unknown platform {platform}")


def mock_adapter(platform: str) -> SocialAdapter:
    if not settings.SOCIAL_MOCK_ENABLED:
        raise NotConfigured("Simulation accounts are disabled in this environment.")
    return MockAdapter(platform, settings.FRONTEND_URL)


def adapter_for(platform: str, *, mock: bool) -> SocialAdapter:
    return mock_adapter(platform) if mock else real_adapter(platform)
