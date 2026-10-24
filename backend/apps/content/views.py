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

from apps.ai.images import image_generation_status
from apps.ai.providers.registry import get_provider
from apps.ai.serializers import AIWorkflowRunSerializer
from apps.ai.workflows import start_workflow
from apps.audit import services as audit
from apps.brand.services import get_guideline
from apps.core.errors import Conflict, ServiceUnavailable
from apps.organizations.api import OrganizationScopedViewSet
from apps.organizations.roles import Perm

from . import approvals, services
from .media import ffmpeg_available
from .models import (
    Approval,
    ContentAsset,
    ContentItem,
    ContentTemplate,
    ContentVersion,
    LibraryAsset,
    RenderJob,
)
from .serializers import (
    ApprovalSerializer,
    AssetUploadSerializer,
    AssistSerializer,
    BuiltInTemplateSerializer,
    ContentAssetSerializer,
    ContentItemCreateSerializer,
    ContentItemSerializer,
    ContentTemplateSerializer,
    ContentVersionSerializer,
    DecisionSerializer,
    DuplicateSerializer,
    GenerateContentSerializer,
    GenerateImageSerializer,
    LibraryAssetSerializer,
    LibraryUploadSerializer,
    RegenerateSerializer,
    RenderJobSerializer,
    RenderUploadSerializer,
    StoryboardSerializer,
    StudioCapabilitiesSerializer,
    SubmitSerializer,
    VersionFieldsSerializer,
)
from .templates import built_in_templates
from .workflows import ASSIST, GENERATE, GENERATE_IMAGE, REGENERATE, STORYBOARD


