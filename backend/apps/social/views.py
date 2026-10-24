from typing import Any

from django.conf import settings
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.organizations.api import OrganizationScopedViewSet
from apps.organizations.roles import Perm

from . import services
from .adapters.base import NotConfigured
from .adapters.registry import real_adapter
from .models import SocialAccount, SocialPlatform


class SocialAccountSerializer(serializers.ModelSerializer[SocialAccount]):
    """Never includes tokens."""

    is_usable = serializers.BooleanField(read_only=True)
    connected_by_email = serializers.EmailField(
        source="connected_by.email", read_only=True, default=None
    )

    class Meta:
        model = SocialAccount
        fields = [
            "id",
            "platform",
            "external_id",
            "name",
            "username",
            "account_type",
            "status",
            "is_mock",
            "is_usable",
            "scopes",
            "token_expires_at",
            "last_error",
            "connected_by_email",
            "connected_at",
        ]
        read_only_fields = fields


class ConnectSerializer(serializers.Serializer[None]):
    platform = serializers.ChoiceField(choices=SocialPlatform.choices)
    simulation = serializers.BooleanField(default=False)


class CallbackSerializer(serializers.Serializer[None]):
    state = serializers.CharField(max_length=64)
    code = serializers.CharField(max_length=2000)


def _platform_info(platform: str) -> dict[str, Any]:
    real = real_adapter(platform)
    caps = real.capabilities
    return {
        "platform": platform,
        "display_name": caps.display_name,
        "configured": real.is_configured(),
        "simulation_available": bool(settings.SOCIAL_MOCK_ENABLED),
        "publish_formats": sorted(caps.publish_formats),
        "supports_text_only": caps.supports_text_only,
        "supports_metrics": caps.supports_metrics,
        "max_images": caps.max_images,
        "notes": list(caps.notes),
    }


_platform = inline_serializer(
    "PlatformInfo",
    {
        "platform": serializers.CharField(),
        "display_name": serializers.CharField(),
        "configured": serializers.BooleanField(),
        "simulation_available": serializers.BooleanField(),
        "publish_formats": serializers.ListField(child=serializers.CharField()),
        "supports_text_only": serializers.BooleanField(),
        "supports_metrics": serializers.BooleanField(),
        "max_images": serializers.IntegerField(),
        "notes": serializers.ListField(child=serializers.CharField()),
    },
    many=True,
)


class SocialAccountViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
):
    model = SocialAccount
    serializer_class = SocialAccountSerializer
    read_permission = Perm.SOCIAL_VIEW
    write_permission = Perm.SOCIAL_MANAGE
    action_permissions = {"platforms": Perm.SOCIAL_VIEW}
    throttle_scope = "auth"

    def get_throttles(self) -> list[Any]:
        return [ScopedRateThrottle()] if self.action == "connect" else []

    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("connected_by")
        if self.request.query_params.get("include_disconnected") != "true":
            qs = qs.exclude(status=SocialAccount.Status.DISCONNECTED)
        if platform := self.request.query_params.get("platform"):
            qs = qs.filter(platform=platform)
        return qs

    def perform_destroy(self, instance: SocialAccount) -> None:
        services.disconnect(instance, actor=self.request.user)

    @extend_schema(responses=_platform)
    @action(detail=False, methods=["get"])
    def platforms(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response([_platform_info(p) for p in SocialPlatform.values])

    @extend_schema(
        request=ConnectSerializer,
        responses=inline_serializer("ConnectStart", {"authorization_url": serializers.CharField()}),
    )
    @action(detail=False, methods=["post"])
    def connect(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = ConnectSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            url = services.start_connection(
                self.organization,
                user=request.user,
                platform=payload.validated_data["platform"],
                mock=payload.validated_data["simulation"],
            )
        except NotConfigured as exc:
            raise serializers.ValidationError({"platform": str(exc)}) from exc
        return Response({"authorization_url": url})


class OAuthCallbackView(APIView):
    """Completes an authorization started by the same signed-in user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CallbackSerializer,
        responses=inline_serializer(
            "ConnectResult",
            {
                "organization_id": serializers.UUIDField(),
                "accounts": SocialAccountSerializer(many=True),
                "meta_connection_id": serializers.UUIDField(allow_null=True),
            },
        ),
    )
    def post(self, request: Request) -> Response:
        payload = CallbackSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        org, accounts, meta_connection = services.complete_connection(
            user=request.user, **payload.validated_data
        )
        return Response(
            {
                "organization_id": org.pk,
                "accounts": SocialAccountSerializer(accounts, many=True).data,
                "meta_connection_id": meta_connection.pk if meta_connection else None,
            },
            status=status.HTTP_200_OK,
        )
