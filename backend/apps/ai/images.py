"""Image generation: a capability separate from structured text generation.

The text provider (Anthropic) does not generate images, so image generation has its own
provider setting (``IMAGE_PROVIDER``). When it is ``none`` the capability is reported as
unavailable (not as a failure) and the design studio still works with uploads,
templates, and the brand kit. Adding a real vendor means implementing ``ImageProvider``
and registering it in ``get_image_provider``; see docs/decisions/0015.
"""

import io
import time
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any, Protocol

from django.conf import settings
from PIL import Image, ImageDraw

from apps.organizations.models import Organization

from .models import AIUsageRecord, AIWorkflowRun
from .providers.base import AIProviderError, ProviderNotConfigured, UnsupportedCapability


class ImageGenerationUnavailable(UnsupportedCapability):
    code = "image_generation_unavailable"
    user_message = (
        "Image generation isn't set up for this workspace. You can still upload images, "
        "use the brand kit, and start from templates."
    )


@dataclass(frozen=True)
class ImageRequest:
    operation: str
    prompt: str
    width: int
    height: int


@dataclass(frozen=True)
class ImageResult:
    content: bytes
    content_type: str
    provider: str
    model: str
    latency_ms: int
    is_mock: bool = False
    revised_prompt: str = ""


class ImageProvider(Protocol):
    name: str
    model: str
    is_mock: bool

    def generate_image(self, request: ImageRequest) -> ImageResult: ...


class MockImageProvider:
    """Deterministic, clearly labelled placeholder images for development and tests."""

    name = "mock"
    model = "mock-image-1"
    is_mock = True

    def generate_image(self, request: ImageRequest) -> ImageResult:
        start = time.monotonic()
        seed = sum(request.prompt.encode()) % 360
        img = Image.new("RGB", (request.width, request.height))
        draw = ImageDraw.Draw(img)
        for y in range(request.height):
            t = y / max(request.height - 1, 1)
            draw.line(
                [(0, y), (request.width, y)],
                fill=(int(60 + 120 * t), int(80 + (seed % 120)), int(200 - 100 * t)),
            )
        label = f"[Mock image] {request.prompt[:60]}"
        draw.rectangle([(0, 0), (request.width, 48)], fill=(0, 0, 0))
        draw.text((16, 16), label, fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return ImageResult(
            content=buf.getvalue(),
            content_type="image/png",
            provider=self.name,
            model=self.model,
            latency_ms=int((time.monotonic() - start) * 1000),
            is_mock=True,
        )


@lru_cache(maxsize=1)
def get_image_provider() -> ImageProvider | None:
    name = settings.IMAGE_PROVIDER
    if name in {"", "none"}:
        return None
    if name == "mock":
        return MockImageProvider()
    raise ProviderNotConfigured(f"Unknown IMAGE_PROVIDER '{name}'.")


def reset_image_provider_cache() -> None:
    get_image_provider.cache_clear()


def image_generation_status() -> dict[str, Any]:
    try:
        provider = get_image_provider()
    except AIProviderError:
        provider = None
    return {
        "available": provider is not None,
        "provider": provider.name if provider else None,
        "is_mock": bool(provider and provider.is_mock),
    }


def generate_image(
    org: Organization, request: ImageRequest, *, user: Any = None, run: AIWorkflowRun | None = None
) -> ImageResult:
    """Generate one image, enforcing the AI quota and recording usage like text calls."""
    from .service import check_ai_quota

    check_ai_quota(org)
    provider = get_image_provider()
    if provider is None:
        raise ImageGenerationUnavailable()
    try:
        result = provider.generate_image(request)
    except AIProviderError as exc:
        _record(
            org, provider.name, provider.model, request, user, run, error=exc, mock=provider.is_mock
        )
        raise
    _record(org, result.provider, result.model, request, user, run, result=result)
    return result


def _record(
    org: Organization,
    provider: str,
    model: str,
    request: ImageRequest,
    user: Any,
    run: AIWorkflowRun | None,
    *,
    result: ImageResult | None = None,
    error: AIProviderError | None = None,
    mock: bool = False,
) -> None:
    AIUsageRecord.objects.create(
        organization=org,
        provider=provider,
        model=model,
        operation=request.operation,
        workflow_run=run,
        user=user if getattr(user, "is_authenticated", False) else None,
        estimated_cost=(
            Decimal(str(settings.IMAGE_COST_PER_IMAGE_USD))
            if result and not result.is_mock
            else Decimal(0)
        ),
        success=result is not None,
        error_code=error.code if error else "",
        latency_ms=result.latency_ms if result else 0,
        is_mock=result.is_mock if result else mock,
    )
