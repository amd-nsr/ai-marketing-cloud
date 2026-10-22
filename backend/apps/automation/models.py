from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


class AutonomyMode(models.TextChoices):
    MANUAL = "manual", "Manual"
    SEMI_AUTOMATIC = "semi_automatic", "Semi-automatic"
    AUTOMATIC = "automatic", "Automatic"


class AutomationPolicy(OrganizationOwnedModel):
    """How much the system may do on its own for one organization.

    Defaults are conservative: manual mode, nothing automated. ``version`` increments on
    every change; actions record the version they were evaluated under.
    """

    mode = models.CharField(
        max_length=20, choices=AutonomyMode.choices, default=AutonomyMode.MANUAL
    )
    paused = models.BooleanField(default=False)
    paused_at = models.DateTimeField(null=True, blank=True)
    paused_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: Automatic mode only: may approved content be published without a further click?
    auto_publish_enabled = models.BooleanField(default=False)
    #: Accounts automation may publish to. Empty = none (never "all").
    allowed_accounts = models.ManyToManyField("social.SocialAccount", blank=True, related_name="+")
    #: Weekdays (0=Mon..6=Sun) and local hours automation may publish in.
    allowed_weekdays = models.JSONField(default=list, blank=True)
    window_start_hour = models.PositiveSmallIntegerField(default=8)
    window_end_hour = models.PositiveSmallIntegerField(default=20)
    timezone = models.CharField(max_length=64, default="UTC")
    max_automated_posts_per_day = models.PositiveSmallIntegerField(default=3)
    #: Semi/automatic: let the system draft routine content from the active plan.
    auto_generate_drafts = models.BooleanField(default=False)
    max_generated_drafts_per_week = models.PositiveSmallIntegerField(default=5)
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization"], name="uniq_automation_policy_per_org"),
            models.CheckConstraint(
                condition=models.Q(window_start_hour__lt=models.F("window_end_hour"))
                & models.Q(window_end_hour__lte=24),
                name="automation_window_valid",
            ),
        ]


class AutomationAction(OrganizationOwnedModel):
    """A durable record of something the system wants to do, and what the policy decided."""

    class ActionType(models.TextChoices):
        PUBLISH_CONTENT = "publish_content", "Publish content"
        GENERATE_DRAFT = "generate_draft", "Generate a draft"

    class Status(models.TextChoices):
        AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
        DEFERRED = "deferred", "Deferred"
        APPROVED = "approved", "Approved"
        EXECUTING = "executing", "Executing"
        SUCCEEDED = "succeeded", "Done"
        FAILED = "failed", "Failed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    action_type = models.CharField(max_length=24, choices=ActionType.choices)
    status = models.CharField(max_length=20, choices=Status.choices)
    workflow = models.CharField(max_length=60)  # e.g. "calendar_autopublish"
    initiated_by = models.CharField(max_length=16, default="automation")  # or "user"
    content_item = models.ForeignKey(
        "content.ContentItem", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    social_account = models.ForeignKey(
        "social.SocialAccount", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    scheduled_for = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    #: Latest policy decision and its reasons (human-readable).
    decision = models.CharField(max_length=20)
    decision_reasons = models.JSONField(default=list, blank=True)
    policy_version = models.PositiveIntegerField()
    mode_at_decision = models.CharField(max_length=20)
    idempotency_key = models.CharField(max_length=150)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True)
    publishing_job = models.ForeignKey(
        "publishing.PublishingJob",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    ai_run = models.ForeignKey(
        "ai.AIWorkflowRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"], name="uniq_automation_action_key"
            )
        ]
        indexes = [models.Index(fields=["organization", "status", "-created_at"])]
