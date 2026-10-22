"""Effective usage limits per organization: settings defaults plus per-org overrides."""

from dataclasses import dataclass
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class Limits:
    ai_requests_per_month: int
    ai_cost_per_month_usd: float
    storage_bytes: int
    publishes_per_day: int


def get_limits(organization: Any) -> Limits:
    defaults: dict[str, Any] = settings.USAGE_DEFAULT_LIMITS
    overrides: dict[str, Any] = {}
    quota = getattr(organization, "usage_quota", None)
    if quota is not None:
        overrides = {k: v for k, v in quota.overrides().items() if v is not None}
    merged = {**defaults, **overrides}
    return Limits(
        ai_requests_per_month=int(merged["ai_requests_per_month"]),
        ai_cost_per_month_usd=float(merged["ai_cost_per_month_usd"]),
        storage_bytes=int(merged["storage_bytes"]),
        publishes_per_day=int(merged["publishes_per_day"]),
    )
