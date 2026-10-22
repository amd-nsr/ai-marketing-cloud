"""Building blocks for organization-scoped API endpoints.

Every tenant-scoped endpoint lives under ``/api/v1/orgs/<org_id>/`` and uses
``OrganizationScopedMixin``: membership is resolved from the URL on every request,
the required permission is checked, and querysets are filtered to the organization.
"""

from typing import Any, ClassVar

from django.db import models
from rest_framework import mixins, serializers, viewsets
from rest_framework.request import Request
from rest_framework.views import APIView

from .access import require_perm, resolve_membership
from .models import Membership, Organization


class OrganizationScopedMixin(APIView):
    #: Permission for safe methods (GET/HEAD/OPTIONS).
    read_permission: ClassVar[str | None] = None
    #: Permission for unsafe methods.
    write_permission: ClassVar[str | None] = None
    #: Per-action overrides, e.g. {"approve": Perm.CONTENT_APPROVE}.
    action_permissions: ClassVar[dict[str, str]] = {}

    organization: Organization
    membership: Membership

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        self.membership = resolve_membership(request.user, kwargs["org_id"])
        self.organization = self.membership.organization
        perm = self.required_permission(request)
        if perm:
            require_perm(self.membership, perm)

    def required_permission(self, request: Request) -> str | None:
        action = getattr(self, "action", None)
        if action and action in self.action_permissions:
            return self.action_permissions[action]
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return self.read_permission
        return self.write_permission


class OrganizationScopedViewSet(OrganizationScopedMixin, viewsets.GenericViewSet):  # type: ignore[type-arg]
    """GenericViewSet whose queryset is always restricted to the URL's organization."""

    model: ClassVar[type[models.Model]]
    lookup_value_converter = "uuid"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # DRF's CreateModelMixin.perform_create would silently replace ours (and drop the
        # organization) if a mixin is listed before this class. Fail at import instead.
        mro = cls.__mro__
        if mixins.CreateModelMixin in mro and mro.index(mixins.CreateModelMixin) < mro.index(
            OrganizationScopedViewSet
        ):
            raise TypeError(
                f"{cls.__name__}: list OrganizationScopedViewSet before DRF mixins in the bases."
            )

    def get_queryset(self) -> models.QuerySet[Any]:
        if getattr(self, "swagger_fake_view", False):  # OpenAPI generation has no org
            return self.model._default_manager.none()
        return self.model._default_manager.filter(organization=self.organization)

    def perform_create(self, serializer: serializers.BaseSerializer[Any]) -> None:
        serializer.save(organization=self.organization)


class OrgScopedRelatedField(serializers.PrimaryKeyRelatedField):  # type: ignore[type-arg]
    """A foreign-key field that only accepts objects from the request's organization.

    Prevents cross-tenant references such as attaching another tenant's campaign.
    """

    def __init__(self, model: type[models.Model], **kwargs: Any) -> None:
        self.model = model
        kwargs.setdefault("queryset", model._default_manager.none())
        super().__init__(**kwargs)

    def get_queryset(self) -> models.QuerySet[Any]:
        view = self.context.get("view")
        organization = getattr(view, "organization", None)
        if organization is None:
            return self.model._default_manager.none()
        return self.model._default_manager.filter(organization=organization)
