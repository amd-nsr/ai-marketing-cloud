from typing import Any

from rest_framework import mixins

from apps.organizations.api import OrganizationScopedViewSet
from apps.organizations.roles import Perm

from .models import AIWorkflowRun
from .serializers import AIWorkflowRunSerializer


class AIWorkflowRunViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    """Status of asynchronous AI jobs (clients poll the detail endpoint)."""

    model = AIWorkflowRun
    serializer_class = AIWorkflowRunSerializer
    read_permission = Perm.ORG_VIEW

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        if workflow := self.request.query_params.get("workflow"):
            qs = qs.filter(workflow=workflow)
        return qs
