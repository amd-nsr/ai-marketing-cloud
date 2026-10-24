"""Ad accounts, synchronization and the campaign draft lifecycle.

Writes to Meta never happen here directly: they are AutomationActions evaluated by the
policy engine and carried out by ``execution.py``.
"""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.core.errors import Conflict
from apps.meta import permissions
from apps.meta.models import MetaConnection
from apps.social.adapters.base import RateLimited, ReauthRequired, SocialError

from .models import Ad, AdAccount, AdCampaign, AdInsight, AdSet, AdSyncRun
from .platform import AccountContext, AdsPlatform

logger = logging.getLogger(__name__)


def platform_for(account: AdAccount) -> AdsPlatform:
    if account.is_mock:
        from .simulation import SimulatedAdsPlatform

        return SimulatedAdsPlatform()
    from apps.meta.graph import GraphClient

    from .meta_platform import MetaAdsPlatform

    return MetaAdsPlatform(GraphClient.from_settings())


def context_for(account: AdAccount) -> AccountContext:
    connection = account.meta_connection
    token = connection.user_token if connection else None
    if not account.is_usable or not token:
        raise Conflict(f"{account.name} needs to be reconnected with Meta.")
    return AccountContext(external_id=account.external_id, token=token, currency=account.currency)


# --- Connecting -----------------------------------------------------------------------------


@transaction.atomic
def connect_ad_accounts(
    connection: MetaConnection, *, account_ids: list[str], actor: Any
) -> list[AdAccount]:
    if not settings.META_ADS_ENABLED:
        raise Conflict("Advertising isn't enabled for this environment.")
    if not permissions.has_feature(connection.granted_permissions, permissions.ADS_READ_FEATURE):
        raise Conflict("Ads permissions weren't granted. Reconnect and allow them.")
    available = {a["id"]: a for a in connection.available_ad_accounts}
    unknown = [i for i in account_ids if i not in available]
    if unknown:
        raise ValidationError({"account_ids": "Some ad accounts aren't available to this login."})
    org = connection.organization
    accounts = []
    for ext_id in account_ids:
        info = available[ext_id]
        account, created = AdAccount.objects.get_or_create(
            organization=org,
            platform="meta",
            external_id=ext_id,
            defaults={
                "name": info["name"],
                "currency": info["currency"],
                "is_mock": connection.is_mock,
                "connected_by": actor,
            },
        )
        account.name = info["name"]
        account.currency = info["currency"]
        account.timezone_name = info.get("timezone_name", "")
        account.account_status = int(info.get("account_status") or 0)
        account.is_mock = connection.is_mock
        account.meta_connection = connection
        account.status = AdAccount.Status.CONNECTED
        account.last_error = ""
        account.connected_by = actor
        account.save()
        accounts.append(account)
        audit.record(
            "ads.account_connected" if created else "ads.account_reconnected",
            organization=org,
            actor=actor,
            target=account,
            metadata={"external_id": ext_id, "simulation": account.is_mock},
        )
        transaction.on_commit(_queue_sync(str(account.pk), "connect"))
    return accounts


def _queue_sync(account_id: str, trigger: str) -> Any:
    def queue() -> None:
        from .tasks import sync_ad_account

        sync_ad_account.delay(account_id, trigger)

    return queue


def disconnect_ad_account(account: AdAccount, *, actor: Any, reason: str = "") -> None:
    from apps.automation.services import cancel_pending_for_ad_account

    cancel_pending_for_ad_account(account, actor=actor, reason=reason or "Ad account disconnected")
    account.status = AdAccount.Status.DISCONNECTED
    account.save(update_fields=["status", "updated_at"])
    audit.record(
        "ads.account_disconnected",
        organization=account.organization,
        actor=actor,
        target=account,
        metadata={"reason": reason[:200]},
    )


def disconnect_ad_accounts_for(connection: MetaConnection, *, actor: Any, reason: str) -> int:
    accounts = list(connection.ad_accounts.exclude(status=AdAccount.Status.DISCONNECTED))
    for account in accounts:
        disconnect_ad_account(account, actor=actor, reason=reason)
    return len(accounts)


