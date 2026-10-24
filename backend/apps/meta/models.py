import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import OrganizationOwnedModel, TimeStampedModel
from apps.social import crypto


class MetaConnection(OrganizationOwnedModel):
    """One person's Facebook Login grant, connected to one organization.

    Holds the (encrypted) long-lived user token, the permissions the person actually
    granted, and the assets (Pages, ad accounts) discovered with it. Assets become usable
    only when someone selects them; Pages are then stored as ``SocialAccount`` rows with
    their own Page token, and ad accounts as ``ads.AdAccount`` rows.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Connected"
        NEEDS_REAUTH = "needs_reauth", "Reconnect required"
        REVOKED = "revoked", "Access removed on Facebook"
        DISCONNECTED = "disconnected", "Disconnected"
        DELETED = "deleted", "Data deleted"

    meta_user_id = models.CharField(max_length=64)
    name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    is_mock = models.BooleanField(default=False)
    user_token_enc = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    granted_permissions = models.JSONField(default=list, blank=True)
    declined_permissions = models.JSONField(default=list, blank=True)
    #: Discovered assets (non-secret fields only). Page tokens are never stored here.
    available_pages = models.JSONField(default=list, blank=True)
    available_ad_accounts = models.JSONField(default=list, blank=True)
    assets_refreshed_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    expiry_warned_at = models.DateTimeField(null=True, blank=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    connected_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-connected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "meta_user_id"], name="uniq_meta_connection_per_user"
            )
        ]

    def __str__(self) -> str:
        return f"Meta: {self.name or self.meta_user_id}"

    def set_user_token(self, token: str | None) -> None:
        self.user_token_enc = crypto.encrypt(token)

    @property
    def user_token(self) -> str | None:
        return crypto.decrypt(self.user_token_enc)

    @property
    def is_usable(self) -> bool:
        if self.status != self.Status.ACTIVE or not self.user_token_enc:
            return False
        return self.token_expires_at is None or self.token_expires_at > timezone.now()


class MetaWebhookEvent(TimeStampedModel):
    """A verified webhook delivery from Meta (not tenant-owned until matched)."""

    object = models.CharField(max_length=40)
    field = models.CharField(max_length=80, blank=True)
    entry_id = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["object", "entry_id"])]


def _confirmation_code() -> str:
    return secrets.token_urlsafe(18)


class MetaDataDeletionRequest(TimeStampedModel):
    """A user's request (via Meta) to delete the data we hold about them."""

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    meta_user_id = models.CharField(max_length=64)
    confirmation_code = models.CharField(max_length=40, unique=True, default=_confirmation_code)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RECEIVED)
    completed_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)
