"""Advertising: connected ad accounts, campaigns (our drafts and their Meta mirror),
ad sets, ads, daily insights, and sync history.

Money is stored in the ad account's currency, in major units (e.g. 12.50 USD). Meta's
Marketing API uses minor units; conversion happens only at the API boundary
(``currency.py``). Missing metrics are NULL, never 0.
"""

from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


class AdAccount(OrganizationOwnedModel):
    class Status(models.TextChoices):
        CONNECTED = "connected", "Connected"
        NEEDS_REAUTH = "needs_reauth", "Reconnect required"
        DISCONNECTED = "disconnected", "Disconnected"

    meta_connection = models.ForeignKey(
        "meta.MetaConnection",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ad_accounts",
    )
    platform = models.CharField(max_length=16, default="meta")
    external_id = models.CharField(max_length=64)  # "act_<id>"
    name = models.CharField(max_length=200)
    currency = models.CharField(max_length=3)
    timezone_name = models.CharField(max_length=64, blank=True)
    #: Meta's account_status (1 = active; others mean the account can't deliver).
    account_status = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CONNECTED)
    is_mock = models.BooleanField(default=False)
    last_error = models.CharField(max_length=500, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=16, blank=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    connected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "platform", "external_id"], name="uniq_ad_account"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.external_id})"

    @property
    def is_usable(self) -> bool:
        connection = self.meta_connection
        return (
            self.status == self.Status.CONNECTED and connection is not None and connection.is_usable
        )


class AdCampaign(OrganizationOwnedModel):
    """A campaign we drafted (and may have created on Meta), or one synced from Meta."""

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved, not on Meta yet"
        CREATING = "creating", "Creating on Meta"
        CREATED = "created", "On Meta"
        FAILED = "failed", "Creation failed"
        REMOVED = "removed", "Removed"

    class Source(models.TextChoices):
        AI = "ai", "AI draft"
        MANUAL = "manual", "Created here"
        SYNCED = "synced", "Created on Meta"

    class Objective(models.TextChoices):
        TRAFFIC = "OUTCOME_TRAFFIC", "Traffic"
        AWARENESS = "OUTCOME_AWARENESS", "Awareness"
        ENGAGEMENT = "OUTCOME_ENGAGEMENT", "Engagement"

    ad_account = models.ForeignKey(AdAccount, on_delete=models.CASCADE, related_name="campaigns")
    # NULL (not "") for drafts so the conditional unique constraint ignores them.
    external_id = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    name = models.CharField(max_length=200)
    objective = models.CharField(max_length=40, blank=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.DRAFT)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.MANUAL)
    #: Status configured on Meta (ACTIVE, PAUSED, ARCHIVED, DELETED) and what Meta
    #: reports as actually delivering (effective_status).
    configured_status = models.CharField(max_length=24, blank=True)
    effective_status = models.CharField(max_length=40, blank=True)
    daily_budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    lifetime_budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    special_ad_categories = models.JSONField(default=list, blank=True)
    #: Our draft definition: targeting, creative, schedule (see validation.py).
    spec = models.JSONField(default=dict, blank=True)
    #: Internal marketing campaign this ad campaign belongs to.
    marketing_campaign = models.ForeignKey(
        "marketing.Campaign",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ad_campaigns",
    )
    ai_run = models.ForeignKey(
        "ai.AIWorkflowRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    ai_notes = models.JSONField(default=list, blank=True)
    is_mock_ai = models.BooleanField(default=False)
    #: Increments on every edit; approval is for one revision.
    revision = models.PositiveIntegerField(default=1)
    approved_revision = models.PositiveIntegerField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    #: External ids created so far, so a failed creation resumes instead of duplicating.
    progress = models.JSONField(default=dict, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["ad_account", "external_id"],
                condition=models.Q(external_id__isnull=False),
                name="uniq_ad_campaign_external",
            )
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_approved(self) -> bool:
        return self.approved_revision is not None and self.approved_revision == self.revision

    @property
    def is_live(self) -> bool:
        return self.state == self.State.CREATED and self.configured_status == "ACTIVE"

    @property
    def name_tag(self) -> str:
        """Short marker added to names on Meta, used to find objects after a lost response."""
        return f"[amc-{str(self.pk)[:8]}]"


class AdSet(OrganizationOwnedModel):
    campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name="ad_sets")
    external_id = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    configured_status = models.CharField(max_length=24, blank=True)
    effective_status = models.CharField(max_length=40, blank=True)
    daily_budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    optimization_goal = models.CharField(max_length=40, blank=True)
    billing_event = models.CharField(max_length=40, blank=True)
    targeting = models.JSONField(default=dict, blank=True)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "external_id"], name="uniq_ad_set")
        ]


class Ad(OrganizationOwnedModel):
    ad_set = models.ForeignKey(AdSet, on_delete=models.CASCADE, related_name="ads")
    external_id = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    configured_status = models.CharField(max_length=24, blank=True)
    effective_status = models.CharField(max_length=40, blank=True)
    creative_id = models.CharField(max_length=64, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["ad_set", "external_id"], name="uniq_ad")]


class AdInsight(OrganizationOwnedModel):
    """Daily performance for one campaign, as reported by the platform."""

    ad_account = models.ForeignKey(AdAccount, on_delete=models.CASCADE, related_name="insights")
    campaign = models.ForeignKey(
        AdCampaign, null=True, blank=True, on_delete=models.CASCADE, related_name="insights"
    )
    campaign_external_id = models.CharField(max_length=64)
    date = models.DateField()
    currency = models.CharField(max_length=3)
    spend = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    impressions = models.BigIntegerField(null=True, blank=True)
    reach = models.BigIntegerField(null=True, blank=True)
    clicks = models.BigIntegerField(null=True, blank=True)
    link_clicks = models.BigIntegerField(null=True, blank=True)
    ctr = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    cpc = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    cpm = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    is_mock = models.BooleanField(default=False)
    retrieved_at = models.DateTimeField()

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=["ad_account", "campaign_external_id", "date"], name="uniq_ad_insight_day"
            )
        ]
        indexes = [models.Index(fields=["organization", "date"])]


class AdSyncRun(OrganizationOwnedModel):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        PARTIAL = "partial", "Partially succeeded"
        FAILED = "failed", "Failed"

    ad_account = models.ForeignKey(AdAccount, on_delete=models.CASCADE, related_name="sync_runs")
    trigger = models.CharField(max_length=16)  # schedule, manual, webhook, after_write
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    errors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-started_at"]
