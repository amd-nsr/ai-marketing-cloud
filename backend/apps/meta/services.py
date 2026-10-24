"""Meta connection lifecycle: authorize, discover assets, select them, revoke, delete.

Business code depends on these functions and on ``apps.ads`` / ``apps.social`` models,
never on Graph API details (those live in ``graph.py`` and ``client.py``).
"""

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.core.errors import Conflict
from apps.organizations.models import Organization
from apps.organizations.roles import Perm
from apps.social.adapters.base import ReauthRequired, SocialError
from apps.social.models import SocialAccount

from . import permissions
from .client import AccountClient, account_client
from .models import MetaConnection, MetaDataDeletionRequest

logger = logging.getLogger(__name__)
C = MetaConnection.Status


def client_for(connection: MetaConnection) -> AccountClient:
    return account_client(mock=connection.is_mock)


def _token(connection: MetaConnection) -> str:
    token = connection.user_token
    if not connection.is_usable or not token:
        raise Conflict("This Meta connection needs to be reconnected first.")
    return token


# --- Authorization --------------------------------------------------------------------------


@transaction.atomic
def complete_authorization(
    org: Organization, *, user: Any, code: str, redirect_uri: str, mock: bool
) -> MetaConnection:
    """Exchange the code, record who connected and what they granted, discover assets.
    Nothing is selected yet: the person chooses Pages and ad accounts next."""
    client = account_client(mock=mock)
    token = client.exchange_code(code=code, redirect_uri=redirect_uri)
    me = client.me(token.token)
    connection, created = MetaConnection.objects.get_or_create(
        organization=org,
        meta_user_id=me["id"],
        defaults={"is_mock": mock, "connected_by": user},
    )
    connection.name = me["name"]
    connection.is_mock = mock
    connection.status = C.ACTIVE
    connection.last_error = ""
    connection.connected_by = user
    connection.connected_at = timezone.now()
    connection.expiry_warned_at = None
    connection.token_expires_at = token.expires_at
    connection.set_user_token(token.token)
    _refresh(connection, client, token.token)
    audit.record(
        "meta.connected" if created else "meta.reconnected",
        organization=org,
        actor=user,
        target=connection,
        metadata={
            "simulation": mock,
            "granted": connection.granted_permissions,
            "declined": connection.declined_permissions,
            "pages": len(connection.available_pages),
            "ad_accounts": len(connection.available_ad_accounts),
        },
    )
    return connection


def _refresh(connection: MetaConnection, client: AccountClient, token: str) -> None:
    granted, declined = client.permissions(token)
    connection.granted_permissions, connection.declined_permissions = granted, declined
    # List what the person can see even if a feature is incomplete, so the UI can show
    # what reconnecting with the missing permissions would enable.
    pages = [p.public() for p in client.pages(token)] if "pages_show_list" in granted else []
    ad_accounts = (
        [a.public() for a in client.ad_accounts(token)]
        if settings.META_ADS_ENABLED and "ads_read" in granted
        else []
    )
    connection.available_pages, connection.available_ad_accounts = pages, ad_accounts
    connection.assets_refreshed_at = connection.last_checked_at = timezone.now()
    connection.save()


def refresh_connection(connection: MetaConnection, *, actor: Any = None) -> MetaConnection:
    """Re-read granted permissions and available assets."""
    token = _token(connection)
    try:
        _refresh(connection, client_for(connection), token)
    except ReauthRequired as exc:
        mark_needs_reauth(connection, str(exc))
        raise Conflict("Facebook no longer accepts this login. Reconnect with Meta.") from exc
    except SocialError as exc:
        connection.last_error = str(exc)[:500]
        connection.save(update_fields=["last_error", "updated_at"])
        raise Conflict(f"Couldn't refresh from Meta: {exc}") from exc
    _apply_permission_changes(connection)
    if actor is not None:
        audit.record(
            "meta.refreshed", organization=connection.organization, actor=actor, target=connection
        )
    return connection


def _apply_permission_changes(connection: MetaConnection) -> None:
    """If a feature's permissions were removed, the assets that need them stop working."""
    granted = connection.granted_permissions
    if not permissions.has_feature(granted, permissions.PAGES_FEATURE):
        for page in connection.pages.filter(status=SocialAccount.Status.CONNECTED):
            from apps.social.services import mark_needs_reauth as page_needs_reauth

            page_needs_reauth(page, "Publishing permission was removed on Facebook.")
    if not permissions.has_feature(granted, permissions.ADS_READ_FEATURE):
        from apps.ads.services import mark_accounts_needing_reauth

        mark_accounts_needing_reauth(connection, "Ads permission was removed on Facebook.")


# --- Selecting assets -----------------------------------------------------------------------


