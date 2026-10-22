import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit import services as audit
from apps.core.errors import Conflict

from .models import Invitation, Membership, Organization
from .roles import Role
from .signals import organization_created

logger = logging.getLogger(__name__)


def _unique_slug(name: str) -> str:
    base = slugify(name)[:120] or "org"
    slug, n = base, 1
    while Organization.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


@transaction.atomic
def create_organization(
    *, user: Any, name: str, request: HttpRequest | None = None
) -> Organization:
    org = Organization.objects.create(name=name.strip(), slug=_unique_slug(name), created_by=user)
    Membership.objects.create(organization=org, user=user, role=Role.OWNER)
    audit.record("organization.created", organization=org, actor=user, target=org, request=request)
    organization_created.send(sender=Organization, organization=org, owner=user)
    return org


def update_organization(
    org: Organization, *, actor: Any, name: str, request: HttpRequest | None = None
) -> Organization:
    old = org.name
    org.name = name.strip()
    org.save(update_fields=["name", "updated_at"])
    audit.record(
        "organization.updated",
        organization=org,
        actor=actor,
        target=org,
        metadata={"name": {"from": old, "to": org.name}},
        request=request,
    )
    return org


def _owner_count(org: Organization) -> int:
    return Membership.objects.filter(organization=org, role=Role.OWNER).count()


def _guard_owner_change(actor: Membership, target_role: str, new_role: str | None) -> None:
    if Role.OWNER in (target_role, new_role) and actor.role != Role.OWNER:
        raise PermissionDenied("Only an owner can grant or remove the owner role.")


@transaction.atomic
def change_role(
    *, actor: Membership, membership: Membership, role: str, request: HttpRequest | None = None
) -> Membership:
    membership = Membership.objects.select_for_update().get(pk=membership.pk)
    if membership.role == role:
        return membership
    _guard_owner_change(actor, membership.role, role)
    if membership.role == Role.OWNER and _owner_count(membership.organization) <= 1:
        raise Conflict("An organization must keep at least one owner.")
    old = membership.role
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    audit.record(
        "member.role_changed",
        organization=membership.organization,
        actor=actor.user,
        target=membership,
        metadata={"user_id": str(membership.user_id), "from": old, "to": role},
        request=request,
    )
    return membership


@transaction.atomic
def remove_member(
    *, actor: Membership, membership: Membership, request: HttpRequest | None = None
) -> None:
    membership = Membership.objects.select_for_update().get(pk=membership.pk)
    is_self = membership.user_id == actor.user_id
    if not is_self:
        _guard_owner_change(actor, membership.role, None)
    if membership.role == Role.OWNER and _owner_count(membership.organization) <= 1:
        raise Conflict("An organization must keep at least one owner.")
    audit.record(
        "member.left" if is_self else "member.removed",
        organization=membership.organization,
        actor=actor.user,
        target=membership,
        metadata={"user_id": str(membership.user_id), "role": membership.role},
        request=request,
    )
    membership.delete()


def invitation_url(invitation: Invitation) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/invitations/accept?token={invitation.token}"


@transaction.atomic
def invite_member(
    *,
    actor: Membership,
    email: str,
    role: str,
    request: HttpRequest | None = None,
) -> Invitation:
    org = actor.organization
    email = email.strip().lower()
    _guard_owner_change(actor, role, role)
    if Membership.objects.filter(organization=org, user__email__iexact=email).exists():
        raise Conflict("This person is already a member of the organization.")
    Invitation.objects.filter(
        organization=org,
        email__iexact=email,
        status=Invitation.Status.PENDING,
        expires_at__lte=timezone.now(),
    ).update(status=Invitation.Status.REVOKED)
    try:
        with transaction.atomic():
            invitation = Invitation.objects.create(
                organization=org, email=email, role=role, invited_by=actor.user
            )
    except IntegrityError as exc:
        raise Conflict("A pending invitation already exists for this email.") from exc
    audit.record(
        "invitation.created",
        organization=org,
        actor=actor.user,
        target=invitation,
        metadata={"email": email, "role": role},
        request=request,
    )
    transaction.on_commit(lambda: _send_invitation_email(invitation))
    return invitation


def _send_invitation_email(invitation: Invitation) -> None:
    try:
        send_mail(
            subject=f"You're invited to {invitation.organization.name} on AI Marketing Cloud",
            message=(
                f"You've been invited to join {invitation.organization.name} as "
                f"{invitation.get_role_display()}.\n\nAccept the invitation: "
                f"{invitation_url(invitation)}\n\nThis link expires in 7 days."
            ),
            from_email=None,
            recipient_list=[invitation.email],
        )
    except Exception:
        logger.exception(
            "Failed to send invitation email", extra={"invitation": str(invitation.pk)}
        )


def revoke_invitation(
    *, actor: Membership, invitation: Invitation, request: HttpRequest | None = None
) -> None:
    if invitation.status != Invitation.Status.PENDING:
        raise Conflict("Only pending invitations can be revoked.")
    invitation.status = Invitation.Status.REVOKED
    invitation.save(update_fields=["status", "updated_at"])
    audit.record(
        "invitation.revoked",
        organization=invitation.organization,
        actor=actor.user,
        target=invitation,
        request=request,
    )


@transaction.atomic
def accept_invitation(*, user: Any, token: str, request: HttpRequest | None = None) -> Membership:
    try:
        invitation = Invitation.objects.select_for_update().get(token=token)
    except Invitation.DoesNotExist as exc:
        raise ValidationError({"token": "This invitation is invalid."}) from exc
    if invitation.status != Invitation.Status.PENDING or invitation.is_expired:
        raise ValidationError({"token": "This invitation is no longer valid."})
    if invitation.email.lower() != user.email.lower():
        raise PermissionDenied("This invitation was sent to a different email address.")
    membership, created = Membership.objects.get_or_create(
        organization=invitation.organization, user=user, defaults={"role": invitation.role}
    )
    invitation.status = Invitation.Status.ACCEPTED
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["status", "accepted_at", "updated_at"])
    audit.record(
        "invitation.accepted",
        organization=invitation.organization,
        actor=user,
        target=invitation,
        metadata={"role": membership.role, "already_member": not created},
        request=request,
    )
    return membership
