from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.organizations.api import OrganizationScopedViewSet

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer[Notification]):
    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "link", "read_at", "created_at"]
        read_only_fields = fields


class NotificationViewSet(OrganizationScopedViewSet, mixins.ListModelMixin):
    """The caller's own notifications in this organization."""

    model = Notification
    serializer_class = NotificationSerializer

    def get_queryset(self) -> Any:
        qs = super().get_queryset().filter(user=self.request.user)
        if self.request.query_params.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        return qs

    @extend_schema(
        request=None,
        responses=inline_serializer("MarkedRead", {"updated": serializers.IntegerField()}),
    )
    @action(detail=False, methods=["post"], url_path="mark-read")
    def mark_read(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        updated = self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"updated": updated})
