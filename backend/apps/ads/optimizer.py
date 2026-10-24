"""Deterministic ad recommendations, proposed as automation actions.

Nothing here writes to Meta: each proposal is an AutomationAction that the policy engine
evaluates (and that a person approves unless the advertising policy allows it).

Rules (evidence is stored in the action payload):
- spend guard: monthly spend reached the limit and auto-pause is on → pause running
  campaigns;
- no clicks: active ≥ 3 days, spent ≥ 3x the minimum daily budget in the last 3 days, and
  zero clicks → pause;
- budget-limited winner: active ≥ 7 days, spending ≥ 90% of its daily budget, CTR ≥ 1.5x
  and CPC ≤ the account's 7-day average → raise the budget by the allowed percentage
  (at most 20%), never above the per-campaign limit.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Sum
from django.utils import timezone

from apps.automation.models import AutomationPolicy
from apps.automation.policy import ADS_BUDGET_CHANGE, ADS_PAUSE, get_policy
from apps.automation.services import propose_ad_action

from . import spend
from .models import AdCampaign, AdInsight
from .validation import MIN_DAILY_BUDGET


def _window(campaign: AdCampaign, days: int) -> dict[str, Any]:
    since = timezone.now().date() - timedelta(days=days - 1)
    agg = AdInsight.objects.filter(campaign=campaign, date__gte=since).aggregate(
        spend=Sum("spend"), clicks=Sum("clicks"), impressions=Sum("impressions")
    )
    return {k: v or 0 for k, v in agg.items()}


def run_for_org(org: Any) -> int:
    policy: AutomationPolicy = get_policy(org)
    if not policy.ads_automation_enabled or policy.mode == "manual":
        return 0
    currency = policy.ads_limit_currency
    live = AdCampaign.objects.filter(
        organization=org,
        state=AdCampaign.State.CREATED,
        configured_status="ACTIVE",
        ad_account__status="connected",
    )
    proposed = 0
    now = timezone.now()

    if (
        currency
        and policy.ads_monthly_spend_limit
        and policy.ads_auto_pause_on_spend_limit
        and spend.month_spend(org, currency) >= policy.ads_monthly_spend_limit
    ):
        for campaign in live.filter(ad_account__currency=currency):
            propose_ad_action(
                org,
                campaign=campaign,
                action_type=ADS_PAUSE,
                initiated_by="automation",
                workflow="ads_spend_guard",
                payload={"evidence": "Monthly spend limit reached."},
            )
            proposed += 1
        return proposed

    for campaign in live:
        if not campaign.activated_at:
            continue
        age = now - campaign.activated_at
        last3 = _window(campaign, 3)
        if (
            age >= timedelta(days=3)
            and Decimal(last3["spend"]) >= MIN_DAILY_BUDGET * 3
            and last3["clicks"] == 0
        ):
            propose_ad_action(
                org,
                campaign=campaign,
                action_type=ADS_PAUSE,
                initiated_by="automation",
                workflow="ads_optimizer",
                payload={"evidence": f"Spent {last3['spend']} in 3 days with no clicks."},
            )
            proposed += 1
            continue
        if age < timedelta(days=7) or not campaign.daily_budget:
            continue
        mine = _window(campaign, 7)
        acct = AdInsight.objects.filter(
            ad_account=campaign.ad_account, date__gte=now.date() - timedelta(days=6)
        ).aggregate(spend=Sum("spend"), clicks=Sum("clicks"), impressions=Sum("impressions"))
        if not (mine["impressions"] and mine["clicks"] and acct["impressions"] and acct["clicks"]):
            continue
        ctr = Decimal(mine["clicks"]) / mine["impressions"]
        avg_ctr = Decimal(acct["clicks"]) / acct["impressions"]
        cpc = Decimal(mine["spend"]) / mine["clicks"]
        avg_cpc = Decimal(acct["spend"] or 0) / acct["clicks"]
        budget_limited = Decimal(mine["spend"]) >= campaign.daily_budget * 7 * Decimal("0.9")
        if budget_limited and ctr >= avg_ctr * Decimal("1.5") and cpc <= avg_cpc:
            pct = Decimal(min(policy.ads_max_budget_increase_percent, 20))
            new = (campaign.daily_budget * (1 + pct / 100)).quantize(Decimal("0.01"))
            if policy.ads_max_daily_budget_per_campaign:
                new = min(new, policy.ads_max_daily_budget_per_campaign)
            if new > campaign.daily_budget:
                propose_ad_action(
                    org,
                    campaign=campaign,
                    action_type=ADS_BUDGET_CHANGE,
                    initiated_by="automation",
                    workflow="ads_optimizer",
                    payload={
                        "daily_budget": str(new),
                        "evidence": (
                            f"Spending its full budget with CTR {ctr:.2%} vs {avg_ctr:.2%} "
                            f"average and CPC {cpc:.2f} vs {avg_cpc:.2f}."
                        ),
                    },
                )
                proposed += 1
    return proposed


def run_for_all() -> dict[str, int]:
    from apps.organizations.models import Organization

    orgs = Organization.objects.filter(
        pk__in=AutomationPolicy.objects.filter(ads_automation_enabled=True).values(
            "organization_id"
        )
    )
    return {str(org.pk): run_for_org(org) for org in orgs}
