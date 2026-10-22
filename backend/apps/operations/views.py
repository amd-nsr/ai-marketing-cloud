from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.api import OrganizationScopedMixin
from apps.organizations.roles import Perm

from . import heartbeat, overview


class BackgroundStatusSerializer(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=["ok", "stale", "unknown"])
    last_heartbeat_at = serializers.DateTimeField(allow_null=True)
    age_seconds = serializers.IntegerField(allow_null=True)


class JobFailureSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    content_item = serializers.UUIDField()
    content_title = serializers.CharField()
    account_name = serializers.CharField()
    platform = serializers.CharField()
    is_mock = serializers.BooleanField()
    error_code = serializers.CharField()
    error_message = serializers.CharField()
    at = serializers.DateTimeField()


class RunFailureSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    workflow = serializers.CharField()
    error_code = serializers.CharField()
    error_message = serializers.CharField()
    is_mock = serializers.BooleanField()
    at = serializers.DateTimeField()


class PublishingOpsSerializer(serializers.Serializer[Any]):
    scheduled = serializers.IntegerField()
    queued = serializers.IntegerField()
    publishing = serializers.IntegerField()
    needs_reconciliation = serializers.IntegerField()
    published_recent = serializers.IntegerField()
    failed_recent = serializers.IntegerField()
    recent_failures = JobFailureSerializer(many=True)


class AIOpsSerializer(serializers.Serializer[Any]):
    queued = serializers.IntegerField()
    running = serializers.IntegerField()
    succeeded_recent = serializers.IntegerField()
    failed_recent = serializers.IntegerField()
    recent_failures = RunFailureSerializer(many=True)


class AutomationOpsSerializer(serializers.Serializer[Any]):
    mode = serializers.CharField()
    paused = serializers.BooleanField()
    awaiting_approval = serializers.IntegerField()
    deferred = serializers.IntegerField()
    failed_recent = serializers.IntegerField()


class AccountAttentionSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    platform = serializers.CharField()
    status = serializers.CharField()


class OperationsOverviewSerializer(serializers.Serializer[Any]):
    generated_at = serializers.DateTimeField()
    window_days = serializers.IntegerField()
    background = BackgroundStatusSerializer()
    publishing = PublishingOpsSerializer()
    ai = AIOpsSerializer()
    automation = AutomationOpsSerializer()
    social_accounts_needing_attention = AccountAttentionSerializer(many=True)
    metrics_collection = serializers.DictField(child=serializers.IntegerField())


class OperationsOverviewView(OrganizationScopedMixin):
    read_permission = Perm.ORG_MANAGE

    @extend_schema(responses=OperationsOverviewSerializer, tags=["operations"])
    def get(self, request: Request, org_id: str) -> Response:
        data = overview.build(self.organization)
        return Response(OperationsOverviewSerializer(data).data)


class BackgroundHealthView(APIView):
    """Is background processing alive? Exposes only status and heartbeat age."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(responses=BackgroundStatusSerializer, tags=["health"])
    def get(self, request: Request) -> Response:
        data = heartbeat.status()
        return Response(
            BackgroundStatusSerializer(data).data, status=200 if data["status"] == "ok" else 503
        )
