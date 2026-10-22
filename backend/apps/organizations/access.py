from typing import Any
from uuid import UUID

from rest_framework.exceptions import NotFound, PermissionDenied

from .models import Membership


def resolve_membership(user: Any, org_id: UUID | str) -> Membership:
    """Return the caller's membership in ``org_id``.

    Raises NotFound (not PermissionDenied) for non-members so the API never confirms
    that another tenant's organization exists.
    """
    if not getattr(user, "is_authenticated", False):
        raise NotFound()
    try:
        return Membership.objects.select_related("organization").get(
            user=user, organization_id=org_id
        )
    except (Membership.DoesNotExist, ValueError) as exc:
        raise NotFound() from exc


def require_perm(membership: Membership, perm: str) -> None:
    if not membership.has_perm(perm):
        raise PermissionDenied(f"Your role does not allow this action ({perm}).")