@transaction.atomic
def connect_pages(
    connection: MetaConnection, *, page_ids: list[str], actor: Any
) -> list[SocialAccount]:
    if not permissions.has_feature(connection.granted_permissions, permissions.PAGES_FEATURE):
        raise Conflict("Publishing permissions weren't granted. Reconnect and allow them.")
    token = _token(connection)
    client = client_for(connection)
    try:
        available = {p.id: p for p in client.pages(token, with_tokens=True)}
    except ReauthRequired as exc:
        mark_needs_reauth(connection, str(exc))
        raise Conflict("Facebook no longer accepts this login. Reconnect with Meta.") from exc
    except SocialError as exc:
        raise Conflict(f"Couldn't load your Pages from Meta: {exc}") from exc
    unknown = [pid for pid in page_ids if pid not in available]
    if unknown:
        raise ValidationError({"page_ids": "Some Pages aren't available to this login."})
    blocked = [available[pid].name for pid in page_ids if not available[pid].can_publish]
    if blocked:
        raise ValidationError(
            {"page_ids": f"You can't publish to: {', '.join(blocked)} (no content access)."}
        )
    org = connection.organization
    accounts = []
    for pid in page_ids:
        page = available[pid]
        account, created = SocialAccount.objects.get_or_create(
            organization=org,
            platform="facebook",
            external_id=page.id,
            defaults={"name": page.name, "is_mock": connection.is_mock, "connected_by": actor},
        )
        account.name = page.name
        account.account_type = "facebook_page"
        account.is_mock = connection.is_mock
        account.scopes = list(permissions.FEATURE_PERMISSIONS[permissions.PAGES_FEATURE])
        account.metadata = {"category": page.category, "link": page.link}
        account.token_expires_at = None  # Page tokens from a long-lived user token don't expire
        account.status = SocialAccount.Status.CONNECTED
        account.last_error = ""
        account.connected_by = actor
        account.connected_at = timezone.now()
        account.meta_connection = connection
        account.set_tokens(page.access_token)
        account.save()
        accounts.append(account)
        audit.record(
            "social.account_connected" if created else "social.account_reconnected",
            organization=org,
            actor=actor,
            target=account,
            metadata={"platform": "facebook", "name": page.name, "simulation": account.is_mock},
        )
    connection.available_pages = [p.public() for p in available.values()]
    connection.save(update_fields=["available_pages", "updated_at"])
    return accounts


# --- Disconnect, revocation, deletion -------------------------------------------------------


def mark_needs_reauth(connection: MetaConnection, reason: str) -> None:
    if connection.status != C.ACTIVE:
        return
    connection.status = C.NEEDS_REAUTH
    connection.last_error = reason[:500]
    connection.save(update_fields=["status", "last_error", "updated_at"])
    from apps.ads.services import mark_accounts_needing_reauth
    from apps.notifications.models import Notification
    from apps.notifications.services import notify_members_with

    mark_accounts_needing_reauth(connection, reason)
    notify_members_with(
        connection.organization,
        Perm.SOCIAL_MANAGE,
        kind=Notification.Kind.ACCOUNT_REAUTH,
        title="Reconnect your Meta account",
        body=reason,
        link=f"/o/{connection.organization_id}/accounts",
    )
    audit.record(
        "meta.needs_reauth",
        organization=connection.organization,
        target=connection,
        system=True,
        metadata={"reason": reason[:200]},
    )


def _detach_assets(connection: MetaConnection, *, actor: Any, reason: str) -> dict[str, int]:
    from apps.ads.services import disconnect_ad_accounts_for
    from apps.social.services import disconnect as disconnect_page

    pages = 0
    for page in connection.pages.exclude(status=SocialAccount.Status.DISCONNECTED):
        disconnect_page(page, actor=actor)
        pages += 1
    ad_accounts = disconnect_ad_accounts_for(connection, actor=actor, reason=reason)
    return {"pages": pages, "ad_accounts": ad_accounts}


def disconnect(connection: MetaConnection, *, actor: Any, revoke: bool = True) -> dict[str, Any]:
    """Disconnect a Meta login and everything selected through it.

    With ``revoke``, also removes the app's permissions on Facebook (best effort: the
    local disconnect always completes, and a failed revoke is reported)."""
    revoked = False
    revoke_error = ""
    if revoke and connection.user_token_enc and connection.status == C.ACTIVE:
        try:
            client_for(connection).revoke(connection.user_token or "")
            revoked = True
        except SocialError as exc:
            revoke_error = str(exc)[:200]
            logger.warning("Meta revoke failed", extra={"connection": str(connection.pk)})
    with transaction.atomic():
        detached = _detach_assets(connection, actor=actor, reason="Meta account disconnected")
        connection.status = C.DISCONNECTED
        connection.set_user_token(None)
        connection.token_expires_at = None
        connection.available_pages, connection.available_ad_accounts = [], []
        connection.save()
    audit.record(
        "meta.disconnected",
        organization=connection.organization,
        actor=actor,
        target=connection,
        metadata={**detached, "revoked_on_meta": revoked, "revoke_error": revoke_error},
    )
    return {**detached, "revoked_on_meta": revoked, "revoke_error": revoke_error}


