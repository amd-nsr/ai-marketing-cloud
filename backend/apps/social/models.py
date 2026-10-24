import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import OrganizationOwnedModel

from . import crypto


class SocialPlatform(models.TextChoices):
    """Platforms with a social integration (a subset of the content model's channels)."""

    INSTAGRAM = "instagram", "Instagram"
    FACEBOOK = "facebook", "Facebook"
    TIKTOK = "tiktok", "TikTok"


class SocialAccount(OrganizationOwnedModel):
    """A connected publishing destination (e.g. a Facebook Page)."""

    class Status(models.TextChoices):
        CONNECTED = "connected", "Connected"
        NEEDS_REAUTH = "needs_reauth", "Reconnect required"
        DISCONNECTED = "disconnected", "Disconnected"

    platform = models.CharField(max_length=16, choices=SocialPlatform.choices)
    external_id = models.CharField(max_length=120)
    name = models.CharField(max_length=200)
    username = models.CharField(max_length=200, blank=True)
    account_type = models.CharField(max_length=60, blank=True)  # e.g. "facebook_page"
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CONNECTED)
    #: Simulation account from the mock adapter; never contacts a real platform.
    is_mock = models.BooleanField(default=False)
    access_token_enc = models.TextField(blank=True)
    refresh_token_enc = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # non-secret platform details
    last_error = models.CharField(max_length=500, blank=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    connected_at = models.DateTimeField(default=timezone.now)
    #: The Meta login this Page was selected from (Facebook only).
    meta_connection = models.ForeignKey(
        "meta.MetaConnection",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pages",
    )

    class Meta:
        ordering = ["platform", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "platform", "external_id"], name="uniq_social_account"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_platform_display()}: {self.name}"

    # Tokens are only reachable through these accessors.
    def set_tokens(self, access: str | None, refresh: str | None = None) -> None:
        self.access_token_enc = crypto.encrypt(access)
        self.refresh_token_enc = crypto.encrypt(refresh)

    @property
    def access_token(self) -> str | None:
        return crypto.decrypt(self.access_token_enc)

    @property
    def refresh_token(self) -> str | None:
        return crypto.decrypt(self.refresh_token_enc)

    @property
    def is_usable(self) -> bool:
        if self.status != self.Status.CONNECTED:
            return False
        return self.token_expires_at is None or self.token_expires_at > timezone.now()


def _state() -> str:
    return secrets.token_urlsafe(32)


def _expiry() -> datetime:
    return timezone.now() + timedelta(minutes=15)


class OAuthState(OrganizationOwnedModel):
    """Single-use CSRF state (and PKCE verifier) for one authorization attempt."""

    platform = models.CharField(max_length=16, choices=SocialPlatform.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    state = models.CharField(max_length=64, unique=True, default=_state)
    code_verifier = models.CharField(max_length=128, blank=True)
    redirect_uri = models.CharField(max_length=500)
    mock = models.BooleanField(default=False)
    expires_at = models.DateTimeField(default=_expiry)
    used_at = models.DateTimeField(null=True, blank=True)
