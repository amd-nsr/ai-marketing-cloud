from decimal import Decimal

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from apps.organizations.api import OrganizationScopedMixin
from apps.organizations.roles import Perm

from .limits import get_limits
from .storage import storage_used_bytes

_summary = inline_serializer(
    "UsageSummary",
    {
        "period_start": serializers.DateTimeField(),
        "ai_requests": serializers.IntegerField(),
        "ai_requests_limit": serializers.IntegerField(),
        "ai_estimated_cost_usd": serializers.DecimalField(max_digits=12, decimal_places=6),
        "ai_cost_limit_usd": serializers.FloatField(),
        "storage_bytes": serializers.IntegerField(),
        "storage_limit_bytes": serializers.IntegerField(),
        "publishes_last_24h": serializers.IntegerField(),
        "publishes_per_day_limit": serializers.IntegerField(),
        "ai_by_workflow": serializers.ListField(
            child=inline_serializer(
                "UsageByWorkflow",
                {
                    "operation": serializers.CharField(),
                    "requests": serializers.IntegerField(),
                    "failed": serializers.IntegerField(),
                    "estimated_cost_usd": serializers.DecimalField(max_digits=12, decimal_places=6),
                },
            )
        ),
        "cost_is_estimate": serializers.BooleanField(),
    },
)


def _money(value: Decimal) -> str:
    # Decimal amounts are strings in the API contract (no float rounding).
    return f"{value:.6f}"


class UsageSummaryView(OrganizationScopedMixin):
    read_permission = Perm.USAGE_VIEW

    @extend_schema(responses=_summary)
    def get(self, request: Request, org_id: str) -> Response:
        from apps.ai.service import month_start, monthly_ai_usage, monthly_ai_usage_by_operation
        from apps.publishing.services import publishes_last_24h

        limits = get_limits(self.organization)
        ai = monthly_ai_usage(self.organization)
        by_workflow = [
            {**row, "estimated_cost_usd": _money(row["estimated_cost_usd"])}
            for row in monthly_ai_usage_by_operation(self.organization)
        ]
        return Response(
            {
                "period_start": month_start(),
                "ai_requests": ai["requests"],
                "ai_requests_limit": limits.ai_requests_per_month,
                "ai_estimated_cost_usd": _money(ai["estimated_cost"]),
                "ai_cost_limit_usd": limits.ai_cost_per_month_usd,
                "storage_bytes": storage_used_bytes(self.organization),
                "storage_limit_bytes": limits.storage_bytes,
                "publishes_last_24h": publishes_last_24h(self.organization),
                "publishes_per_day_limit": limits.publishes_per_day,
                "ai_by_workflow": by_workflow,
                "cost_is_estimate": True,
            }
        )
