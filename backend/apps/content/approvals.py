"""Approval workflow for content.

An approval is bound to the exact version that was submitted. Editing the content
afterwards cancels the pending request and returns the item to draft, so nothing can be
approved (or published) without a reviewer having seen that exact text.
"""

from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.core.errors import Conflict
from apps.organizations.models import Membership
from apps.organizations.roles import Perm

from .models import Approval, ContentItem

S = ContentItem.Status


@transaction.atomic
def submit_for_approval(item: ContentItem, *, actor: Any, note: str = "") -> Approval:
    from .services import set_status

    item = ContentItem.objects.select_for_update().get(pk=item.pk)
    version = item.current_version
    if version is None:
        raise Conflict("Add content before submitting it for approval.")
    if item.status not in {S.DRAFT, S.CHANGES_REQUESTED}:
        raise Conflict(f"Content that is {item.get_status_display().lower()} can't be submitted.")
    blocking = [c["message"] for c in version.checks if c.get("severity") == "error"]
    if blocking:
        raise Conflict("Fix these issues first: " + " ".join(blocking))
    try:
        with transaction.atomic():
            approval = Approval.objects.create(
                organization=item.organization,
                item=item,
                version=version,
                requested_by=actor,
                request_note=note[:500],
            )
    except IntegrityError as exc:
        raise Conflict("This content already has a pending approval request.") from exc
    set_status(item, S.IN_REVIEW, actor=actor, reason="Submitted for approval")
    from apps.notifications.services import notify_approval_requested

    transaction.on_commit(lambda: notify_approval_requested(approval))
    audit.record(
        "approval.requested",
        organization=item.organization,
        actor=actor,
        target=approval,
        metadata={"item": str(item.pk), "version": version.number},
    )
    return approval


def _lock_pending(approval: Approval) -> Approval:
    approval = Approval.objects.select_for_update().select_related("item").get(pk=approval.pk)
    if approval.status != Approval.Status.PENDING:
        raise Conflict("This approval request has already been decided or cancelled.")
    if approval.item.current_version_id != approval.version_id:
        raise Conflict("The content changed after it was submitted. Ask for a new review.")
    return approval


@transaction.atomic
def decide(
    approval: Approval, *, approver: Membership, approve: bool, comment: str = ""
) -> Approval:
    from .services import set_status

    if not approver.has_perm(Perm.CONTENT_APPROVE):
        raise Conflict("Your role can't approve content.")
    approval = _lock_pending(approval)
    if not approve and not comment.strip():
        raise Conflict("Explain what needs to change.")
    approval.status = Approval.Status.APPROVED if approve else Approval.Status.REJECTED
    approval.decided_by = approver.user
    approval.decided_at = timezone.now()
    approval.comment = comment[:2000]
    approval.save()
    set_status(
        approval.item,
        S.APPROVED if approve else S.CHANGES_REQUESTED,
        actor=approver.user,
        reason="Approved" if approve else "Changes requested",
    )
    audit.record(
        "approval.approved" if approve else "approval.rejected",
        organization=approval.organization,
        actor=approver.user,
        target=approval,
        metadata={
            "item": str(approval.item_id),
            "version": approval.version.number,
            "self_approved": approval.requested_by_id == approver.user_id,
        },
    )
    return approval


@transaction.atomic
def cancel(approval: Approval, *, actor: Any) -> Approval:
    from .services import set_status

    approval = Approval.objects.select_for_update().select_related("item").get(pk=approval.pk)
    if approval.status != Approval.Status.PENDING:
        raise Conflict("Only pending approval requests can be cancelled.")
    approval.status = Approval.Status.CANCELLED
    approval.decided_at = timezone.now()
    approval.save(update_fields=["status", "decided_at", "updated_at"])
    if approval.item.status == S.IN_REVIEW:
        set_status(approval.item, S.DRAFT, actor=actor, reason="Approval request cancelled")
    audit.record(
        "approval.cancelled", organization=approval.organization, actor=actor, target=approval
    )
    return approval


def invalidate_pending_approvals(item: ContentItem, *, actor: Any, reason: str) -> None:
    for approval in Approval.objects.select_for_update().filter(
        item=item, status=Approval.Status.PENDING
    ):
        approval.status = Approval.Status.CANCELLED
        approval.comment = reason
        approval.decided_at = timezone.now()
        approval.save(update_fields=["status", "comment", "decided_at", "updated_at"])
        audit.record(
            "approval.invalidated",
            organization=item.organization,
            actor=actor,
            target=approval,
            metadata={"reason": reason},
        )
