from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


class MarketingPlan(OrganizationOwnedModel):
    """An immutable version of the organization's marketing plan.

    Editing or regenerating creates a new version; history is never overwritten.
    At most one version per organization is ``active``.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    class Source(models.TextChoices):
        AI = "ai", "AI-generated"
        AI_EDITED = "ai_edited", "AI-generated, edited"
        MANUAL = "manual", "Written by the team"

    version = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    source = models.CharField(max_length=16, choices=Source.choices)
    #: Validated ``MarketingPlanOutput`` JSON.
    content = models.JSONField()
    horizon_weeks = models.PositiveSmallIntegerField(default=4)
    instructions = models.TextField(blank=True, max_length=2000)
    #: Automated checks run on save (restricted claims, guarantee language, platform fixes).
    quality_warnings = models.JSONField(default=list, blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="revisions"
    )
    generation_run = models.ForeignKey(
        "ai.AIWorkflowRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    ai_model = models.CharField(max_length=80, blank=True)
    is_mock = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "version"], name="uniq_plan_version"),
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(status="active"),
                name="uniq_active_plan_per_org",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} (v{self.version})"


class Campaign(OrganizationOwnedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=160)
    objective = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True, max_length=4000)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNED)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    platforms = models.JSONField(default=list, blank=True)
    key_messages = models.JSONField(default=list, blank=True)
    plan = models.ForeignKey(
        MarketingPlan, null=True, blank=True, on_delete=models.SET_NULL, related_name="campaigns"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__isnull=True)
                | models.Q(start_date__isnull=True)
                | models.Q(end_date__gte=models.F("start_date")),
                name="campaign_end_after_start",
            )
        ]

    def __str__(self) -> str:
        return self.name
