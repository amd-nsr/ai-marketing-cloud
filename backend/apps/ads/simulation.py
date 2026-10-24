"""Simulated advertising platform: no network calls, no money.

Used for simulation ad accounts (labelled everywhere) and automated tests. Objects get
``sim_`` ids; reads mirror what was created here; insights are synthesized only for days
a campaign was active (spend ≈ 85% of its daily budget) and flagged as simulation.

Failure steering through the campaign name, for tests and demos:
- ``[sim:fail-adset]``   → the ad set step is rejected (partial failure);
- ``[sim:lost-campaign]`` → the campaign is created but the response is lost.
"""

import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.social.adapters.base import ContentRejected, UncertainOutcome

from .platform import (
    AccountContext,
    CampaignSpec,
    RemoteAd,
    RemoteAdSet,
    RemoteCampaign,
    RemoteInsight,
)

#: Objects created in this process: account → level → {name: id}. Lets find_by_name work.
_CREATED: dict[str, dict[str, dict[str, str]]] = {}
#: Names whose simulated "lost response" already happened (it happens once per name).
_LOST: set[str] = set()


def _new_id(prefix: str) -> str:
    return f"sim_{prefix}_{secrets.token_hex(4)}"


class SimulatedAdsPlatform:
    is_mock = True

    def _campaigns(self, account: AccountContext):  # type: ignore[no-untyped-def]
        from .models import AdCampaign

        return AdCampaign.objects.filter(
            ad_account__external_id=account.external_id,
            ad_account__is_mock=True,
            external_id__isnull=False,
        )

    def list_campaigns(self, account: AccountContext) -> list[RemoteCampaign]:
        return [
            RemoteCampaign(
                id=c.external_id or "",
                name=c.name,
                objective=c.objective,
                configured_status=c.configured_status or "PAUSED",
                effective_status=c.configured_status or "PAUSED",
                daily_budget=c.daily_budget,
                lifetime_budget=None,
                special_ad_categories=list(c.special_ad_categories),
            )
            for c in self._campaigns(account)
        ]

    def list_ad_sets(self, account: AccountContext) -> list[RemoteAdSet]:
        out = []
        for c in self._campaigns(account):
            if adset := c.progress.get("adset_id"):
                status = c.configured_status or "PAUSED"
                out.append(
                    RemoteAdSet(
                        id=adset,
                        campaign_id=c.external_id or "",
                        name=f"{c.name} · ad set",
                        configured_status=status,
                        effective_status=status,
                        daily_budget=None,
                        optimization_goal="LINK_CLICKS",
                        billing_event="IMPRESSIONS",
                        targeting=(c.spec or {}).get("targeting", {}),
                        start_time=None,
                        end_time=None,
                    )
                )
        return out

    def list_ads(self, account: AccountContext) -> list[RemoteAd]:
        out = []
        for c in self._campaigns(account):
            if (ad := c.progress.get("ad_id")) and (adset := c.progress.get("adset_id")):
                status = c.configured_status or "PAUSED"
                out.append(
                    RemoteAd(
                        id=ad,
                        adset_id=adset,
                        name=f"{c.name} · ad",
                        configured_status=status,
                        effective_status=status,
                        creative_id=c.progress.get("creative_id", ""),
                    )
                )
        return out

    def insights(self, account: AccountContext, *, since: date, until: date) -> list[RemoteInsight]:
        rows = []
        today = timezone.now().date()
        for c in self._campaigns(account):
            if not c.activated_at or not c.daily_budget:
                continue
            start = max(since, c.activated_at.date())
            stop_at = c.paused_at.date() if c.paused_at and not c.is_live else today
            end = min(until, stop_at)
            day = start
            while day <= end:
                spend = (c.daily_budget * Decimal("0.85")).quantize(Decimal("0.01"))
                impressions = int(spend * 120)
                clicks = max(1, int(impressions * 0.012))
                rows.append(
                    RemoteInsight(
                        campaign_id=c.external_id or "",
                        date=day,
                        spend=spend,
                        impressions=impressions,
                        reach=int(impressions * 0.7),
                        clicks=clicks,
                        link_clicks=int(clicks * 0.8),
                        ctr=(Decimal(clicks) * 100 / impressions).quantize(Decimal("0.0001")),
                        cpc=(spend / clicks).quantize(Decimal("0.0001")),
                        cpm=(spend * 1000 / impressions).quantize(Decimal("0.0001")),
                    )
                )
                day += timedelta(days=1)
        return rows

    def _remember(self, account: AccountContext, level: str, name: str, object_id: str) -> str:
        _CREATED.setdefault(account.external_id, {}).setdefault(level, {})[name] = object_id
        return object_id

    def create_campaign(self, account: AccountContext, spec: CampaignSpec, name: str) -> str:
        object_id = self._remember(account, "campaign", name, _new_id("campaign"))
        if "[sim:lost-campaign]" in name and name not in _LOST:
            _LOST.add(name)
            raise UncertainOutcome("Simulated: the response was lost after creating.")
        return object_id

    def create_ad_set(
        self, account: AccountContext, spec: CampaignSpec, name: str, campaign_id: str
    ) -> str:
        if "[sim:fail-adset]" in name:
            raise ContentRejected("Simulated: the ad set was rejected (invalid targeting).")
        return self._remember(account, "adset", name, _new_id("adset"))

    def upload_image(self, account: AccountContext, content: bytes, filename: str) -> str:
        return f"simhash{secrets.token_hex(6)}"

    def create_creative(
        self, account: AccountContext, spec: CampaignSpec, name: str, image_hash: str | None
    ) -> str:
        return self._remember(account, "creative", name, _new_id("creative"))

    def create_ad(
        self, account: AccountContext, name: str, ad_set_id: str, creative_id: str
    ) -> str:
        return self._remember(account, "ad", name, _new_id("ad"))

    def find_by_name(self, account: AccountContext, level: str, contains: str) -> str | None:
        for name, object_id in _CREATED.get(account.external_id, {}).get(level, {}).items():
            if contains in name:
                return object_id
        return None

    def set_status(self, account: AccountContext, object_id: str, status: str) -> None:
        return None

    def set_daily_budget(self, account: AccountContext, campaign_id: str, amount: Decimal) -> None:
        return None
