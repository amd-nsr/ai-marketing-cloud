from typing import Any

from rest_framework import mixins

from apps.organizations.api import OrganizationScopedViewSet
from apps.organizations.roles import Perm

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
):
    model = AuditEvent
    serializer_class = AuditEventSerializer
    read_permission = Perm.AUDIT_VIEW

    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("actor")
        params = self.request.query_params
        if action := params.get("action"):
            qs = qs.filter(action__startswith=action)
        if target_id := params.get("target_id"):
            qs = qs.filter(target_id=target_id)
        return qs
