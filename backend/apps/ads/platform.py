"""Internal interface for advertising platforms.

Business logic (sync, execution, policies) uses these types only. ``MetaAdsPlatform``
implements them with the Marketing API; ``SimulatedAdsPlatform`` (simulation.py)
implements them without contacting anyone. Another channel would add an implementation,
not change callers.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class AccountContext:
    external_id: str  # "act_<id>"
    token: str
    currency: str


@dataclass(frozen=True)
class RemoteCampaign:
    id: str
    name: str
    objective: str
    configured_status: str
    effective_status: str
    daily_budget: Decimal | None
    lifetime_budget: Decimal | None
    special_ad_categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RemoteAdSet:
    id: str
    campaign_id: str
    name: str
    configured_status: str
    effective_status: str
    daily_budget: Decimal | None
    optimization_goal: str
    billing_event: str
    targeting: dict[str, Any]
    start_time: datetime | None
    end_time: datetime | None


@dataclass(frozen=True)
class RemoteAd:
    id: str
    adset_id: str
    name: str
    configured_status: str
    effective_status: str
    creative_id: str


@dataclass(frozen=True)
class RemoteInsight:
    campaign_id: str
    date: date
    spend: Decimal | None
    impressions: int | None
    reach: int | None
    clicks: int | None
    link_clicks: int | None
    ctr: Decimal | None
    cpc: Decimal | None
    cpm: Decimal | None


@dataclass(frozen=True)
class CampaignSpec:
    """Validated input for creating one campaign → ad set → creative → ad on a platform."""

    name: str
    objective: str
    daily_budget: Decimal
    special_ad_categories: list[str]
    countries: list[str]
    age_min: int
    age_max: int
    genders: list[int]
    page_id: str
    primary_text: str
    headline: str
    description: str
    link: str
    call_to_action: str
    start_time: datetime | None
    end_time: datetime | None


class AdsPlatform(Protocol):
    is_mock: bool

    def list_campaigns(self, account: AccountContext) -> list[RemoteCampaign]: ...

    def list_ad_sets(self, account: AccountContext) -> list[RemoteAdSet]: ...

    def list_ads(self, account: AccountContext) -> list[RemoteAd]: ...

    def insights(
        self, account: AccountContext, *, since: date, until: date
    ) -> list[RemoteInsight]: ...

    # Writes. Everything is created PAUSED; delivery starts only through set_status.

    def create_campaign(self, account: AccountContext, spec: CampaignSpec, name: str) -> str: ...

    def create_ad_set(
        self, account: AccountContext, spec: CampaignSpec, name: str, campaign_id: str
    ) -> str: ...

    def upload_image(self, account: AccountContext, content: bytes, filename: str) -> str: ...

    def create_creative(
        self, account: AccountContext, spec: CampaignSpec, name: str, image_hash: str | None
    ) -> str: ...

    def create_ad(
        self, account: AccountContext, name: str, ad_set_id: str, creative_id: str
    ) -> str: ...

    def find_by_name(self, account: AccountContext, level: str, contains: str) -> str | None: ...

    def set_status(self, account: AccountContext, object_id: str, status: str) -> None: ...

    def set_daily_budget(
        self, account: AccountContext, campaign_id: str, amount: Decimal
    ) -> None: ...