def mark_accounts_needing_reauth(connection: MetaConnection, reason: str) -> None:
    connection.ad_accounts.filter(status=AdAccount.Status.CONNECTED).update(
        status=AdAccount.Status.NEEDS_REAUTH, last_error=reason[:500]
    )


def purge_meta_data(connection: MetaConnection) -> dict[str, int]:
    """Delete data obtained from Meta through this connection (data-deletion request).
    Our own drafts stay, detached from Meta ids."""
    counts = {"ad_insights": 0, "ad_objects": 0, "synced_campaigns": 0}
    for account in connection.ad_accounts.all():
        counts["ad_insights"] += account.insights.all().delete()[0]
        ad_sets = AdSet.objects.filter(campaign__ad_account=account)
        counts["ad_objects"] += Ad.objects.filter(ad_set__in=ad_sets).delete()[0]
        counts["ad_objects"] += ad_sets.delete()[0]
        synced = account.campaigns.filter(source=AdCampaign.Source.SYNCED)
        counts["synced_campaigns"] += synced.delete()[0]
        account.campaigns.update(
            external_id=None,
            progress={},
            configured_status="",
            effective_status="",
            state=AdCampaign.State.REMOVED,
        )
        account.name = "Deleted ad account"
        account.status = AdAccount.Status.DISCONNECTED
        account.meta_connection = None
        account.save()
    return counts


# --- Synchronization ------------------------------------------------------------------------


def sync_account(account: AdAccount, *, trigger: str = "schedule") -> AdSyncRun:
    """Mirror campaigns, ad sets, ads and daily insights. Each step is independent: a
    failure in one is recorded and the others still run (status ``partial``)."""
    run = AdSyncRun.objects.create(
        organization=account.organization, ad_account=account, trigger=trigger
    )
    try:
        ctx = context_for(account)
    except Conflict as exc:
        return _finish_run(run, account, errors=[{"step": "auth", "error": str(exc)}])
    platform = platform_for(account)
    errors: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    now = timezone.now()

    def step(name: str, fn: Any) -> None:
        try:
            counts[name] = fn()
        except ReauthRequired as exc:
            raise exc
        except SocialError as exc:
            errors.append({"step": name, "error": str(exc)[:300], "code": exc.code})

    try:
        step("campaigns", lambda: _sync_campaigns(account, platform, ctx, now))
        step("ad_sets", lambda: _sync_ad_sets(account, platform, ctx, now))
        step("ads", lambda: _sync_ads(account, platform, ctx, now))
        step("insights", lambda: _sync_insights(account, platform, ctx, now))
    except ReauthRequired as exc:
        from apps.meta.services import mark_needs_reauth

        if account.meta_connection:
            mark_needs_reauth(account.meta_connection, str(exc))
        errors.append({"step": "auth", "error": str(exc)[:300], "code": exc.code})
    run.counts = counts
    return _finish_run(run, account, errors=errors, complete="insights" in counts)


def _finish_run(
    run: AdSyncRun, account: AdAccount, *, errors: list[dict[str, str]], complete: bool = False
) -> AdSyncRun:
    run.errors = errors
    run.finished_at = timezone.now()
    if not errors:
        run.status = AdSyncRun.Status.SUCCEEDED
    elif run.counts:
        run.status = AdSyncRun.Status.PARTIAL
    else:
        run.status = AdSyncRun.Status.FAILED
    run.save()
    account.last_sync_status = run.status
    account.last_error = "; ".join(e["error"] for e in errors)[:500]
    # Only a sync that refreshed spend counts towards "spend data is fresh".
    if complete:
        account.last_synced_at = run.finished_at
    account.save(update_fields=["last_sync_status", "last_error", "last_synced_at", "updated_at"])
    if errors:
        logger.warning(
            "Ad sync finished with errors",
            extra={"ad_account": str(account.pk), "status": run.status, "steps": len(errors)},
        )
    return run


