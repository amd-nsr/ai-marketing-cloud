import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """UUID primary key plus creation/update timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OrganizationOwnedModel(TimeStampedModel):
    """Base for every tenant-scoped record. Queries must always filter by organization."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        abstract = True
