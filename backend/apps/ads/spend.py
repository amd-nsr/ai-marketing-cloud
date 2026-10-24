"""Spend figures the policy engine uses. Deterministic; read from our synced data."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .models import AdAccount, AdCampaign, AdInsight


def _accounts(org: Any, currency: str) -> Any:
    return AdAccount.objects.filter(
        organization=org, currency=currency, status=AdAccount.Status.CONNECTED
    )


def active_daily_total(org: Any, currency: str, *, exclude: AdCampaign | None = None) -> Decimal:
    """Sum of daily budgets of campaigns currently set to ACTIVE on Meta."""
    qs = AdCampaign.objects.filter(
        organization=org,
        ad_account__in=_accounts(org, currency),
        state=AdCampaign.State.CREATED,
        configured_status="ACTIVE",
    )
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.aggregate(total=Sum("daily_budget"))["total"] or Decimal(0)


def month_spend(org: Any, currency: str) -> Decimal:
    """Spend this calendar month (UTC) across the organization's ad accounts."""
    first = timezone.now().date().replace(day=1)
    total = AdInsight.objects.filter(
        organization=org,
        currency=currency,
        date__gte=first,
        ad_account__in=_accounts(org, currency),
    ).aggregate(total=Sum("spend"))["total"]
    return total or Decimal(0)


def spend_data_is_fresh(org: Any, currency: str) -> bool:
    """Limits are only trusted when every account's spend was synced recently."""
    accounts = _accounts(org, currency)
    if not accounts.exists():
        return False
    cutoff = timezone.now() - timedelta(hours=settings.ADS_SPEND_DATA_MAX_AGE_HOURS)
    return (
        not accounts.filter(last_synced_at__isnull=True).exists()
        and not accounts.filter(last_synced_at__lt=cutoff).exists()
    )
