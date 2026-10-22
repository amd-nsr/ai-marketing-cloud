"""The single entry point business code uses to call AI.

Centralizes provider selection, quota enforcement, error normalization, a bounded
retry for invalid output, and usage/cost recording.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.core.errors import QuotaExceeded
from apps.organizations.models import Organization
from apps.usage.limits import get_limits

from .models import AIUsageRecord, AIWorkflowRun
from .pricing import estimate_cost
from .providers.base import (
    AIProviderError,
    Capability,
    ProviderOutputInvalid,
    StructuredRequest,
    StructuredResult,
    T,
    UnsupportedCapability,
)
from .providers.registry import get_provider

logger = logging.getLogger(__name__)

#: Invalid/truncated output is retried once; transport-level retries happen in the SDK.
OUTPUT_RETRIES = 1


def month_start(now: datetime | None = None) -> datetime:
    now = now or timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def monthly_ai_usage(org: Organization) -> dict[str, Any]:
    agg = AIUsageRecord.objects.filter(organization=org, created_at__gte=month_start()).aggregate(
        requests=Count("id"), cost=Sum("estimated_cost")
    )
    return {"requests": agg["requests"] or 0, "estimated_cost": agg["cost"] or Decimal(0)}


def monthly_ai_usage_by_operation(org: Organization) -> list[dict[str, Any]]:
    rows = (
        AIUsageRecord.objects.filter(organization=org, created_at__gte=month_start())
        .values("operation")
        .annotate(
            requests=Count("id"),
            failed=Count("id", filter=Q(success=False)),
            estimated_cost_usd=Sum("estimated_cost"),
        )
        .order_by("-estimated_cost_usd", "operation")
    )
    return [{**r, "estimated_cost_usd": r["estimated_cost_usd"] or Decimal(0)} for r in rows]


def check_ai_quota(org: Organization) -> None:
    limits = get_limits(org)
    used = monthly_ai_usage(org)
    if used["requests"] >= limits.ai_requests_per_month:
        raise QuotaExceeded(
            f"Your organization has used its {limits.ai_requests_per_month} AI requests "
            "for this month."
        )
    if used["estimated_cost"] >= Decimal(str(limits.ai_cost_per_month_usd)):
        raise QuotaExceeded("Your organization has reached its monthly AI spending limit.")


def generate_structured(
    org: Organization,
    request: StructuredRequest[T],
    *,
    user: Any = None,
    run: AIWorkflowRun | None = None,
) -> StructuredResult[T]:
    check_ai_quota(org)
    provider = get_provider()
    if Capability.STRUCTURED_OUTPUT not in provider.capabilities:
        raise UnsupportedCapability()

    attempt = 0
    while True:
        attempt += 1
        try:
            result = provider.generate_structured(request)
        except AIProviderError as exc:
            _record(
                org,
                provider.name,
                provider.model,
                request.operation,
                user,
                run,
                error=exc,
                is_mock=provider.is_mock,
            )
            if isinstance(exc, ProviderOutputInvalid) and attempt <= OUTPUT_RETRIES:
                logger.info(
                    "Retrying after invalid AI output", extra={"operation": request.operation}
                )
                continue
            raise
        _record(org, result.provider, result.model, request.operation, user, run, result=result)
        return result


def _record(
    org: Organization,
    provider: str,
    model: str,
    operation: str,
    user: Any,
    run: AIWorkflowRun | None,
    *,
    result: StructuredResult[Any] | None = None,
    error: AIProviderError | None = None,
    is_mock: bool = False,
) -> None:
    usage = result.usage if result else None
    AIUsageRecord.objects.create(
        organization=org,
        provider=provider,
        model=model,
        operation=operation,
        workflow_run=run,
        user=user if getattr(user, "is_authenticated", False) else None,
        input_tokens=usage.input_tokens if usage else 0,
        output_tokens=usage.output_tokens if usage else 0,
        cache_read_tokens=usage.cache_read_tokens if usage else 0,
        cache_write_tokens=usage.cache_write_tokens if usage else 0,
        estimated_cost=estimate_cost(model, usage) if usage else Decimal(0),
        success=result is not None,
        error_code=error.code if error else "",
        request_id=(result.request_id if result else error.request_id if error else None) or "",
        latency_ms=result.latency_ms if result else 0,
        is_mock=result.is_mock if result else is_mock,
        served_by_fallback=result.served_by_fallback if result else False,
    )
