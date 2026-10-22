import uuid
from pathlib import PurePosixPath
from typing import Any

from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel

from .presets import INDUSTRY_CHOICES


class BusinessProfile(OrganizationOwnedModel):
    """Facts the business owner provides about their business (one per organization).

    Everything here is user-supplied and editable; AI features treat it as the
    authoritative business facts and must not invent others.
    """

    business_name = models.CharField(max_length=160, blank=True)
    industry = models.CharField(max_length=40, choices=INDUSTRY_CHOICES, blank=True)
    website = models.URLField(blank=True)
    description = models.TextField(blank=True, max_length=4000)
    products_services = models.JSONField(default=list, blank=True)  # [{name, description}]
    location = models.CharField(max_length=200, blank=True)
    service_area = models.CharField(max_length=300, blank=True)
    goals = models.JSONField(default=list, blank=True)  # goal keys or free text
    preferred_platforms = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)  # e.g. ["en", "ar"]
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization"], name="uniq_business_profile_per_org")
        ]


class BrandGuideline(OrganizationOwnedModel):
    """How the brand communicates, and what it must never say (one per organization)."""

    tone = models.JSONField(default=list, blank=True)  # adjectives, e.g. ["warm", "expert"]
    voice_description = models.TextField(blank=True, max_length=2000)
    do_list = models.JSONField(default=list, blank=True)
    dont_list = models.JSONField(default=list, blank=True)
    restricted_claims = models.JSONField(default=list, blank=True)
    example_posts = models.JSONField(default=list, blank=True)
    colors = models.JSONField(default=list, blank=True)  # hex strings
    fonts = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization"], name="uniq_brand_guideline_per_org")
        ]


class TargetAudience(OrganizationOwnedModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=2000)
    age_range = models.CharField(max_length=40, blank=True)
    locations = models.CharField(max_length=200, blank=True)
    interests = models.JSONField(default=list, blank=True)
    pain_points = models.JSONField(default=list, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "created_at"]
        indexes = [models.Index(fields=["organization", "created_at"])]


def brand_asset_path(instance: "BrandAsset", filename: str) -> str:
    # Never use the client's filename in the storage path.
    ext = PurePosixPath(filename).suffix.lower()
    return f"orgs/{instance.organization_id}/brand/{uuid.uuid4().hex}{ext}"


class BrandAsset(OrganizationOwnedModel):
    class Kind(models.TextChoices):
        LOGO = "logo", "Logo"
        IMAGE = "image", "Approved image"
        OTHER = "other", "Other"

    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.IMAGE)
    title = models.CharField(max_length=160, blank=True)
    file = models.FileField(upload_to=brand_asset_path, max_length=300)
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField()
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "kind"])]

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        storage, name = self.file.storage, self.file.name
        result = super().delete(*args, **kwargs)
        if name:
            storage.delete(name)
        return result
