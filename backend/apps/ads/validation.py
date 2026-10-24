"""Deterministic validation of a campaign draft before it can be approved or created.

The spec shape (``AdCampaign.spec``)::

    {
      "targeting": {"countries": ["US"], "age_min": 18, "age_max": 65, "genders": []},
      "creative": {"page_account_id": "<SocialAccount uuid>", "primary_text": "...",
                   "headline": "...", "description": "", "link": "https://...",
                   "call_to_action": "LEARN_MORE", "image_asset_id": "<ContentAsset uuid>"},
      "schedule": {"start_time": "<iso>", "end_time": "<iso>"}
    }

Spend limits are *not* checked here: they belong to the automation policy and are
evaluated at the moment a write would happen (policy.py), so a valid draft can still be
refused if the organization's limits or current spend don't allow it.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import AdCampaign
from .platform import CampaignSpec

OBJECTIVES = {c.value for c in AdCampaign.Objective}
CALLS_TO_ACTION = {
    "LEARN_MORE",
    "SHOP_NOW",
    "SIGN_UP",
    "CONTACT_US",
    "ORDER_NOW",
    "GET_OFFER",
    "BOOK_NOW",
}
#: Categories that restrict targeting (Meta "special ad categories").
RESTRICTED_CATEGORIES = {"HOUSING", "EMPLOYMENT", "CREDIT"}
#: Requires separate authorization with Meta; not supported by this integration.
UNSUPPORTED_CATEGORIES = {"ISSUES_ELECTIONS_POLITICS"}
MIN_DAILY_BUDGET = Decimal("1.00")
_COUNTRY = re.compile(r"^[A-Z]{2}$")


@dataclass(frozen=True)
class Issue:
    field: str
    message: str


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except InvalidOperation:
        return None


def _when(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return parse_datetime(str(value))


def validate(campaign: AdCampaign) -> list[Issue]:
    issues: list[Issue] = []
    spec = campaign.spec or {}
    targeting = spec.get("targeting") or {}
    creative = spec.get("creative") or {}
    schedule = spec.get("schedule") or {}

    if not campaign.name.strip():
        issues.append(Issue("name", "Give the campaign a name."))
    if campaign.objective not in OBJECTIVES:
        issues.append(Issue("objective", "Choose Traffic, Awareness or Engagement."))

    budget = campaign.daily_budget
    if budget is None:
        issues.append(Issue("daily_budget", "Set a daily budget."))
    elif budget < MIN_DAILY_BUDGET:
        issues.append(
            Issue("daily_budget", f"The daily budget must be at least {MIN_DAILY_BUDGET}.")
        )

    categories = set(campaign.special_ad_categories or [])
    if categories & UNSUPPORTED_CATEGORIES:
        issues.append(
            Issue(
                "special_ad_categories",
                "Political and social-issue ads need Meta authorization and aren't supported.",
            )
        )
    unknown = categories - RESTRICTED_CATEGORIES - UNSUPPORTED_CATEGORIES
    if unknown:
        issues.append(Issue("special_ad_categories", f"Unknown category: {', '.join(unknown)}."))

    countries = targeting.get("countries") or []
    if not countries or len(countries) > 25 or not all(_COUNTRY.match(str(c)) for c in countries):
        issues.append(Issue("targeting.countries", "Choose 1-25 countries (two-letter codes)."))
    age_min, age_max = targeting.get("age_min", 18), targeting.get("age_max", 65)
    if not (
        isinstance(age_min, int) and isinstance(age_max, int) and 18 <= age_min <= age_max <= 65
    ):
        issues.append(Issue("targeting.age", "Ages must be between 18 and 65, min ≤ max."))
    genders = targeting.get("genders") or []
    if not set(genders) <= {1, 2}:
        issues.append(Issue("targeting.genders", "Genders must be 1 (men) and/or 2 (women)."))
    if categories & RESTRICTED_CATEGORIES and (genders or age_min != 18 or age_max != 65):
        issues.append(
            Issue(
                "targeting",
                "Housing, employment and credit ads can't be narrowed by age or gender.",
            )
        )

    page = _page_for(campaign, creative.get("page_account_id"))
    if page is None:
        issues.append(
            Issue("creative.page", "Choose a connected Facebook Page to run the ad from.")
        )
    primary_text = str(creative.get("primary_text") or "").strip()
    if not primary_text or len(primary_text) > 2000:
        issues.append(Issue("creative.primary_text", "Write the ad text (up to 2,000 characters)."))
    headline = str(creative.get("headline") or "").strip()
    if not headline or len(headline) > 255:
        issues.append(Issue("creative.headline", "Write a headline (up to 255 characters)."))
    link = str(creative.get("link") or "")
    parsed = urlparse(link)
    if parsed.scheme != "https" or not parsed.netloc:
        issues.append(Issue("creative.link", "Add the https:// page people land on."))
    if creative.get("call_to_action") not in CALLS_TO_ACTION:
        issues.append(Issue("creative.call_to_action", "Choose a call-to-action button."))
    if image_id := creative.get("image_asset_id"):
        from apps.content.models import ContentAsset

        asset = ContentAsset.objects.filter(
            organization_id=campaign.organization_id, pk=image_id
        ).first()
        if asset is None or not asset.content_type.startswith("image/"):
            issues.append(Issue("creative.image", "The selected image isn't available."))

    start, end = _when(schedule.get("start_time")), _when(schedule.get("end_time"))
    if start and start < timezone.now() - timedelta(minutes=5):
        issues.append(Issue("schedule.start_time", "The start time is in the past."))
    if start and end and end <= start:
        issues.append(Issue("schedule.end_time", "The end must be after the start."))
    return issues


def _page_for(campaign: AdCampaign, page_account_id: Any) -> Any:
    from apps.social.models import SocialAccount

    if not page_account_id:
        return None
    return SocialAccount.objects.filter(
        organization_id=campaign.organization_id,
        pk=page_account_id,
        platform="facebook",
        status=SocialAccount.Status.CONNECTED,
        # Simulation ad accounts run simulation Pages; real ones need a real Page.
        is_mock=campaign.ad_account.is_mock,
    ).first()


def to_spec(campaign: AdCampaign) -> CampaignSpec:
    """Build the platform request from a draft that passed ``validate``."""
    spec = campaign.spec or {}
    targeting = spec.get("targeting") or {}
    creative = spec.get("creative") or {}
    schedule = spec.get("schedule") or {}
    page = _page_for(campaign, creative.get("page_account_id"))
    if page is None or campaign.daily_budget is None:
        raise ValueError("to_spec requires a draft that passed validate().")
    return CampaignSpec(
        name=campaign.name,
        objective=campaign.objective,
        daily_budget=campaign.daily_budget,
        special_ad_categories=sorted(campaign.special_ad_categories or []),
        countries=[str(c) for c in targeting.get("countries", [])],
        age_min=int(targeting.get("age_min", 18)),
        age_max=int(targeting.get("age_max", 65)),
        genders=[int(g) for g in targeting.get("genders", [])],
        page_id=page.external_id,
        primary_text=str(creative.get("primary_text", "")).strip(),
        headline=str(creative.get("headline", "")).strip(),
        description=str(creative.get("description", "")).strip(),
        link=str(creative.get("link", "")),
        call_to_action=str(creative.get("call_to_action")),
        start_time=_when(schedule.get("start_time")),
        end_time=_when(schedule.get("end_time")),
    )


def budget_value(value: Any) -> Decimal | None:
    return _decimal(value)
