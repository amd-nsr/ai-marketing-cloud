"""Shared contract for social platform integrations.

Adapters implement only what the platform actually supports and describe it in
``PlatformCapabilities``; the UI and services consult capabilities instead of assuming
parity. Platform errors are normalized into ``SocialError`` subclasses whose flags tell
the publishing engine whether to retry, ask for reconnection, or reconcile.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class PlatformCapabilities:
    platform: str
    display_name: str
    #: Formats this integration can publish (subset of the content model's formats).
    publish_formats: frozenset[str]
    #: Formats that cannot be published without media.
    media_required_formats: frozenset[str]
    max_images: int
    supports_text_only: bool
    supports_metrics: bool
    #: Human-readable limitations shown in the UI.
    notes: tuple[str, ...] = ()
    #: Image types the platform accepts (None = any type our uploads allow).
    image_types: frozenset[str] | None = None
    #: The platform fetches media by URL, so storage must serve public (signed) URLs.
    requires_public_media_url: bool = False


@dataclass(frozen=True)
class AccountCredentials:
    """One publishable account returned by an authorization flow."""

    external_id: str
    name: str
    username: str
    account_type: str
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scopes: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaFile:
    content: bytes
    content_type: str
    filename: str
    #: Short-lived public URL when storage provides one (required by some platforms).
    public_url: str | None = None


@dataclass(frozen=True)
class PublishRequest:
    format: str
    text: str
    media: tuple[MediaFile, ...] = ()
    alt_text: str = ""
    link: str = ""


@dataclass(frozen=True)
class PublishResult:
    external_post_id: str
    permalink: str = ""
    request_id: str = ""
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountRef:
    """What an adapter needs to act on a connected account (decrypted at call time)."""

    external_id: str
    access_token: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class MetricValue:
    key: str
    value: float | None  # None = not reported by the platform (never coerced to 0)
    unit: str = "count"
    period: str = "lifetime"


# --- Normalized errors --------------------------------------------------------------


class SocialError(Exception):
    code = "platform_error"
    retryable = False
    needs_reauth = False
    #: The request may have reached the platform; the outcome is unknown.
    uncertain = False

    def __init__(self, message: str = "", *, request_id: str = "") -> None:
        super().__init__(message or self.code)
        self.request_id = request_id


class NotConfigured(SocialError):
    code = "integration_not_configured"


class AuthorizationFailed(SocialError):
    code = "authorization_failed"


class ReauthRequired(SocialError):
    code = "reauth_required"
    needs_reauth = True


class PermissionMissing(ReauthRequired):
    """A required permission was not granted or was removed; reconnecting can fix it."""

    code = "permission_missing"


class RateLimited(SocialError):
    code = "rate_limited"
    retryable = True

    def __init__(
        self, message: str = "", *, request_id: str = "", retry_after_seconds: int | None = None
    ) -> None:
        super().__init__(message, request_id=request_id)
        self.retry_after_seconds = retry_after_seconds


class TransientError(SocialError):
    code = "platform_unavailable"
    retryable = True


class ContentRejected(SocialError):
    code = "content_rejected"


class UncertainOutcome(SocialError):
    code = "outcome_unknown"
    uncertain = True


class Unsupported(SocialError):
    code = "unsupported"


class SocialAdapter(Protocol):
    platform: str
    is_mock: bool
    capabilities: PlatformCapabilities

    def is_configured(self) -> bool: ...

    def authorization_url(self, *, state: str, redirect_uri: str, code_challenge: str) -> str: ...

    def complete_authorization(
        self, *, code: str, redirect_uri: str, code_verifier: str
    ) -> list[AccountCredentials]: ...

    def publish(self, account: AccountRef, request: PublishRequest) -> PublishResult: ...

    def find_recent_post(
        self, account: AccountRef, *, text: str, since: datetime
    ) -> PublishResult | None: ...

    def fetch_post_metrics(
        self, account: AccountRef, external_post_id: str
    ) -> list[MetricValue]: ...
