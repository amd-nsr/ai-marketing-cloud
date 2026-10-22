from typing import Any

from django.http import FileResponse, HttpResponseBase, HttpResponseRedirect
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.organizations.api import OrganizationScopedMixin, OrganizationScopedViewSet
from apps.organizations.roles import Perm

from . import services
from .models import BrandAsset, TargetAudience
from .presets import GOALS, INDUSTRY_PRESETS, PLATFORMS
from .serializers import (
    BrandAssetSerializer,
    BrandAssetUploadSerializer,
    BrandGuidelineSerializer,
    BusinessProfileSerializer,
    OnboardingStatusSerializer,
    ReferenceDataSerializer,
    TargetAudienceSerializer,
)


class ReferenceDataView(APIView):
    """Industry presets, goal and platform vocabularies used by onboarding."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ReferenceDataSerializer)
    def get(self, request: Request) -> Response:
        return Response({"industries": INDUSTRY_PRESETS, "goals": GOALS, "platforms": PLATFORMS})


class BusinessProfileView(OrganizationScopedMixin, APIView):
    read_permission = Perm.BRAND_VIEW
    write_permission = Perm.BRAND_EDIT

    @extend_schema(responses=BusinessProfileSerializer)
    def get(self, request: Request, org_id: str) -> Response:
        return Response(BusinessProfileSerializer(services.get_profile(self.organization)).data)

    @extend_schema(request=BusinessProfileSerializer, responses=BusinessProfileSerializer)
    def patch(self, request: Request, org_id: str) -> Response:
        profile = services.get_profile(self.organization)
        serializer = BusinessProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit.record(
            "business_profile.updated",
            organization=self.organization,
            actor=request.user,
            target=profile,
            metadata={"fields": sorted(serializer.validated_data)},
            request=request._request,
        )
        return Response(serializer.data)


class BrandGuidelineView(OrganizationScopedMixin, APIView):
    read_permission = Perm.BRAND_VIEW
    write_permission = Perm.BRAND_EDIT

    @extend_schema(responses=BrandGuidelineSerializer)
    def get(self, request: Request, org_id: str) -> Response:
        return Response(BrandGuidelineSerializer(services.get_guideline(self.organization)).data)

    @extend_schema(request=BrandGuidelineSerializer, responses=BrandGuidelineSerializer)
    def patch(self, request: Request, org_id: str) -> Response:
        guideline = services.get_guideline(self.organization)
        serializer = BrandGuidelineSerializer(guideline, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit.record(
            "brand_guideline.updated",
            organization=self.organization,
            actor=request.user,
            target=guideline,
            metadata={"fields": sorted(serializer.validated_data)},
            request=request._request,
        )
        return Response(serializer.data)


class TargetAudienceViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    model = TargetAudience
    serializer_class = TargetAudienceSerializer
    read_permission = Perm.BRAND_VIEW
    write_permission = Perm.BRAND_EDIT


class BrandAssetViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
):
    model = BrandAsset
    serializer_class = BrandAssetSerializer
    read_permission = Perm.BRAND_VIEW
    write_permission = Perm.BRAND_EDIT

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        kind = self.request.query_params.get("kind")
        return qs.filter(kind=kind) if kind else qs

    @extend_schema(
        request={"multipart/form-data": BrandAssetUploadSerializer},
        responses={201: BrandAssetSerializer},
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = BrandAssetUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        asset = services.upload_asset(
            self.organization,
            actor=request.user,
            upload=payload.validated_data["file"],
            kind=payload.validated_data["kind"],
            title=payload.validated_data["title"],
            request=request._request,
        )
        return Response(BrandAssetSerializer(asset).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: BrandAsset) -> None:
        audit.record(
            "brand_asset.deleted",
            organization=self.organization,
            actor=self.request.user,
            target=instance,
            request=self.request._request,
        )
        instance.delete()

    @extend_schema(responses={(200, "image/*"): OpenApiTypes.BINARY, 302: None})
    @action(detail=True, methods=["get"], url_path="file")
    def file(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponseBase:
        """Stream the file after the membership check, or redirect to a signed URL (S3)."""
        asset = self.get_object()
        storage = asset.file.storage
        if storage.__class__.__name__ == "S3Storage":
            return HttpResponseRedirect(storage.url(asset.file.name))
        response = FileResponse(
            storage.open(asset.file.name, "rb"), content_type=asset.content_type
        )
        response["Content-Disposition"] = "inline"
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, max-age=300"
        return response


class OnboardingView(OrganizationScopedMixin, APIView):
    read_permission = Perm.BRAND_VIEW
    write_permission = Perm.BRAND_EDIT

    def _status(self) -> dict[str, Any]:
        steps = services.onboarding_steps(self.organization)
        required = [s for s in steps if s.required]
        return {
            "steps": [s.__dict__ for s in steps],
            "percent": round(100 * sum(s.complete for s in steps) / len(steps)),
            "can_complete": all(s.complete for s in required),
            "completed_at": services.get_profile(self.organization).onboarding_completed_at,
        }

    @extend_schema(responses=OnboardingStatusSerializer)
    def get(self, request: Request, org_id: str) -> Response:
        return Response(OnboardingStatusSerializer(self._status()).data)

    @extend_schema(request=None, responses=OnboardingStatusSerializer)
    def post(self, request: Request, org_id: str) -> Response:
        """Mark onboarding complete (all required steps must be done)."""
        services.complete_onboarding(
            self.organization, actor=request.user, request=request._request
        )
        return Response(OnboardingStatusSerializer(self._status()).data)


class BusinessContextView(OrganizationScopedMixin, APIView):
    """Exactly what AI workflows receive about this business, for user inspection."""

    read_permission = Perm.BRAND_VIEW

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, org_id: str) -> Response:
        return Response(services.build_business_context(self.organization))
