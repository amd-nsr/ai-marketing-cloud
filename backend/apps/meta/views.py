import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, extend_schema_field, inline_serializer
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.api import OrganizationScopedViewSet
from apps.organizations.roles import Perm
from apps.social.models import SocialAccount

from . import permissions, services
from .callbacks import (
    InvalidSignature,
    parse_signed_request,
    verify_subscription,
    verify_webhook_signature,
)
from .models import MetaConnection, MetaDataDeletionRequest

logger = logging.getLogger(__name__)


class MetaPageSerializer(serializers.Serializer[Any]):
    id = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField(allow_blank=True)
    can_publish = serializers.BooleanField()
    connected = serializers.BooleanField()
    social_account_id = serializers.UUIDField(allow_null=True)


class MetaAdAccountSerializer(serializers.Serializer[Any]):
    id = serializers.CharField()
    name = serializers.CharField()
    currency = serializers.CharField()
    timezone_name = serializers.CharField(allow_blank=True)
    is_active = serializers.BooleanField()
    connected = serializers.BooleanField()
    ad_account_id = serializers.UUIDField(allow_null=True)


class FeatureSerializer(serializers.Serializer[Any]):
    feature = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    available = serializers.BooleanField()
    missing = serializers.ListField(child=serializers.CharField())


class MetaConnectionSerializer(serializers.ModelSerializer[MetaConnection]):
    """Never includes tokens."""

    is_usable = serializers.BooleanField(read_only=True)
    connected_by_email = serializers.EmailField(
        source="connected_by.email", read_only=True, default=None
    )
    features = serializers.SerializerMethodField()
    pages = serializers.SerializerMethodField()
    ad_accounts = serializers.SerializerMethodField()
    ads_enabled = serializers.SerializerMethodField()

    class Meta:
        model = MetaConnection
        fields = [
            "id",
            "name",
            "status",
            "is_mock",
            "is_usable",
            "granted_permissions",
            "declined_permissions",
            "features",
            "pages",
            "ad_accounts",
            "ads_enabled",
            "token_expires_at",
            "assets_refreshed_at",
            "last_checked_at",
            "last_error",
            "connected_by_email",
            "connected_at",
        ]
        read_only_fields = fields

    @extend_schema_field(FeatureSerializer(many=True))
    def get_features(self, obj: MetaConnection) -> list[dict[str, Any]]:
        return permissions.feature_status(obj.granted_permissions)

    @extend_schema_field(MetaPageSerializer(many=True))
    def get_pages(self, obj: MetaConnection) -> list[dict[str, Any]]:
        connected = dict(
            SocialAccount.objects.filter(
                organization_id=obj.organization_id,
                platform="facebook",
                status=SocialAccount.Status.CONNECTED,
            ).values_list("external_id", "pk")
        )
        return [
            {**p, "connected": p["id"] in connected, "social_account_id": connected.get(p["id"])}
            for p in obj.available_pages
        ]

    @extend_schema_field(MetaAdAccountSerializer(many=True))
    def get_ad_accounts(self, obj: MetaConnection) -> list[dict[str, Any]]:
        from apps.ads.models import AdAccount

        connected = dict(
            AdAccount.objects.filter(
                organization_id=obj.organization_id, status=AdAccount.Status.CONNECTED
            ).values_list("external_id", "pk")
        )
        return [
            {**a, "connected": a["id"] in connected, "ad_account_id": connected.get(a["id"])}
            for a in obj.available_ad_accounts
        ]

    def get_ads_enabled(self, obj: MetaConnection) -> bool:
        return bool(settings.META_ADS_ENABLED)


class SelectPagesSerializer(serializers.Serializer[None]):
    page_ids = serializers.ListField(child=serializers.CharField(max_length=64), max_length=50)


class SelectAdAccountsSerializer(serializers.Serializer[None]):
    account_ids = serializers.ListField(child=serializers.CharField(max_length=64), max_length=50)


class MetaConnectionViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
):
    model = MetaConnection
    serializer_class = MetaConnectionSerializer
    read_permission = Perm.SOCIAL_VIEW
    write_permission = Perm.SOCIAL_MANAGE
    action_permissions = {"connect_ad_accounts": Perm.ADS_MANAGE}

    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("connected_by")
        if self.request.query_params.get("include_disconnected") != "true":
            qs = qs.exclude(
                status__in=[MetaConnection.Status.DISCONNECTED, MetaConnection.Status.DELETED]
            )
        return qs

    def perform_destroy(self, instance: MetaConnection) -> None:
        services.disconnect(instance, actor=self.request.user, revoke=True)

    @extend_schema(request=None, responses=MetaConnectionSerializer)
    @action(detail=True, methods=["post"])
    def refresh(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        connection = services.refresh_connection(self.get_object(), actor=request.user)
        return Response(self.get_serializer(connection).data)

    @extend_schema(request=SelectPagesSerializer, responses=MetaConnectionSerializer)
    @action(detail=True, methods=["post"], url_path="pages")
    def connect_pages(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = SelectPagesSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        connection = self.get_object()
        services.connect_pages(
            connection, page_ids=payload.validated_data["page_ids"], actor=request.user
        )
        connection.refresh_from_db()
        return Response(self.get_serializer(connection).data)

    @extend_schema(request=SelectAdAccountsSerializer, responses=MetaConnectionSerializer)
    @action(detail=True, methods=["post"], url_path="ad-accounts")
    def connect_ad_accounts(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from apps.ads.services import connect_ad_accounts

        payload = SelectAdAccountsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        connection = self.get_object()
        if not connection.is_usable:
            from apps.core.errors import Conflict

            raise Conflict("This Meta connection needs to be reconnected first.")
        connect_ad_accounts(
            connection, account_ids=payload.validated_data["account_ids"], actor=request.user
        )
        return Response(self.get_serializer(connection).data)


# --- Public callbacks from Meta (no session; verified by signature) ---------------------------


def _signed_request(request: Request) -> str:
    data = request.data
    return str(data.get("signed_request", "")) if isinstance(data, dict) else ""


class _PublicMetaView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    parser_classes = [FormParser, MultiPartParser, JSONParser]


class WebhookView(_PublicMetaView):
    """Meta webhooks: subscription check (GET) and signed deliveries (POST)."""

    @extend_schema(exclude=True)
    def get(self, request: Request) -> HttpResponse:
        challenge = verify_subscription(request.query_params.dict())
        if challenge is None:
            return HttpResponse("Forbidden", status=403, content_type="text/plain")
        return HttpResponse(challenge, content_type="text/plain")

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        from .webhooks import process_delivery

        body = request._request.body  # raw bytes, needed for the signature
        try:
            verify_webhook_signature(body, request.headers.get("X-Hub-Signature-256"))
            payload = json.loads(body or b"{}")
        except (InvalidSignature, json.JSONDecodeError):
            logger.warning("Rejected Meta webhook delivery")
            return Response(status=status.HTTP_403_FORBIDDEN)
        stored = process_delivery(payload if isinstance(payload, dict) else {})
        return Response({"received": stored})


class DeauthorizeView(_PublicMetaView):
    """Meta calls this when a person removes the app from their Facebook settings."""

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        try:
            data = parse_signed_request(_signed_request(request))
        except InvalidSignature:
            return Response(status=status.HTTP_403_FORBIDDEN)
        services.handle_deauthorization(str(data["user_id"]))
        return Response({"ok": True})


class DataDeletionView(_PublicMetaView):
    """Meta's data deletion callback: delete, then return a status URL and code."""

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        try:
            data = parse_signed_request(_signed_request(request))
        except InvalidSignature:
            return Response(status=status.HTTP_403_FORBIDDEN)
        deletion = services.handle_data_deletion(str(data["user_id"]))
        code = deletion.confirmation_code
        return Response(
            {
                "url": f"{settings.FRONTEND_URL.rstrip('/')}/meta/data-deletion/{code}",
                "confirmation_code": code,
            }
        )


class DataDeletionStatusView(_PublicMetaView):
    @extend_schema(
        responses=inline_serializer(
            "MetaDataDeletionStatus",
            {
                "confirmation_code": serializers.CharField(),
                "status": serializers.CharField(),
                "requested_at": serializers.DateTimeField(),
                "completed_at": serializers.DateTimeField(allow_null=True),
            },
        ),
        tags=["meta"],
    )
    def get(self, request: Request, code: str) -> Response:
        deletion = MetaDataDeletionRequest.objects.filter(confirmation_code=code).first()
        if deletion is None:
            raise NotFound("Unknown confirmation code.")
        return Response(
            {
                "confirmation_code": deletion.confirmation_code,
                "status": deletion.status,
                "requested_at": deletion.created_at,
                "completed_at": deletion.completed_at,
            }
        )
