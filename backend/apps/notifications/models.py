from django.conf import settings
from django.db import models

from apps.core.models import OrganizationOwnedModel


class Notification(OrganizationOwnedModel):
    """An in-app notification for one user."""

    class Kind(models.TextChoices):
        PUBLISHING_FAILED = "publishing_failed", "Publishing failed"
        ACCOUNT_REAUTH = "account_reauth", "Account needs reconnecting"
        APPROVAL_REQUESTED = "approval_requested", "Approval requested"
        AUTOMATION = "automation", "Automation"
        RECOMMENDATION = "recommendation", "Recommendation"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=1000, blank=True)
    link = models.CharField(max_length=300, blank=True)  # frontend path
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "organization", "read_at"])]