def handle_deauthorization(meta_user_id: str) -> int:
    """Meta tells us a person removed the app: stop using their grants everywhere."""
    count = 0
    for connection in MetaConnection.objects.filter(meta_user_id=meta_user_id).exclude(
        status__in=[C.DISCONNECTED, C.DELETED]
    ):
        with transaction.atomic():
            _detach_assets(connection, actor=None, reason="App removed on Facebook")
            connection.status = C.REVOKED
            connection.set_user_token(None)
            connection.save()
        audit.record(
            "meta.deauthorized",
            organization=connection.organization,
            target=connection,
            system=True,
        )
        from apps.notifications.models import Notification
        from apps.notifications.services import notify_members_with

        notify_members_with(
            connection.organization,
            Perm.SOCIAL_MANAGE,
            kind=Notification.Kind.ACCOUNT_REAUTH,
            title="Meta access was removed",
            body=f"{connection.name or 'A team member'} removed this app on Facebook. "
            "Their Pages and ad accounts were disconnected.",
            link=f"/o/{connection.organization_id}/accounts",
        )
        count += 1
    return count


def handle_data_deletion(meta_user_id: str) -> MetaDataDeletionRequest:
    """Delete the data obtained from Meta through this person's grants."""
    request = MetaDataDeletionRequest.objects.create(meta_user_id=meta_user_id)
    summary: dict[str, int] = {"connections": 0, "pages": 0, "metric_snapshots": 0}
    try:
        handle_deauthorization(meta_user_id)
        from apps.ads.services import purge_meta_data
        from apps.analytics.models import MetricSnapshot

        for connection in MetaConnection.objects.filter(meta_user_id=meta_user_id):
            with transaction.atomic():
                page_ids = list(connection.pages.values_list("pk", flat=True))
                deleted, _ = MetricSnapshot.objects.filter(
                    published_post__social_account_id__in=page_ids
                ).delete()
                summary["metric_snapshots"] += deleted
                summary["pages"] += len(page_ids)
                for key, n in purge_meta_data(connection).items():
                    summary[key] = summary.get(key, 0) + n
                connection.status = C.DELETED
                connection.name = ""
                connection.granted_permissions = connection.declined_permissions = []
                connection.available_pages = connection.available_ad_accounts = []
                connection.set_user_token(None)
                connection.save()
                summary["connections"] += 1
                audit.record(
                    "meta.data_deleted",
                    organization=connection.organization,
                    target=connection,
                    system=True,
                    metadata={"confirmation_code": request.confirmation_code},
                )
        request.status = MetaDataDeletionRequest.Status.COMPLETED
    except Exception:
        logger.exception("Meta data deletion failed", extra={"request": str(request.pk)})
        request.status = MetaDataDeletionRequest.Status.FAILED
    request.summary = summary
    request.completed_at = timezone.now()
    request.save()
    return request


# --- Periodic checks ------------------------------------------------------------------------


def check_connections() -> dict[str, int]:
    """Daily: warn before user tokens expire, mark expired ones, re-read permissions."""
    from apps.notifications.models import Notification
    from apps.notifications.services import notify_members_with

    now = timezone.now()
    counts = {"checked": 0, "expiring": 0, "expired": 0, "errors": 0}
    for connection in MetaConnection.objects.filter(status=C.ACTIVE):
        counts["checked"] += 1
        expires = connection.token_expires_at
        if expires and expires <= now:
            mark_needs_reauth(connection, "The Meta login expired. Reconnect to keep syncing.")
            counts["expired"] += 1
            continue
        warn_at = now + timedelta(days=settings.META_TOKEN_WARNING_DAYS)
        if expires and expires <= warn_at and connection.expiry_warned_at is None:
            notify_members_with(
                connection.organization,
                Perm.SOCIAL_MANAGE,
                kind=Notification.Kind.ACCOUNT_REAUTH,
                title="Your Meta login expires soon",
                body=f"Reconnect before {expires:%Y-%m-%d} to keep ad syncing working.",
                link=f"/o/{connection.organization_id}/accounts",
            )
            connection.expiry_warned_at = now
            connection.save(update_fields=["expiry_warned_at", "updated_at"])
            counts["expiring"] += 1
        try:
            refresh_connection(connection)
        except Conflict:
            counts["errors"] += 1
    return counts
