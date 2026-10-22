from typing import Any

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit import services as audit
from apps.organizations.api import OrganizationScopedMixin, OrganizationScopedViewSet
from apps.organizations.roles import Perm

from . import recommendations, services
from .definitions import METRICS
from .models import MarketingRecommendation, RecommendationEvidence

_days = OpenApiParameter("days", int, description="Look-back window in days (1-365, default 30).")


def _days_param(request: Request) -> int:
    try:
        return max(1, min(365, int(request.query_params.get("days", 30))))
    except ValueError:
        return 30


class AnalyticsOverviewView(OrganizationScopedMixin):
    read_permission = Perm.ANALYTICS_VIEW

    @extend_schema(parameters=[_days], responses=OpenApiTypes.OBJECT)
    def get(self, request: Request, org_id: str) -> Response:
        data = services.overview(self.organization, days=_days_param(request))
        data["definitions"] = {k: d.__dict__ for k, d in METRICS.items()}
        return Response(data)


class AnalyticsPostsView(OrganizationScopedMixin):
    read_permission = Perm.ANALYTICS_VIEW

    @extend_schema(
        parameters=[_days, OpenApiParameter("platform", str)], responses=OpenApiTypes.OBJECT
    )
    def get(self, request: Request, org_id: str) -> Response:
        rows = services.posts_with_metrics(
            self.organization,
            days=_days_param(request),
            platform=request.query_params.get("platform"),
        )
        return Response({"results": rows})


class AnalyticsTrendView(OrganizationScopedMixin):
    read_permission = Perm.ANALYTICS_VIEW

    @extend_schema(
        parameters=[
            _days,
            OpenApiParameter("platform", str, required=True),
            OpenApiParameter("metric", str, required=True),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request, org_id: str) -> Response:
        platform = request.query_params.get("platform", "")
        metric = request.query_params.get("metric", "")
        if not platform or not metric:
            raise serializers.ValidationError({"detail": "platform and metric are required."})
        points = services.trend(
            self.organization, metric=metric, platform=platform, days=_days_param(request)
        )
        return Response({"platform": platform, "metric": metric, "points": points})


class AnalyticsRefreshView(OrganizationScopedMixin):
    """Fetch fresh metrics now (per-post cooldown applies)."""

    read_permission = Perm.ANALYTICS_VIEW
    write_permission = Perm.ANALYTICS_VIEW

    @extend_schema(
        request=None,
        responses=inline_serializer("MetricsRefreshed", {"snapshots": serializers.IntegerField()}),
    )
    def post(self, request: Request, org_id: str) -> Response:
        return Response({"snapshots": services.refresh_org(self.organization)})


class EvidenceSerializer(serializers.ModelSerializer[RecommendationEvidence]):
    class Meta:
        model = RecommendationEvidence
        fields = [
            "description",
            "platform",
            "metric_key",
            "value",
            "baseline",
            "sample_size",
            "published_post",
        ]
        read_only_fields = fields


class RecommendationSerializer(serializers.ModelSerializer[MarketingRecommendation]):
    evidence = EvidenceSerializer(many=True, read_only=True)
    decided_by_email = serializers.EmailField(
        source="decided_by.email", read_only=True, default=None
    )

    class Meta:
        model = MarketingRecommendation
        fields = [
            "id",
            "kind",
            "priority",
            "title",
            "observation",
            "rationale",
            "suggested_action",
            "uncertainty",
            "link",
            "status",
            "uses_simulated_data",
            "generated_at",
            "decided_by_email",
            "decided_at",
            "evidence",
        ]
        read_only_fields = fields


class RecommendationViewSet(
    OrganizationScopedViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin
):
    model = MarketingRecommendation
    serializer_class = RecommendationSerializer
    read_permission = Perm.RECOMMENDATIONS_VIEW
    write_permission = Perm.RECOMMENDATIONS_MANAGE

    def get_queryset(self) -> Any:
        qs = super().get_queryset().prefetch_related("evidence").select_related("decided_by")
        return qs.filter(status=self.request.query_params.get("status", "new"))

    def _decide(self, status: str) -> Response:
        rec = self.get_object()
        rec.status = status
        rec.decided_by = self.request.user
        rec.decided_at = timezone.now()
        rec.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
        audit.record(
            f"recommendation.{status}",
            organization=self.organization,
            actor=self.request.user,
            target=rec,
            metadata={"kind": rec.kind},
        )
        return Response(self.get_serializer(rec).data)

    @extend_schema(request=None, responses=RecommendationSerializer)
    @action(detail=True, methods=["post"])
    def accept(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._decide(MarketingRecommendation.Status.ACCEPTED)

    @extend_schema(request=None, responses=RecommendationSerializer)
    @action(detail=True, methods=["post"])
    def dismiss(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._decide(MarketingRecommendation.Status.DISMISSED)

    @extend_schema(
        request=None,
        responses=inline_serializer(
            "RecommendationsRefreshed",
            {
                "created": serializers.IntegerField(),
                "updated": serializers.IntegerField(),
                "resolved": serializers.IntegerField(),
            },
        ),
    )
    @action(detail=False, methods=["post"])
    def refresh(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(recommendations.generate(self.organization))
