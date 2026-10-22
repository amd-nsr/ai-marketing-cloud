"""Per-organization storage accounting across every model that stores files."""

from typing import Any

from django.db import models
from django.db.models import Sum

from apps.core.errors import QuotaExceeded

_STORAGE_MODELS: list[type[models.Model]] = []


def register_storage_model(model: type[models.Model]) -> None:
    """Register a model with ``organization`` and ``size_bytes`` fields."""
    if model not in _STORAGE_MODELS:
        _STORAGE_MODELS.append(model)


def storage_used_bytes(organization: Any) -> int:
    total = 0
    for model in _STORAGE_MODELS:
        total += (
            model._default_manager.filter(organization=organization).aggregate(s=Sum("size_bytes"))[
                "s"
            ]
            or 0
        )
    return total


def storage_limit_bytes(organization: Any) -> int:
    from .limits import get_limits

    return get_limits(organization).storage_bytes


def check_storage_quota(organization: Any, incoming_bytes: int) -> None:
    limit = storage_limit_bytes(organization)
    if storage_used_bytes(organization) + incoming_bytes > limit:
        raise QuotaExceeded(
            f"This upload would exceed your organization's storage limit "
            f"({limit // (1024 * 1024)} MB)."
        )
