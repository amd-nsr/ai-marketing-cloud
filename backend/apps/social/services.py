import base64
import hashlib
import secrets
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit import services as audit
from apps.organizations.models import Organization

from .adapters.base import AccountRef, SocialError
from .adapters.registry import adapter_for
from .models import OAuthState, SocialAccount


def callback_url() -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/oauth/callback"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


def start_connection(org: Organization, *, user: Any, platform: str, mock: bool) -> str:
    """Create single-use OAuth state and return the platform's authorization URL."""
    adapter = adapter_for(platform, mock=mock)
    if not adapter.is_configured():
        raise ValidationError(
            {
                "platform": f"{adapter.capabilities.display_name} "
                "isn't configured for this environment."
            }
        )
    verifier, challenge = _pkce_pair()
    state = OAuthState.objects.create(
        organization=org,
        platform=platform,
        user=user,
        code_verifier=verifier,
        redirect_uri=callback_url(),
        mock=mock,
    )
    audit.record(
        "social.connect_started",
        organization=org,
        actor=user,
        metadata={"platform": platform, "simulation": mock},
    )
    return adapter.authorization_url(
        state=state.state, redirect_uri=state.redirect_uri, code_challenge=challenge
    )


@transaction.atomic
def complete_connection(
    *, user: Any, state: str, code: str
) -> tuple[Organization, list[SocialAccount]]:
    try:
        oauth = (
            OAuthState.objects.select_for_update().select_related("organization").get(state=state)
        )
    except OAuthState.DoesNotExist as exc:
        raise ValidationError({"state": "This connection link is invalid. Start again."}) from exc
    if oauth.used_at is not None or oauth.expires_at <= timezone.now():
        raise ValidationError({"state": "This connection link has expired. Start again."})
    if oauth.user_id != user.pk:
        raise PermissionDenied("This connection was started by someone else.")
    oauth.used_at = timezone.now()
    oauth.save(update_fields=["used_at", "updated_at"])

    adapter = adapter_for(oauth.platform, mock=oauth.mock)
    try:
        credentials = adapter.complete_authorization(
            code=code, redirect_uri=oauth.redirect_uri, code_verifier=oauth.code_verifier
        )
    except SocialError as exc:
        audit.record(
            "social.connect_failed",
            organization=oauth.organization,
            actor=user,
            metadata={"platform": oauth.platform, "error": exc.code},
        )
        raise ValidationError({"code": str(exc)}) from exc

    accounts = []
    for cred in credentials:
        account, created = SocialAccount.objects.get_or_create(
            organization=oauth.organization,
            platform=oauth.platform,
            external_id=cred.external_id,
            defaults={"name": cred.name, "is_mock": oauth.mock, "connected_by": user},
        )
        account.name = cred.name
        account.username = cred.username
        account.account_type = cred.account_type
        account.is_mock = oauth.mock
        account.scopes = list(cred.scopes)
        account.metadata = cred.metadata
        account.token_expires_at = cred.expires_at
        account.status = SocialAccount.Status.CONNECTED
        account.last_error = ""
        account.connected_by = user
        account.connected_at = timezone.now()
        account.set_tokens(cred.access_token, cred.refresh_token)
        account.save()
        accounts.append(account)
        audit.record(
            "social.account_connected" if created else "social.account_reconnected",
            organization=oauth.organization,
            actor=user,
            target=account,
            metadata={
                "platform": account.platform,
                "name": account.name,
                "simulation": account.is_mock,
            },
        )
    return oauth.organization, accounts


def disconnect(account: SocialAccount, *, actor: Any) -> None:
    from apps.publishing.services import cancel_pending_for_account

    cancelled = cancel_pending_for_account(account, actor=actor, reason="Account disconnected")
    account.status = SocialAccount.Status.DISCONNECTED
    account.set_tokens(None, None)  # tokens are destroyed, not just hidden
    account.token_expires_at = None
    account.save()
    audit.record(
        "social.account_disconnected",
        organization=account.organization,
        actor=actor,
        target=account,
        metadata={"platform": account.platform, "cancelled_jobs": cancelled},
    )


def mark_needs_reauth(account: SocialAccount, reason: str) -> None:
    account.status = SocialAccount.Status.NEEDS_REAUTH
    account.last_error = reason[:500]
    account.save(update_fields=["status", "last_error", "updated_at"])
    audit.record(
        "social.account_needs_reauth",
        organization=account.organization,
        target=account,
        system=True,
        metadata={"platform": account.platform},
    )


def account_ref(account: SocialAccount) -> AccountRef:
    token = account.access_token
    if not token:
        from .adapters.base import ReauthRequired

        raise ReauthRequired("No usable credentials for this account.")
    return AccountRef(
        external_id=account.external_id, access_token=token, metadata=dict(account.metadata)
    )
