import uuid
from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.content.models import ContentItem
from apps.organizations.api import OrganizationScopedViewSet, OrgScopedRelatedField
from apps.organizations.roles import Perm
from apps.social.models import SocialAccount

from . import services
from .models import PublishedPost, PublishingAttempt, PublishingJob


class AttemptSerializer(serializers.ModelSerializer[PublishingAttempt]):
    class Meta:
        model = PublishingAttempt
        fields = ["number", "outcome", "started_at", "finished_at", "error_code", "error_message"]
        read_only_fields = fields


class PublishingJobSerializer(serializers.ModelSerializer[PublishingJob]):
    content_title = serializers.CharField(source="content_item.title", read_only=True)
    platform = serializers.CharField(source="social_account.platform", read_only=True)
    account_name = serializers.CharField(source="social_account.name", read_only=True)
    version_number = serializers.IntegerField(source="version.number", read_only=True)
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, default=None
    )
    attempt_log = AttemptSerializer(many=True, read_only=True)

    class Meta:
        model = PublishingJob
        fields = [
            "id",
            "content_item",
            "content_title",
            "social_account",
            "account_name",
            "platform",
            "version_number",
            "status",
            "scheduled_for",
            "attempts",
            "max_attempts",
            "next_attempt_at",
            "external_post_id",
            "permalink",
            "published_at",
            "error_code",
            "error_message",
            "is_mock",
            "initiated_by",
            "created_by_email",
            "attempt_log",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PublishRequestSerializer(serializers.Serializer[None]):
    content_item = OrgScopedRelatedField(ContentItem)
    social_account = OrgScopedRelatedField(SocialAccount)
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)


class RetrySerializer(serializers.Serializer[None]):
    confirm_not_published = serializers.BooleanField(default=False)


class PublishedPostSerializer(serializers.ModelSerializer[PublishedPost]):
    content_title = serializers.CharField(source="content_item.title", read_only=True)
    account_name = serializers.CharField(source="social_account.name", read_only=True)

    class Meta:
        model = PublishedPost
        fields = [
            "id",
            "job",
            "content_item",
            "content_title",
            "social_account",
            "account_name",
            "platform",
            "format",
            "external_post_id",
            "permalink",
            "published_at",
            "is_mock",
            "metrics_last_collected_at",
        ]
        read_only_fields = fields


class PublishingJobViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    model = PublishingJob
    serializer_class = PublishingJobSerializer
    read_permission = Perm.PUBLISHING_VIEW
    write_permission = Perm.PUBLISHING_PUBLISH

    def get_queryset(self) -> Any:
        qs = (
            super()
            .get_queryset()
            .select_related("content_item", "social_account", "version", "created_by")
            .prefetch_related("attempt_log")
        )
        p = self.request.query_params
        if s := p.get("status"):
            qs = qs.filter(status__in=s.split(","))
        if item := p.get("content_item"):
            qs = qs.filter(content_item_id=item)
        return qs

    @extend_schema(
        request=PublishRequestSerializer,
        responses={201: PublishingJobSerializer, 200: PublishingJobSerializer},
        parameters=[
            OpenApiParameter(
                "Idempotency-Key",
                str,
                OpenApiParameter.HEADER,
                description="Repeating a request with the same key returns the original job.",
            )
        ],
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = PublishRequestSerializer(data=request.data, context=self.get_serializer_context())
        payload.is_valid(raise_exception=True)
        key = (request.headers.get("Idempotency-Key") or "").strip()[:100] or f"auto-{uuid.uuid4()}"
        job, created = services.request_publish(
            self.organization,
            item=payload.validated_data["content_item"],
            account=payload.validated_data["social_account"],
            scheduled_for=payload.validated_data.get("scheduled_for"),
            actor=request.user,
            idempotency_key=key,
        )
        return Response(
            self.get_serializer(job).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(request=None, responses=PublishingJobSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        job = services.cancel_job(self.get_object(), actor=request.user, reason="Cancelled by user")
        return Response(self.get_serializer(job).data)

    @extend_schema(request=RetrySerializer, responses=PublishingJobSerializer)
    @action(detail=True, methods=["post"])
    def retry(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = RetrySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        job = services.retry_job(
            self.get_object(),
            actor=request.user,
            confirm_not_published=payload.validated_data["confirm_not_published"],
        )
        return Response(self.get_serializer(job).data)


class PublishedPostViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    model = PublishedPost
    serializer_class = PublishedPostSerializer
    read_permission = Perm.PUBLISHING_VIEW

    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("content_item", "social_account")
        if platform := self.request.query_params.get("platform"):
            qs = qs.filter(platform=platform)
        return qs
