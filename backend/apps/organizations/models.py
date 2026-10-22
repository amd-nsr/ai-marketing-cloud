import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.core.models import TimeStampedModel

from .roles import Role, permissions_for


class Organization(TimeStampedModel):
    """A tenant. Every customer-owned record belongs to exactly one organization."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self) -> str:
        return self.name


class Membership(TimeStampedModel):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="uniq_membership"),
        ]
        indexes = [models.Index(fields=["user", "organization"])]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.organization_id} ({self.role})"

    @property
    def permissions(self) -> frozenset[str]:
        return permissions_for(self.role)

    def has_perm(self, perm: str) -> bool:
        return perm in self.permissions


def _invitation_token() -> str:
    return secrets.token_urlsafe(32)


def _invitation_expiry() -> datetime:
    return timezone.now() + timedelta(days=7)


class Invitation(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField()
    role = models.CharField(max_length=16, choices=Role.choices)
    token = models.CharField(max_length=64, unique=True, default=_invitation_token)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    expires_at = models.DateTimeField(default=_invitation_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "organization",
                Lower("email"),
                condition=models.Q(status="pending"),
                name="uniq_pending_invitation_per_email",
            ),
        ]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at
