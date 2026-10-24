"""Meta Marketing API implementation of ``AdsPlatform``.

Endpoints (Marketing API, v26.0 docs reviewed 2026-10-23):
- reads: GET act_<id>/campaigns, /adsets, /ads (cursor-paginated), GET act_<id>/insights
  with level=campaign and time_increment=1 (daily rows);
- writes: POST act_<id>/campaigns, /adsets, /adimages, /adcreatives, /ads; POST <object-id>
  with ``status`` or ``daily_budget``.

Campaigns use campaign budget optimization (the daily budget lives on the campaign) so a
budget change is a single write. Every object is created PAUSED.

Not yet exercised against the live API: field names and required parameters can differ
by objective and API version, which is why real-account validation is still required.
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.meta.graph import GraphClient

from .currency import from_minor, to_minor
from .platform import (
    AccountContext,
    CampaignSpec,
    RemoteAd,
    RemoteAdSet,
    RemoteCampaign,
    RemoteInsight,
)

#: Optimization goal and billing event per objective (ad set level).
_OPTIMIZATION = {
    "OUTCOME_TRAFFIC": ("LINK_CLICKS", "IMPRESSIONS"),
    "OUTCOME_AWARENESS": ("REACH", "IMPRESSIONS"),
    "OUTCOME_ENGAGEMENT": ("POST_ENGAGEMENT", "IMPRESSIONS"),
}
_LEVEL_EDGES = {"campaign": "campaigns", "adset": "adsets", "creative": "adcreatives", "ad": "ads"}


class MetaAdsPlatform:
    is_mock = False

    def __init__(self, graph: GraphClient) -> None:
        self.graph = graph

    def _key(self, account: AccountContext) -> str:
        return f"adaccount:{account.external_id}"

    def _list(self, account: AccountContext, edge: str, fields: str) -> list[dict[str, Any]]:
        return list(
            self.graph.paginate(
                f"{account.external_id}/{edge}",
                token=account.token,
                params={"fields": fields, "limit": 200},
                throttle_key=self._key(account),
            )
        )

    # --- Reads -------------------------------------------------------------------------

    def list_campaigns(self, account: AccountContext) -> list[RemoteCampaign]:
        fields = (
            "id,name,objective,status,effective_status,daily_budget,lifetime_budget,"
            "special_ad_categories"
        )
        return [
            RemoteCampaign(
                id=str(c["id"]),
                name=c.get("name", ""),
                objective=c.get("objective", ""),
                configured_status=c.get("status", ""),
                effective_status=c.get("effective_status", ""),
                daily_budget=from_minor(c.get("daily_budget"), account.currency),
                lifetime_budget=from_minor(c.get("lifetime_budget"), account.currency),
                special_ad_categories=list(c.get("special_ad_categories") or []),
            )
            for c in self._list(account, "campaigns", fields)
        ]

    def list_ad_sets(self, account: AccountContext) -> list[RemoteAdSet]:
        fields = (
            "id,campaign_id,name,status,effective_status,daily_budget,optimization_goal,"
            "billing_event,targeting,start_time,end_time"
        )
        return [
            RemoteAdSet(
                id=str(a["id"]),
                campaign_id=str(a.get("campaign_id", "")),
                name=a.get("name", ""),
                configured_status=a.get("status", ""),
                effective_status=a.get("effective_status", ""),
                daily_budget=from_minor(a.get("daily_budget"), account.currency),
                optimization_goal=a.get("optimization_goal", ""),
                billing_event=a.get("billing_event", ""),
                targeting=a.get("targeting") or {},
                start_time=_dt(a.get("start_time")),
                end_time=_dt(a.get("end_time")),
            )
            for a in self._list(account, "adsets", fields)
        ]

    def list_ads(self, account: AccountContext) -> list[RemoteAd]:
        fields = "id,adset_id,name,status,effective_status,creative{id}"
        return [
            RemoteAd(
                id=str(a["id"]),
                adset_id=str(a.get("adset_id", "")),
                name=a.get("name", ""),
                configured_status=a.get("status", ""),
                effective_status=a.get("effective_status", ""),
                creative_id=str((a.get("creative") or {}).get("id", "")),
            )
            for a in self._list(account, "ads", fields)
        ]

    def insights(self, account: AccountContext, *, since: date, until: date) -> list[RemoteInsight]:
        rows = self.graph.paginate(
            f"{account.external_id}/insights",
            token=account.token,
            params={
                "level": "campaign",
                "time_increment": 1,
                "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
                "fields": (
                    "campaign_id,date_start,spend,impressions,reach,clicks,"
                    "inline_link_clicks,ctr,cpc,cpm"
                ),
                "limit": 500,
            },
            throttle_key=self._key(account),
        )
        return [
            RemoteInsight(
                campaign_id=str(r.get("campaign_id", "")),
                date=date.fromisoformat(r["date_start"]),
                spend=_dec(r.get("spend")),
                impressions=_int(r.get("impressions")),
                reach=_int(r.get("reach")),
                clicks=_int(r.get("clicks")),
                link_clicks=_int(r.get("inline_link_clicks")),
                ctr=_dec(r.get("ctr")),
                cpc=_dec(r.get("cpc")),
                cpm=_dec(r.get("cpm")),
            )
            for r in rows
            if r.get("date_start")
        ]

    # --- Writes ------------------------------------------------------------------------

    def _post(self, account: AccountContext, path: str, data: dict[str, Any], **kw: Any) -> str:
        body = self.graph.request(
            "POST",
            path,
            token=account.token,
            data=data,
            write=True,
            throttle_key=self._key(account),
            **kw,
        )
        return str(body.get("id") or body.get("success") or "")

    def create_campaign(self, account: AccountContext, spec: CampaignSpec, name: str) -> str:
        return self._post(
            account,
            f"{account.external_id}/campaigns",
            {
                "name": name,
                "objective": spec.objective,
                "status": "PAUSED",
                "special_ad_categories": json.dumps(spec.special_ad_categories),
                "daily_budget": to_minor(spec.daily_budget, account.currency),
                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            },
        )

    def create_ad_set(
        self, account: AccountContext, spec: CampaignSpec, name: str, campaign_id: str
    ) -> str:
        goal, billing = _OPTIMIZATION[spec.objective]
        targeting: dict[str, Any] = {
            "geo_locations": {"countries": spec.countries},
            "age_min": spec.age_min,
            "age_max": spec.age_max,
        }
        if spec.genders:
            targeting["genders"] = spec.genders
        data: dict[str, Any] = {
            "name": name,
            "campaign_id": campaign_id,
            "status": "PAUSED",
            "optimization_goal": goal,
            "billing_event": billing,
            "targeting": json.dumps(targeting),
        }
        if spec.objective == "OUTCOME_ENGAGEMENT":
            data["promoted_object"] = json.dumps({"page_id": spec.page_id})
        if spec.objective == "OUTCOME_TRAFFIC":
            data["destination_type"] = "WEBSITE"
        if spec.start_time:
            data["start_time"] = spec.start_time.isoformat()
        if spec.end_time:
            data["end_time"] = spec.end_time.isoformat()
        return self._post(account, f"{account.external_id}/adsets", data)

    def upload_image(self, account: AccountContext, content: bytes, filename: str) -> str:
        body = self.graph.request(
            "POST",
            f"{account.external_id}/adimages",
            token=account.token,
            data={},
            files={"filename": (filename, content)},
            write=True,
            throttle_key=self._key(account),
        )
        images = body.get("images") or {}
        first: dict[str, Any] = next(iter(images.values()), {})
        return str(first.get("hash", ""))

    def create_creative(
        self, account: AccountContext, spec: CampaignSpec, name: str, image_hash: str | None
    ) -> str:
        link_data: dict[str, Any] = {
            "link": spec.link,
            "message": spec.primary_text,
            "name": spec.headline,
            "call_to_action": {"type": spec.call_to_action, "value": {"link": spec.link}},
        }
        if spec.description:
            link_data["description"] = spec.description
        if image_hash:
            link_data["image_hash"] = image_hash
        return self._post(
            account,
            f"{account.external_id}/adcreatives",
            {
                "name": name,
                "object_story_spec": json.dumps({"page_id": spec.page_id, "link_data": link_data}),
            },
        )

    def create_ad(
        self, account: AccountContext, name: str, ad_set_id: str, creative_id: str
    ) -> str:
        return self._post(
            account,
            f"{account.external_id}/ads",
            {
                "name": name,
                "adset_id": ad_set_id,
                "creative": json.dumps({"creative_id": creative_id}),
                "status": "PAUSED",
            },
        )

    def find_by_name(self, account: AccountContext, level: str, contains: str) -> str | None:
        body = self.graph.request(
            "GET",
            f"{account.external_id}/{_LEVEL_EDGES[level]}",
            token=account.token,
            params={
                "fields": "id,name",
                "filtering": json.dumps(
                    [{"field": "name", "operator": "CONTAIN", "value": contains}]
                ),
                "limit": 5,
            },
            throttle_key=self._key(account),
        )
        found = body.get("data") or []
        return str(found[0]["id"]) if found else None

    def set_status(self, account: AccountContext, object_id: str, status: str) -> None:
        self._post(account, object_id, {"status": status})

    def set_daily_budget(self, account: AccountContext, campaign_id: str, amount: Decimal) -> None:
        self._post(account, campaign_id, {"daily_budget": to_minor(amount, account.currency)})


def _dec(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("+0000", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
