from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.ai.serializers import AIWorkflowRunSerializer
from apps.audit import services as audit
from apps.core.errors import Conflict
from apps.organizations.api import OrganizationScopedViewSet
from apps.organizations.roles import Perm

from . import services
from .models import Campaign, MarketingPlan
from .serializers import (
    CampaignSerializer,
    GeneratePlanSerializer,
    MarketingPlanListSerializer,
    MarketingPlanSerializer,
    RevisePlanSerializer,
)


class MarketingPlanViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    model = MarketingPlan
    read_permission = Perm.STRATEGY_VIEW
    write_permission = Perm.STRATEGY_EDIT
    throttle_scope = "ai"

    def get_throttles(self) -> list[Any]:
        if self.action == "generate":
            from rest_framework.throttling import ScopedRateThrottle

            return [ScopedRateThrottle()]
        return []

    def get_serializer_class(self) -> Any:
        return MarketingPlanListSerializer if self.action == "list" else MarketingPlanSerializer

    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("created_by")
        if s := self.request.query_params.get("status"):
            qs = qs.filter(status=s)
        return qs

    @extend_schema(request=GeneratePlanSerializer, responses={202: AIWorkflowRunSerializer})
    @action(detail=False, methods=["post"])
    def generate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Start asynchronous plan generation; poll the returned AI run."""
        payload = GeneratePlanSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        run = services.request_plan_generation(
            self.organization, user=request.user, **payload.validated_data
        )
        return Response(AIWorkflowRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=RevisePlanSerializer, responses={201: MarketingPlanSerializer})
    @action(detail=True, methods=["post"])
    def revise(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Save edited content as a new version (history is never overwritten)."""
        payload = RevisePlanSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        plan = services.revise_plan(
            self.get_object(),
            content=payload.validated_data["content"],
            user=request.user,
            request=request._request,
        )
        return Response(MarketingPlanSerializer(plan).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=MarketingPlanSerializer)
    @action(detail=True, methods=["post"])
    def activate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        plan = services.activate_plan(
            self.get_object(), user=request.user, request=request._request
        )
        return Response(MarketingPlanSerializer(plan).data)


class CampaignViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    model = Campaign
    serializer_class = CampaignSerializer
    read_permission = Perm.CAMPAIGN_VIEW
    write_permission = Perm.CAMPAIGN_EDIT

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        if s := self.request.query_params.get("status"):
            qs = qs.filter(status__in=s.split(","))
        return qs

    def perform_create(self, serializer: Any) -> None:
        campaign = serializer.save(organization=self.organization, created_by=self.request.user)
        audit.record(
            "campaign.created",
            organization=self.organization,
            actor=self.request.user,
            target=campaign,
        )

    def perform_update(self, serializer: Any) -> None:
        campaign = serializer.save()
        audit.record(
            "campaign.updated",
            organization=self.organization,
            actor=self.request.user,
            target=campaign,
            metadata={"fields": sorted(serializer.validated_data)},
        )

    def perform_destroy(self, instance: Campaign) -> None:
        if instance.content_items.exclude(status="archived").exists():
            raise Conflict(
                "Move or archive this campaign's content before deleting it, "
                "or archive the campaign."
            )
        audit.record(
            "campaign.deleted",
            organization=self.organization,
            actor=self.request.user,
            target=instance,
            metadata={"name": instance.name},
        )
        instance.delete()