class CapabilityUnavailable(ServiceUnavailable):
    """A feature that isn't configured here (as opposed to a failure while running it)."""

    default_code = "capability_unavailable"


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
        if self.action in {"generate", "regenerate", "assist", "storyboard"}:
            return [ScopedRateThrottle()]
        return []

    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("campaign", "current_version")
        if self.action == "list":  # thumbnails; detail actions must see live asset counts
            qs = qs.prefetch_related("assets")
        p = self.request.query_params
        if s := p.get("status"):
            qs = qs.filter(status__in=s.split(","))
        else:
            qs = qs.exclude(status=ContentItem.Status.ARCHIVED)
        if platform := p.get("platform"):
            qs = qs.filter(platform__in=platform.split(","))
        if fmt := p.get("format"):
            qs = qs.filter(format__in=fmt.split(","))
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
        data = payload.validated_data
        campaign = data.get("campaign")
        audience = data.get("audience")
        run = start_workflow(
            self.organization,
            GENERATE,
            user=request.user,
            payload={
                "brief": data["brief"],
                "targets": data["targets"],
                "campaign_id": str(campaign.pk) if campaign else None,
                "objective": data["objective"],
                "audience_id": str(audience.pk) if audience else None,
                "tone": data["tone"],
                "language": data["language"],
                "length": data["length"],
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

    @extend_schema(request=AssistSerializer, responses={202: AIWorkflowRunSerializer})
    @action(detail=True, methods=["post"])
    def assist(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Suggest replacement text for one section (rewrite, shorten, translate, ...).

        The suggestion arrives in the run's output; nothing is saved until the user
        accepts it into the editor and saves a version.
        """
        item = self.get_object()
        payload = AssistSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        run = start_workflow(
            self.organization,
            ASSIST,
            user=request.user,
            payload={"item_id": str(item.pk), **payload.validated_data},
        )
        return Response(AIWorkflowRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=StoryboardSerializer, responses={202: AIWorkflowRunSerializer})
    @action(detail=True, methods=["post"])
    def storyboard(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        payload = StoryboardSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        run = start_workflow(
            self.organization,
            STORYBOARD,
            user=request.user,
            payload={"item_id": str(item.pk), "brief": payload.validated_data["brief"]},
        )
        return Response(AIWorkflowRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=DuplicateSerializer, responses={201: ContentItemSerializer})
    @action(detail=True, methods=["post"])
    def duplicate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Copy into a new draft; pass platform/format to adapt it for another channel."""
        item = self.get_object()
        payload = DuplicateSerializer(
            data=request.data, context={**self.get_serializer_context(), "item": item}
        )
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        copy = services.duplicate_item(
            item,
            actor=request.user,
            title=data["title"],
            platform=data.get("platform"),
            format=data.get("format"),
            campaign=data.get("campaign", ...),
        )
        return Response(self.get_serializer(copy).data, status=status.HTTP_201_CREATED)

    # --- rendered outputs ---------------------------------------------------------

    @extend_schema(
        request={"multipart/form-data": RenderUploadSerializer},
        responses={201: ContentAssetSerializer},
    )
    @action(detail=True, methods=["post"], url_path="renders")
    def renders(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Upload the editor's export of one page of the current design."""
        payload = RenderUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        asset = services.upload_render(
            self.get_object(),
            actor=request.user,
            page_id=payload.validated_data["page_id"],
            upload=payload.validated_data["file"],
        )
        return Response(ContentAssetSerializer(asset).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={202: RenderJobSerializer})
    @action(detail=True, methods=["post"], url_path="render-video")
    def render_video(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        job = services.start_video_render(self.get_object(), actor=request.user)
        return Response(RenderJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses=RenderJobSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="render-jobs")
    def render_jobs(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        jobs = self.get_object().render_jobs.select_related("version", "output")[:10]
        return Response(RenderJobSerializer(jobs, many=True).data)

    @extend_schema(responses=StudioCapabilitiesSerializer)
    @action(detail=False, methods=["get"])
    def capabilities(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """What this deployment can do, so the UI never offers a feature that isn't there."""
        from django.conf import settings

        try:
            text = get_provider()
            text_cap = {
                "available": True,
                "is_mock": text.is_mock,
                "provider": text.name,
                "note": "Labelled mock output (no AI key configured)." if text.is_mock else "",
            }
        except Exception:  # noqa: BLE001 - any misconfiguration means "unavailable"
            text_cap = {
                "available": False,
                "is_mock": False,
                "provider": None,
                "note": "Text generation isn't configured.",
            }
        image = image_generation_status()
        ffmpeg = ffmpeg_available()
        return Response(
            StudioCapabilitiesSerializer(
                {
                    "text_generation": text_cap,
                    "image_generation": {
                        **image,
                        "note": (
                            "Placeholder images from the mock provider."
                            if image["is_mock"]
                            else ""
                            if image["available"]
                            else "Image generation isn't set up. Upload images instead."
                        ),
                    },
                    "video_rendering": {
                        "available": ffmpeg,
                        "is_mock": False,
                        "provider": "ffmpeg" if ffmpeg else None,
                        "note": "" if ffmpeg else "ffmpeg isn't installed on the server.",
                    },
                    "ai_video_generation": {
                        "available": False,
                        "is_mock": False,
                        "provider": None,
                        "note": "Not available: videos are edited from your own clips.",
                    },
                    "ai_voiceover": {
                        "available": False,
                        "is_mock": False,
                        "provider": None,
                        "note": "Not available yet: upload a recorded voiceover instead.",
                    },
                    "max_media_upload_bytes": settings.MAX_MEDIA_UPLOAD_BYTES,
                    "max_image_upload_bytes": settings.MAX_IMAGE_UPLOAD_BYTES,
                }
            ).data
        )

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

    @extend_schema(responses={(200, "*/*"): OpenApiTypes.BINARY, 302: None})
    @action(detail=True, methods=["get"], url_path=r"assets/(?P<asset_id>[0-9a-f-]{36})/file")
    def asset_file(
        self, request: Request, asset_id: str, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        asset = self._asset(asset_id)
        return _stream_file(asset.file, asset.content_type)


class LibraryAssetViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    """The organization's reusable media: uploaded and AI-generated images, video, audio."""

    model = LibraryAsset
    serializer_class = LibraryAssetSerializer
    read_permission = Perm.CONTENT_VIEW
    write_permission = Perm.CONTENT_EDIT
    throttle_scope = "ai"

    def get_throttles(self) -> list[Any]:
        return [ScopedRateThrottle()] if self.action == "generate" else []

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        p = self.request.query_params
        if kind := p.get("kind"):
            qs = qs.filter(kind__in=kind.split(","))
        if source := p.get("source"):
            qs = qs.filter(source=source)
        if tag := p.get("tag"):
            qs = qs.filter(tags__contains=[tag.lower()])
        if q := p.get("q"):
            qs = qs.filter(Q(title__icontains=q) | Q(original_filename__icontains=q))
        return qs

    @extend_schema(
        request={"multipart/form-data": LibraryUploadSerializer},
        responses={201: LibraryAssetSerializer},
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = LibraryUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        asset = services.upload_library_asset(
            self.organization,
            actor=request.user,
            upload=data["file"],
            title=data["title"],
            tags=data["tags"],
        )
        return Response(self.get_serializer(asset).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer: Any) -> None:
        asset = serializer.save()
        audit.record(
            "library_asset.updated",
            organization=self.organization,
            actor=self.request.user,
            target=asset,
        )

    def perform_destroy(self, instance: LibraryAsset) -> None:
        services.delete_library_asset(instance, actor=self.request.user)

    @extend_schema(responses={(200, "*/*"): OpenApiTypes.BINARY, 302: None})
    @action(detail=True, methods=["get"])
    def file(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponseBase:
        asset = self.get_object()
        return _stream_file(asset.file, asset.content_type)

    @extend_schema(request=GenerateImageSerializer, responses={202: AIWorkflowRunSerializer})
    @action(detail=False, methods=["post"])
    def generate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Generate an image into the library with the configured image provider."""
        if not image_generation_status()["available"]:
            raise CapabilityUnavailable(
                "Image generation isn't set up for this workspace. Upload images or use "
                "the brand kit instead."
            )
        payload = GenerateImageSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        run = start_workflow(
            self.organization, GENERATE_IMAGE, user=request.user, payload=payload.validated_data
        )
        return Response(AIWorkflowRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class ContentTemplateViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    """Starting documents: built-in (styled with the brand) plus the organization's own."""

    model = ContentTemplate
    serializer_class = ContentTemplateSerializer
    read_permission = Perm.CONTENT_VIEW
    write_permission = Perm.CONTENT_EDIT
    pagination_class = None

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        if kind := self.request.query_params.get("kind"):
            qs = qs.filter(kind=kind)
        return qs

    @extend_schema(responses=BuiltInTemplateSerializer(many=True))
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        kind = request.query_params.get("kind")
        built_in = [
            t
            for t in built_in_templates(get_guideline(self.organization))
            if not kind or t["kind"] == kind
        ]
        own = ContentTemplateSerializer(self.get_queryset(), many=True).data
        return Response([*own, *built_in])

    @extend_schema(request=ContentTemplateSerializer, responses={201: ContentTemplateSerializer})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = ContentTemplateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        doc = payload.validated_data["document"]
        services.validate_document(  # referenced assets must belong to this organization
            self.organization,
            {"design": "post", "carousel": "carousel", "video": "reel"}[doc["kind"]],
            doc,
        )
        if ContentTemplate.objects.filter(organization=self.organization).count() >= 100:
            raise Conflict("You can save at most 100 templates.")
        template = ContentTemplate.objects.create(
            organization=self.organization,
            name=payload.validated_data["name"],
            description=payload.validated_data.get("description", ""),
            kind=doc["kind"],
            document=doc,
            created_by=self.membership.user,
        )
        audit.record(
            "content_template.created",
            organization=self.organization,
            actor=request.user,
            target=template,
        )
        return Response(ContentTemplateSerializer(template).data, status=status.HTTP_201_CREATED)


class RenderJobViewSet(OrganizationScopedViewSet, mixins.RetrieveModelMixin):
    model = RenderJob
    serializer_class = RenderJobSerializer
    read_permission = Perm.CONTENT_VIEW

    def get_queryset(self) -> Any:
        return super().get_queryset().select_related("version", "output")


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
