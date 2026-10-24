"""Carry out ad actions the policy engine cleared (called from automation.execute_action).

- Create: campaign → ad set → (image) → creative → ad, all PAUSED. Each step's Meta id is
  saved as soon as it exists (``AdCampaign.progress``), so a failed creation resumes from
  the failed step instead of duplicating objects. If a response is lost
  (``UncertainOutcome``), the object is looked up by its name tag before anything is
  re-created.
- Activate: ad, ad set, then campaign set to ACTIVE (campaign last, so delivery starts only
  once everything is ready). Pause: campaign to PAUSED. Budget: campaign daily_budget.
  These are idempotent (they set absolute values), so one immediate retry is safe after a
  lost response.

A sync is queued after every write so the mirror reflects what Meta actually has.
"""

import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.core.errors import Conflict
from apps.social.adapters.base import ReauthRequired, SocialError, UncertainOutcome

from .models import AdCampaign
from .platform import AccountContext, AdsPlatform
from .services import context_for, platform_for
from .validation import to_spec

logger = logging.getLogger(__name__)


class ExecutionFailed(Exception):
    pass


def execute(action: Any) -> None:
    """Raise ``ExecutionFailed`` with a readable message if the write didn't complete."""
    campaign: AdCampaign = AdCampaign.objects.select_related("ad_account__meta_connection").get(
        pk=action.ad_campaign_id
    )
    account = campaign.ad_account
    try:
        ctx = context_for(account)
    except Conflict as exc:
        raise ExecutionFailed(str(exc)) from exc
    platform = platform_for(account)
    t = action.action_type
    try:
        if t == "ads_create":
            _create(campaign, platform, ctx)
        elif t == "ads_activate":
            _activate(campaign, platform, ctx)
        elif t == "ads_pause":
            _set_status_once(platform, ctx, campaign.external_id or "", "PAUSED")
            campaign.configured_status = "PAUSED"
            campaign.paused_at = timezone.now()
            campaign.save(update_fields=["configured_status", "paused_at", "updated_at"])
        elif t == "ads_budget_change":
            new = Decimal(str(action.payload["daily_budget"]))
            _idempotent(lambda: platform.set_daily_budget(ctx, campaign.external_id or "", new))
            campaign.daily_budget = new
            campaign.save(update_fields=["daily_budget", "updated_at"])
        else:
            raise ExecutionFailed(f"Unknown ad action {t}.")
    except ReauthRequired as exc:
        from apps.meta.services import mark_needs_reauth

        if account.meta_connection:
            mark_needs_reauth(account.meta_connection, str(exc))
        raise ExecutionFailed(f"Meta needs you to reconnect: {exc}") from exc
    except SocialError as exc:
        raise ExecutionFailed(str(exc)[:500]) from exc
    finally:
        from .tasks import sync_ad_account

        transaction.on_commit(lambda: sync_ad_account.delay(str(account.pk), "after_write"))
    audit.record(
        "ads.write_executed",
        organization=campaign.organization,
        target=campaign,
        system=True,
        metadata={"type": t, "external_id": campaign.external_id, "action": str(action.pk)},
    )


def _idempotent(fn: Callable[[], None]) -> None:
    """Absolute-value writes: retry once after a lost response, then report."""
    try:
        fn()
    except UncertainOutcome:
        fn()


def _set_status_once(
    platform: AdsPlatform, ctx: AccountContext, object_id: str, status: str
) -> None:
    _idempotent(lambda: platform.set_status(ctx, object_id, status))


def _create(campaign: AdCampaign, platform: AdsPlatform, ctx: AccountContext) -> None:
    spec = to_spec(campaign)
    tag = campaign.name_tag
    names = {
        "campaign": f"{spec.name} {tag}",
        "adset": f"{spec.name} · ad set {tag}",
        "creative": f"{spec.name} · creative {tag}",
        "ad": f"{spec.name} · ad {tag}",
    }
    progress = dict(campaign.progress or {})
    campaign.state = AdCampaign.State.CREATING
    campaign.last_error = ""
    campaign.save(update_fields=["state", "last_error", "updated_at"])

    def ensure(level: str, key: str, create: Callable[[], str]) -> str:
        if progress.get(key):
            return str(progress[key])
        try:
            object_id = create()
        except UncertainOutcome:
            found = platform.find_by_name(ctx, level, names[level])
            if not found:
                raise
            object_id = found
        if not object_id:
            raise UncertainOutcome(f"Meta returned no id for the {level}.")
        progress[key] = object_id
        campaign.progress = progress
        campaign.save(update_fields=["progress", "updated_at"])
        return object_id

    try:
        campaign_id = ensure(
            "campaign",
            "campaign_id",
            lambda: platform.create_campaign(ctx, spec, names["campaign"]),
        )
        adset_id = ensure(
            "adset",
            "adset_id",
            lambda: platform.create_ad_set(ctx, spec, names["adset"], campaign_id),
        )
        image_hash = progress.get("image_hash") or _upload_image(campaign, platform, ctx)
        if image_hash and not progress.get("image_hash"):
            progress["image_hash"] = image_hash
            campaign.progress = progress
            campaign.save(update_fields=["progress", "updated_at"])
        creative_id = ensure(
            "creative",
            "creative_id",
            lambda: platform.create_creative(ctx, spec, names["creative"], image_hash or None),
        )
        ensure("ad", "ad_id", lambda: platform.create_ad(ctx, names["ad"], adset_id, creative_id))
    except SocialError as exc:
        campaign.state = AdCampaign.State.FAILED
        step = next(
            (k for k in ("campaign_id", "adset_id", "creative_id", "ad_id") if k not in progress),
            "",
        )
        campaign.last_error = f"Stopped at {step.removesuffix('_id') or 'the last step'}: {exc}"[
            :500
        ]
        campaign.save(update_fields=["state", "last_error", "updated_at"])
        raise
    campaign.external_id = progress["campaign_id"]
    campaign.state = AdCampaign.State.CREATED
    campaign.configured_status = campaign.effective_status = "PAUSED"
    campaign.save()


def _upload_image(campaign: AdCampaign, platform: AdsPlatform, ctx: AccountContext) -> str:
    image_id = (campaign.spec.get("creative") or {}).get("image_asset_id")
    if not image_id:
        return ""
    from apps.content.models import ContentAsset

    asset = ContentAsset.objects.get(organization_id=campaign.organization_id, pk=image_id)
    with asset.file.open("rb") as handle:
        content = handle.read()
    return platform.upload_image(ctx, content, asset.original_filename or "image.jpg")


def _activate(campaign: AdCampaign, platform: AdsPlatform, ctx: AccountContext) -> None:
    progress = campaign.progress or {}
    for key in ("ad_id", "adset_id"):
        if progress.get(key):
            _set_status_once(platform, ctx, progress[key], "ACTIVE")
    _set_status_once(platform, ctx, campaign.external_id or "", "ACTIVE")
    campaign.configured_status = "ACTIVE"
    campaign.activated_at = timezone.now()
    campaign.paused_at = None
    campaign.save(update_fields=["configured_status", "activated_at", "paused_at", "updated_at"])
