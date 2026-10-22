import uuid
from pathlib import PurePosixPath
from typing import Any

from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


class Platform(models.TextChoices):
    INSTAGRAM = "instagram", "Instagram"
    FACEBOOK = "facebook", "Facebook"
    TIKTOK = "tiktok", "TikTok"


class Format(models.TextChoices):
    POST = "post", "Post"
    CAROUSEL = "carousel", "Carousel"
    REEL = "reel", "Reel"
    STORY = "story", "Story"
    SHORT_VIDEO = "short_video", "Short video"


class ContentItem(OrganizationOwnedModel):
    """A piece of content for one platform. Its text lives in immutable versions."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "Awaiting approval"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"
        APPROVED = "approved", "Approved"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=200)
    platform = models.CharField(max_length=16, choices=Platform.choices)
    format = models.CharField(max_length=16, choices=Format.choices, default=Format.POST)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    campaign = models.ForeignKey(
        "marketing.Campaign",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="content_items",
    )
    brief = models.TextField(blank=True, max_length=2000)
    current_version = models.ForeignKey(
        "ContentVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: Intended publication time (planning). Actual publishing is driven by publishing jobs.
    planned_for = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "planned_for"]),
            models.Index(fields=["organization", "campaign"]),
        ]

    def __str__(self) -> str:
        return self.title


class ContentVersion(OrganizationOwnedModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Written by the team"
        AI = "ai", "AI-generated"
        AI_EDITED = "ai_edited", "AI-generated, edited"

    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    headline = models.CharField(max_length=200, blank=True)
    hook = models.CharField(max_length=300, blank=True)
    caption = models.TextField(blank=True, max_length=10000)
    cta = models.CharField(max_length=200, blank=True)
    hashtags = models.JSONField(default=list, blank=True)
    script = models.TextField(blank=True, max_length=10000)
    slides = models.JSONField(default=list, blank=True)  # [{title, body}]
    creative_brief = models.TextField(blank=True, max_length=4000)
    alt_text = models.CharField(max_length=1000, blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    ai_run = models.ForeignKey(
        "ai.AIWorkflowRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    ai_model = models.CharField(max_length=80, blank=True)
    is_mock = models.BooleanField(default=False)
    #: Platform/brand check results at save time: [{code, severity, message}]
    checks = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["item", "number"], name="uniq_content_version_number"),
        ]

    @property
    def has_blocking_issues(self) -> bool:
        return any(c.get("severity") == "error" for c in self.checks)


def content_asset_path(instance: "ContentAsset", filename: str) -> str:
    ext = PurePosixPath(filename).suffix.lower()
    return f"orgs/{instance.organization_id}/content/{uuid.uuid4().hex}{ext}"


class ContentAsset(OrganizationOwnedModel):
    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="assets")
    file = models.FileField(upload_to=content_asset_path, max_length=300)
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField()
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64)
    position = models.PositiveSmallIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["position", "created_at"]

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        storage, name = self.file.storage, self.file.name
        result = super().delete(*args, **kwargs)
        if name:
            storage.delete(name)
        return result


class Approval(OrganizationOwnedModel):
    """A request to approve one specific version of a content item."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Changes requested"
        CANCELLED = "cancelled", "Cancelled"

    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="approvals")
    version = models.ForeignKey(ContentVersion, on_delete=models.CASCADE, related_name="approvals")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    request_note = models.CharField(max_length=500, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["item"],
                condition=models.Q(status="pending"),
                name="uniq_pending_approval_per_item",
            )
        ]
        indexes = [models.Index(fields=["organization", "status", "-created_at"])]