def _sync_campaigns(
    account: AdAccount, platform: AdsPlatform, ctx: AccountContext, now: Any
) -> int:
    seen = 0
    for remote in platform.list_campaigns(ctx):
        campaign = AdCampaign.objects.filter(ad_account=account, external_id=remote.id).first()
        if campaign is None:
            campaign = AdCampaign(
                organization=account.organization,
                ad_account=account,
                external_id=remote.id,
                source=AdCampaign.Source.SYNCED,
                state=AdCampaign.State.CREATED,
            )
        campaign.name = remote.name
        campaign.objective = remote.objective
        previous = campaign.configured_status
        campaign.configured_status = remote.configured_status
        campaign.effective_status = remote.effective_status
        campaign.daily_budget = remote.daily_budget
        campaign.lifetime_budget = remote.lifetime_budget
        campaign.special_ad_categories = remote.special_ad_categories
        campaign.last_synced_at = now
        if remote.configured_status == "ACTIVE" and previous != "ACTIVE":
            campaign.activated_at = campaign.activated_at or now
        if remote.configured_status != "ACTIVE" and previous == "ACTIVE":
            campaign.paused_at = now
        campaign.save()
        seen += 1
    return seen


def _sync_ad_sets(account: AdAccount, platform: AdsPlatform, ctx: AccountContext, now: Any) -> int:
    campaigns = {c.external_id: c for c in account.campaigns.exclude(external_id__isnull=True)}
    seen = 0
    for remote in platform.list_ad_sets(ctx):
        campaign = campaigns.get(remote.campaign_id)
        if campaign is None:
            continue
        AdSet.objects.update_or_create(
            campaign=campaign,
            external_id=remote.id,
            defaults={
                "organization": account.organization,
                "name": remote.name,
                "configured_status": remote.configured_status,
                "effective_status": remote.effective_status,
                "daily_budget": remote.daily_budget,
                "optimization_goal": remote.optimization_goal,
                "billing_event": remote.billing_event,
                "targeting": remote.targeting,
                "start_time": remote.start_time,
                "end_time": remote.end_time,
                "last_synced_at": now,
            },
        )
        seen += 1
    return seen


def _sync_ads(account: AdAccount, platform: AdsPlatform, ctx: AccountContext, now: Any) -> int:
    ad_sets = {s.external_id: s for s in AdSet.objects.filter(campaign__ad_account=account)}
    seen = 0
    for remote in platform.list_ads(ctx):
        ad_set = ad_sets.get(remote.adset_id)
        if ad_set is None:
            continue
        Ad.objects.update_or_create(
            ad_set=ad_set,
            external_id=remote.id,
            defaults={
                "organization": account.organization,
                "name": remote.name,
                "configured_status": remote.configured_status,
                "effective_status": remote.effective_status,
                "creative_id": remote.creative_id,
                "last_synced_at": now,
            },
        )
        seen += 1
    return seen


def _sync_insights(account: AdAccount, platform: AdsPlatform, ctx: AccountContext, now: Any) -> int:
    until = now.date()
    since = until - timedelta(days=settings.ADS_INSIGHTS_DAYS - 1)
    campaigns = {c.external_id: c for c in account.campaigns.exclude(external_id__isnull=True)}
    seen = 0
    for row in platform.insights(ctx, since=since, until=until):
        AdInsight.objects.update_or_create(
            ad_account=account,
            campaign_external_id=row.campaign_id,
            date=row.date,
            defaults={
                "organization": account.organization,
                "campaign": campaigns.get(row.campaign_id),
                "currency": account.currency,
                "spend": row.spend,
                "impressions": row.impressions,
                "reach": row.reach,
                "clicks": row.clicks,
                "link_clicks": row.link_clicks,
                "ctr": row.ctr,
                "cpc": row.cpc,
                "cpm": row.cpm,
                "is_mock": account.is_mock,
                "retrieved_at": now,
            },
        )
        seen += 1
    return seen


