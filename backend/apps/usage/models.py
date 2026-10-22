from typing import Any

from django.db import models

from apps.core.models import TimeStampedModel


class OrganizationQuota(TimeStampedModel):
    """Per-organization overrides of the default usage limits (blank = use default)."""

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.CASCADE, related_name="usage_quota"
    )
    ai_requests_per_month = models.PositiveIntegerField(null=True, blank=True)
    ai_cost_per_month_usd = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    storage_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    publishes_per_day = models.PositiveIntegerField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    def overrides(self) -> dict[str, Any]:
        return {
            "ai_requests_per_month": self.ai_requests_per_month,
            "ai_cost_per_month_usd": self.ai_cost_per_month_usd,
            "storage_bytes": self.storage_bytes,
            "publishes_per_day": self.publishes_per_day,
        }
