from typing import Any

from django.db.models import Q
from django.http import FileResponse, HttpResponseBase, HttpResponseRedirect
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.ai.serializers import AIWorkflowRunSerializer
from apps.ai.workflows import start_workflow
from apps.audit import services as audit
from apps.organizations.api import OrganizationScopedViewSet
from apps.organizations.roles import Perm

from . import approvals, services
from .models import Approval, ContentAsset, ContentItem, ContentVersion
from .serializers import (
    ApprovalSerializer,
    AssetUploadSerializer,
    ContentAssetSerializer,
    ContentItemCreateSerializer,
    ContentItemSerializer,
    ContentVersionSerializer,
    DecisionSerializer,
    GenerateContentSerializer,
    RegenerateSerializer,
    SubmitSerializer,
    VersionFieldsSerializer,
)
from .workflows import GENERATE, REGENERATE


def _stream_file(file_field: Any, content_type: str) -> HttpResponseBase:
    storage = file_field.storage
    if storage.__class__.__name__ == "S3Storage":
        return HttpResponseRedirect(storage.url(file_field.name))
    response = FileResponse(storage.open(file_field.name, "rb"), content_type=content_type)
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=300"
    return response


class ContentItemViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    model = ContentItem
    serializer_class = ContentItemSerializer
    read_permission = Perm.CONTENT_VIEW
    write_permission = Perm.CONTENT_EDIT
    action_permissions = {"submit": Perm.CONTENT_SUBMIT}
    throttle_scope = "ai"

    def get_throttles(self) -> list[Any]:
        if self.action in {"generate", "regenerate"}:
            return [ScopedRateThrottle()]
        return []

    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("campaign", "current_version")
        p = self.request.query_params
        if s := p.get("status"):
            qs = qs.filter(status__in=s.split(","))
        else:
            qs = qs.exclude(status=ContentItem.Status.ARCHIVED)
        if platform := p.get("platform"):
            qs = qs.filter(platform=platform)
        if campaign := p.get("campaign"):
            qs = qs.filter(campaign_id=campaign)
        if q := p.get("q"):
            qs = qs.filter(Q(title__icontains=q) | Q(current_version__caption__icontains=q))
        if start := p.get("planned_from"):
            qs = qs.filter(planned_for__gte=start)
        if end := p.get("planned_to"):
            qs = qs.filter(planned_for__lt=end)
        if p.get("unplanned") == "true":
            qs = qs.filter(planned_for__isnull=True)
        return qs

    @extend_schema(request=ContentItemCreateSerializer, responses={201: ContentItemSerializer})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = ContentItemCreateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        meta = {
            k: data.pop(k)
            for k in ("title", "platform", "format", "campaign", "brief", "planned_for")
            if k in data
        }
        item = services.create_item(self.organization, actor=request.user, fields=data, **meta)
        return Response(self.get_serializer(item).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer: Any) -> None:
        item = serializer.save()
        audit.record(
            "content.updated",
            organization=self.organization,
            actor=self.request.user,
            target=item,
            metadata={"fields": sorted(serializer.validated_data)},
        )

    def perform_destroy(self, instance: ContentItem) -> None:
        services.delete_item(instance, actor=self.request.user, request=self.request._request)

    # --- versions -------------------------------------------------------------

    @extend_schema(responses=ContentVersionSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        return Response(
            ContentVersionSerializer(item.versions.select_related("created_by"), many=True).data
        )

    @extend_schema(request=VersionFieldsSerializer, responses={201: ContentVersionSerializer})
    @versions.mapping.post
    def create_version(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = VersionFieldsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        version = services.add_version(
            self.get_object(), fields=dict(payload.validated_data), actor=request.user
        )
        return Response(ContentVersionSerializer(version).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={201: ContentVersionSerializer})
    @action(detail=True, methods=["post"], url_path=r"versions/(?P<number>\d+)/restore")
    def restore(self, request: Request, number: str, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        try:
            source = item.versions.get(number=int(number))
        except ContentVersion.DoesNotExist as exc:
            raise NotFound() from exc
        version = services.restore_version(item, source, actor=request.user)
        return Response(ContentVersionSerializer(version).data, status=status.HTTP_201_CREATED)

    # --- AI -------------------------------------------------------------------

    @extend_schema(request=GenerateContentSerializer, responses={202: AIWorkflowRunSerializer})
    @action(detail=False, methods=["post"])
    def generate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = GenerateContentSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        payload.is_valid(raise_exception=True)
        campaign = payload.validated_data.get("campaign")
        run = start_workflow(
            self.organization,
            GENERATE,
            user=request.user,
            payload={
                "brief": payload.validated_data["brief"],
                "targets": payload.validated_data["targets"],
                "campaign_id": str(campaign.pk) if campaign else None,
            },
        )
        return Response(AIWorkflowRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=RegenerateSerializer, responses={202: AIWorkflowRunSerializer})
    @action(detail=True, methods=["post"])
    def regenerate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        if item.status not in services.EDITABLE:
            from apps.core.errors import Conflict

            raise Conflict("Content that is scheduled or published can't be regenerated.")
        payload = RegenerateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        run = start_workflow(
            self.organization,
            REGENERATE,
            user=request.user,
            payload={
                "item_id": str(item.pk),
                "instructions": payload.validated_data["instructions"],
            },
        )
        return Response(AIWorkflowRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    # --- workflow -------------------------------------------------------------

    @extend_schema(request=SubmitSerializer, responses={201: ApprovalSerializer})
    @action(detail=True, methods=["post"])
    def submit(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = SubmitSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        approval = approvals.submit_for_approval(
            self.get_object(), actor=request.user, note=payload.validated_data["note"]
        )
        return Response(ApprovalSerializer(approval).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=ContentItemSerializer)
    @action(detail=True, methods=["post"])
    def archive(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        pending = item.approvals.filter(status=Approval.Status.PENDING).first()
        if pending:
            approvals.cancel(pending, actor=request.user)
            item.refresh_from_db()
        services.set_status(item, ContentItem.Status.ARCHIVED, actor=request.user)
        return Response(self.get_serializer(item).data)

    @extend_schema(request=None, responses=ContentItemSerializer)
    @action(detail=True, methods=["post"])
    def unarchive(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        services.set_status(
            item, ContentItem.Status.DRAFT, actor=request.user, reason="Restored from archive"
        )
        return Response(self.get_serializer(item).data)

    # --- media ----------------------------------------------------------------

    @extend_schema(responses=ContentAssetSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="assets")
    def assets(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(ContentAssetSerializer(self.get_object().assets.all(), many=True).data)

    @extend_schema(
        request={"multipart/form-data": AssetUploadSerializer},
        responses={201: ContentAssetSerializer},
    )
    @assets.mapping.post
    def upload_asset(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = AssetUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        asset = services.upload_asset(
            self.get_object(), actor=request.user, upload=payload.validated_data["file"]
        )
        return Response(ContentAssetSerializer(asset).data, status=status.HTTP_201_CREATED)

    def _asset(self, asset_id: str) -> ContentAsset:
        item = self.get_object()
        try:
            asset: ContentAsset = item.assets.get(pk=asset_id)
        except (ContentAsset.DoesNotExist, ValueError) as exc:
            raise NotFound() from exc
        return asset

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"assets/(?P<asset_id>[0-9a-f-]{36})")
    def delete_asset(self, request: Request, asset_id: str, *args: Any, **kwargs: Any) -> Response:
        services.delete_asset(self._asset(asset_id), actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={(200, "image/*"): OpenApiTypes.BINARY, 302: None})
    @action(detail=True, methods=["get"], url_path=r"assets/(?P<asset_id>[0-9a-f-]{36})/file")
    def asset_file(
        self, request: Request, asset_id: str, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        asset = self._asset(asset_id)
        return _stream_file(asset.file, asset.content_type)


class ApprovalViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    model = Approval
    serializer_class = ApprovalSerializer
    read_permission = Perm.CONTENT_VIEW
    action_permissions = {
        "approve": Perm.CONTENT_APPROVE,
        "reject": Perm.CONTENT_APPROVE,
        "cancel": Perm.CONTENT_SUBMIT,
    }

    def get_queryset(self) -> Any:
        qs = (
            super()
            .get_queryset()
            .select_related("item", "version", "requested_by", "decided_by", "version__created_by")
        )
        if s := self.request.query_params.get("status"):
            qs = qs.filter(status=s)
        if item := self.request.query_params.get("item"):
            qs = qs.filter(item_id=item)
        return qs

    @extend_schema(request=DecisionSerializer, responses=ApprovalSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = DecisionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        approval = approvals.decide(
            self.get_object(),
            approver=self.membership,
            approve=True,
            comment=payload.validated_data["comment"],
        )
        return Response(ApprovalSerializer(approval).data)

    @extend_schema(request=DecisionSerializer, responses=ApprovalSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = DecisionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        approval = approvals.decide(
            self.get_object(),
            approver=self.membership,
            approve=False,
            comment=payload.validated_data["comment"],
        )
        return Response(ApprovalSerializer(approval).data)

    @extend_schema(request=None, responses=ApprovalSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        approval = approvals.cancel(self.get_object(), actor=request.user)
        return Response(ApprovalSerializer(approval).data)
