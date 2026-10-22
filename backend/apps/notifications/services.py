from typing import Any

from apps.organizations.models import Membership
from apps.organizations.roles import Perm

from .models import Notification


def notify_members_with(
    org: Any, perm: str, *, kind: str, title: str, body: str = "", link: str = "", also: Any = None
) -> int:
    users = {
        m.user
        for m in Membership.objects.filter(organization=org).select_related("user")
        if m.has_perm(perm)
    }
    if also is not None and getattr(also, "pk", None):
        users.add(also)
    Notification.objects.bulk_create(
        [
            Notification(
                organization=org,
                user=u,
                kind=kind,
                title=title[:200],
                body=body[:1000],
                link=link[:300],
            )
            for u in users
        ]
    )
    return len(users)


def notify_publishing_failed(job: Any) -> None:
    item = job.content_item
    notify_members_with(
        job.organization,
        Perm.PUBLISHING_PUBLISH,
        kind=Notification.Kind.PUBLISHING_FAILED,
        title=f"Couldn't publish “{item.title[:80]}”",
        body=job.error_message,
        link=f"/o/{job.organization_id}/publishing",
        also=job.created_by,
    )


def notify_approval_requested(approval: Any) -> None:
    notify_members_with(
        approval.organization,
        Perm.CONTENT_APPROVE,
        kind=Notification.Kind.APPROVAL_REQUESTED,
        title=f"Review requested: “{approval.item.title[:80]}”",
        link=f"/o/{approval.organization_id}/approvals",
    )