def sync_due_accounts() -> int:
    ids = list(
        AdAccount.objects.filter(status=AdAccount.Status.CONNECTED).values_list("pk", flat=True)
    )
    from .tasks import sync_ad_account

    for pk in ids:
        sync_ad_account.delay(str(pk), "schedule")
    return len(ids)


def is_retryable(exc: Exception) -> bool:
    return isinstance(exc, RateLimited) or getattr(exc, "retryable", False)


# --- Drafts ---------------------------------------------------------------------------------


DRAFT_FIELDS = ("name", "objective", "daily_budget", "special_ad_categories", "spec")


@transaction.atomic
def create_draft(
    org: Any,
    *,
    actor: Any,
    ad_account: AdAccount,
    fields: dict[str, Any],
    source: str = AdCampaign.Source.MANUAL,
    run: Any = None,
) -> AdCampaign:
    if ad_account.organization_id != org.pk:
        raise ValidationError({"ad_account": "Unknown ad account."})
    campaign = AdCampaign(
        organization=org,
        ad_account=ad_account,
        source=source,
        state=AdCampaign.State.DRAFT,
        created_by=actor,
        ai_run=run,
        is_mock_ai=bool(run and run.is_mock),
    )
    for name in (*DRAFT_FIELDS, "marketing_campaign", "marketing_campaign_id", "ai_notes"):
        if name in fields:
            setattr(campaign, name, fields[name])
    campaign.save()
    audit.record(
        "ads.draft_created",
        organization=org,
        actor=actor,
        target=campaign,
        metadata={"source": source, "ai_run": str(run.pk) if run else None},
    )
    return campaign


@transaction.atomic
def update_draft(campaign: AdCampaign, *, actor: Any, fields: dict[str, Any]) -> AdCampaign:
    campaign = AdCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.state not in (
        AdCampaign.State.DRAFT,
        AdCampaign.State.APPROVED,
        AdCampaign.State.FAILED,
    ):
        raise Conflict("Only drafts that aren't on Meta yet can be edited here.")
    if campaign.progress:
        raise Conflict("Part of this campaign already exists on Meta; retry or remove it first.")
    changed = [k for k in (*DRAFT_FIELDS, "marketing_campaign") if k in fields]
    for name in changed:
        setattr(campaign, name, fields[name])
    campaign.revision += 1
    campaign.state = AdCampaign.State.DRAFT  # edits need a fresh approval
    campaign.save()
    audit.record(
        "ads.draft_updated",
        organization=campaign.organization,
        actor=actor,
        target=campaign,
        metadata={"fields": changed, "revision": campaign.revision},
    )
    return campaign


@transaction.atomic
def approve_draft(campaign: AdCampaign, *, actor: Any) -> AdCampaign:
    from .validation import validate

    campaign = AdCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.state != AdCampaign.State.DRAFT:
        raise Conflict("Only drafts can be approved.")
    if issues := validate(campaign):
        raise ValidationError({i.field: i.message for i in issues})
    campaign.state = AdCampaign.State.APPROVED
    campaign.approved_revision = campaign.revision
    campaign.approved_by, campaign.approved_at = actor, timezone.now()
    campaign.save()
    audit.record(
        "ads.draft_approved",
        organization=campaign.organization,
        actor=actor,
        target=campaign,
        metadata={"revision": campaign.revision, "daily_budget": str(campaign.daily_budget)},
    )
    return campaign


def delete_draft(campaign: AdCampaign, *, actor: Any) -> None:
    if campaign.external_id or campaign.progress:
        raise Conflict("Campaigns that exist on Meta can't be deleted here; pause them instead.")
    audit.record(
        "ads.draft_deleted",
        organization=campaign.organization,
        actor=actor,
        metadata={"name": campaign.name},
    )
    campaign.delete()


def total_spend(campaign: AdCampaign, days: int) -> Decimal:
    since = timezone.now().date() - timedelta(days=days - 1)
    values = campaign.insights.filter(date__gte=since).values_list("spend", flat=True)
    return sum((v for v in values if v is not None), Decimal(0))
