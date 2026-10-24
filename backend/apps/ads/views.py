from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.ai.serializers import AIWorkflowRunSerializer
from apps.ai.workflows import start_workflow
from apps.automation.policy import ADS_ACTIVATE, ADS_BUDGET_CHANGE, ADS_CREATE, ADS_PAUSE
from apps.automation.services import propose_ad_action
from apps.automation.views import ActionSerializer
from apps.marketing.models import Campaign
from apps.organizations.api import (
    OrganizationScopedMixin,
    OrganizationScopedViewSet,
    OrgScopedRelatedField,
)
from apps.organizations.roles import Perm
from apps.social.models import SocialAccount

from . import services, spend
from .models import Ad, AdAccount, AdCampaign, AdInsight, AdSet, AdSyncRun
from .validation import validate
from .workflows import GENERATE_DRAFT

# --- Ad accounts ----------------------------------------------------------------------------


class AdSyncRunSerializer(serializers.ModelSerializer[AdSyncRun]):
    class Meta:
        model = AdSyncRun
        fields = ["id", "trigger", "status", "started_at", "finished_at", "counts", "errors"]
        read_only_fields = fields


class AdAccountSerializer(serializers.ModelSerializer[AdAccount]):
    is_usable = serializers.BooleanField(read_only=True)
    spend_this_month = serializers.SerializerMethodField()
    recent_syncs = serializers.SerializerMethodField()

    class Meta:
        model = AdAccount
        fields = [
            "id",
            "platform",
            "external_id",
            "name",
            "currency",
            "timezone_name",
            "account_status",
            "status",
            "is_mock",
            "is_usable",
            "last_synced_at",
            "last_sync_status",
            "last_error",
            "connected_at",
            "meta_connection",
            "spend_this_month",
            "recent_syncs",
        ]
        read_only_fields = fields

    def get_spend_this_month(self, obj: AdAccount) -> str:
        first = timezone.now().date().replace(day=1)
        total = obj.insights.filter(date__gte=first).aggregate(s=Sum("spend"))["s"]
        return f"{total or Decimal(0):.2f}"  # money is a string in the API

    @extend_schema_field(AdSyncRunSerializer(many=True))
    def get_recent_syncs(self, obj: AdAccount) -> Any:
        return AdSyncRunSerializer(obj.sync_runs.all()[:5], many=True).data


class AdAccountViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
):
    model = AdAccount
    serializer_class = AdAccountSerializer
    read_permission = Perm.ADS_VIEW
    write_permission = Perm.ADS_MANAGE

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        if self.request.query_params.get("include_disconnected") != "true":
            qs = qs.exclude(status=AdAccount.Status.DISCONNECTED)
        return qs

    def perform_destroy(self, instance: AdAccount) -> None:
        services.disconnect_ad_account(instance, actor=self.request.user)

    @extend_schema(request=None, responses=AdSyncRunSerializer)
    @action(detail=True, methods=["post"])
    def sync(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        account = self.get_object()
        run = services.sync_account(account, trigger="manual")
        return Response(AdSyncRunSerializer(run).data)


# --- Campaigns ------------------------------------------------------------------------------


class AdSerializer(serializers.ModelSerializer[Ad]):
    class Meta:
        model = Ad
        fields = ["id", "external_id", "name", "configured_status", "effective_status"]
        read_only_fields = fields


class AdSetSerializer(serializers.ModelSerializer[AdSet]):
    ads = AdSerializer(many=True, read_only=True)

    class Meta:
        model = AdSet
        fields = [
            "id",
            "external_id",
            "name",
            "configured_status",
            "effective_status",
            "optimization_goal",
            "targeting",
            "start_time",
            "end_time",
            "ads",
        ]
        read_only_fields = fields


class IssueSerializer(serializers.Serializer[Any]):
    field = serializers.CharField()
    message = serializers.CharField()


class MetricsSerializer(serializers.Serializer[Any]):
    days = serializers.IntegerField()
    spend = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    impressions = serializers.IntegerField(allow_null=True)
    reach = serializers.IntegerField(allow_null=True)
    clicks = serializers.IntegerField(allow_null=True)
    ctr = serializers.DecimalField(max_digits=10, decimal_places=4, allow_null=True)
    cpc = serializers.DecimalField(max_digits=14, decimal_places=4, allow_null=True)


def _metrics(qs: Any, days: int) -> dict[str, Any]:
    since = timezone.now().date() - timedelta(days=days - 1)
    agg = qs.filter(date__gte=since).aggregate(
        spend=Sum("spend"), impressions=Sum("impressions"), reach=Sum("reach"), clicks=Sum("clicks")
    )
    impressions, clicks, total = agg["impressions"], agg["clicks"], agg["spend"]
    return {
        "days": days,
        "spend": total,
        "impressions": impressions,
        "reach": agg["reach"],
        "clicks": clicks,
        # Ratios only when both parts were reported (missing stays missing).
        "ctr": (Decimal(clicks) * 100 / impressions).quantize(Decimal("0.0001"))
        if clicks is not None and impressions
        else None,
        "cpc": (total / clicks).quantize(Decimal("0.0001"))
        if total is not None and clicks
        else None,
    }


class AdCampaignSerializer(serializers.ModelSerializer[AdCampaign]):
    ad_account_name = serializers.CharField(source="ad_account.name", read_only=True)
    currency = serializers.CharField(source="ad_account.currency", read_only=True)
    is_mock = serializers.BooleanField(source="ad_account.is_mock", read_only=True)
    is_approved = serializers.BooleanField(read_only=True)
    approved_by_email = serializers.EmailField(
        source="approved_by.email", read_only=True, default=None
    )
    issues = serializers.SerializerMethodField()
    metrics_7d = serializers.SerializerMethodField()
    metrics_30d = serializers.SerializerMethodField()

    class Meta:
        model = AdCampaign
        fields = [
            "id",
            "ad_account",
            "ad_account_name",
            "currency",
            "is_mock",
            "external_id",
            "name",
            "objective",
            "state",
            "source",
            "configured_status",
            "effective_status",
            "daily_budget",
            "lifetime_budget",
            "special_ad_categories",
            "spec",
            "marketing_campaign",
            "ai_run",
            "ai_notes",
            "is_mock_ai",
            "revision",
            "is_approved",
            "approved_by_email",
            "approved_at",
            "progress",
            "activated_at",
            "paused_at",
            "last_error",
            "last_synced_at",
            "created_at",
            "issues",
            "metrics_7d",
            "metrics_30d",
        ]
        read_only_fields = fields

    @extend_schema_field(IssueSerializer(many=True))
    def get_issues(self, obj: AdCampaign) -> list[dict[str, str]]:
        if obj.state not in (
            AdCampaign.State.DRAFT,
            AdCampaign.State.APPROVED,
            AdCampaign.State.FAILED,
        ):
            return []
        return [{"field": i.field, "message": i.message} for i in validate(obj)]

    @extend_schema_field(MetricsSerializer)
    def get_metrics_7d(self, obj: AdCampaign) -> Any:
        return MetricsSerializer(_metrics(obj.insights.all(), 7)).data

    @extend_schema_field(MetricsSerializer)
    def get_metrics_30d(self, obj: AdCampaign) -> Any:
        return MetricsSerializer(_metrics(obj.insights.all(), 30)).data


class AdCampaignDetailSerializer(AdCampaignSerializer):
    ad_sets = AdSetSerializer(many=True, read_only=True)
    actions = serializers.SerializerMethodField()

    class Meta(AdCampaignSerializer.Meta):
        fields = [*AdCampaignSerializer.Meta.fields, "ad_sets", "actions"]
        read_only_fields = fields

    @extend_schema_field(ActionSerializer(many=True))
    def get_actions(self, obj: AdCampaign) -> Any:
        return ActionSerializer(obj.automation_actions.all()[:20], many=True).data


class DraftWriteSerializer(serializers.Serializer[Any]):
    ad_account = OrgScopedRelatedField(AdAccount, required=False)
    name = serializers.CharField(max_length=200, required=False)
    objective = serializers.ChoiceField(choices=AdCampaign.Objective.choices, required=False)
    daily_budget = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False
    )
    special_ad_categories = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, max_length=5
    )
    spec = serializers.DictField(required=False)
    marketing_campaign = OrgScopedRelatedField(Campaign, required=False, allow_null=True)

    def validate_spec(self, value: dict[str, Any]) -> dict[str, Any]:
        allowed = {"targeting", "creative", "schedule"}
        if set(value) - allowed or not all(isinstance(value.get(k, {}), dict) for k in allowed):
            raise serializers.ValidationError("Use targeting, creative and schedule objects.")
        return value


class GenerateDraftSerializer(serializers.Serializer[None]):
    ad_account = OrgScopedRelatedField(AdAccount)
    brief = serializers.CharField(min_length=5, max_length=2000)
    page_account = OrgScopedRelatedField(SocialAccount, required=False, allow_null=True)
    link = serializers.URLField(required=False, allow_blank=True)
    daily_budget = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True
    )
    marketing_campaign = OrgScopedRelatedField(Campaign, required=False, allow_null=True)


class BudgetSerializer(serializers.Serializer[None]):
    daily_budget = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))


class ActionResultSerializer(serializers.Serializer[Any]):
    campaign = AdCampaignDetailSerializer()
    action = ActionSerializer()


class AdCampaignViewSet(
    OrganizationScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
):
    model = AdCampaign
    serializer_class = AdCampaignSerializer
    read_permission = Perm.ADS_VIEW
    write_permission = Perm.ADS_DRAFT
    action_permissions = {
        "approve": Perm.ADS_MANAGE,
        "create_on_platform": Perm.ADS_MANAGE,
        "activate": Perm.ADS_MANAGE,
        "pause": Perm.ADS_MANAGE,
        "budget": Perm.ADS_MANAGE,
        "validate": Perm.ADS_VIEW,
    }
    throttle_scope = "ai"

    def get_throttles(self) -> list[Any]:
        return [ScopedRateThrottle()] if self.action == "generate" else []

    def get_serializer_class(self) -> Any:
        return AdCampaignDetailSerializer if self.action != "list" else AdCampaignSerializer

    def get_queryset(self) -> Any:
        qs = (
            super()
            .get_queryset()
            .select_related("ad_account", "approved_by")
            .prefetch_related("ad_sets__ads")
        )
        params = self.request.query_params
        if account := params.get("ad_account"):
            qs = qs.filter(ad_account_id=account)
        if state := params.get("state"):
            qs = qs.filter(state__in=state.split(","))
        if params.get("include_removed") != "true":
            qs = qs.exclude(state=AdCampaign.State.REMOVED)
        return qs

    def perform_destroy(self, instance: AdCampaign) -> None:
        services.delete_draft(instance, actor=self.request.user)

    def _result(self, campaign: AdCampaign, action_obj: Any) -> Response:
        campaign.refresh_from_db()
        return Response(
            {
                "campaign": AdCampaignDetailSerializer(campaign).data,
                "action": ActionSerializer(action_obj).data,
            }
        )

    @extend_schema(request=DraftWriteSerializer, responses={201: AdCampaignDetailSerializer})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = DraftWriteSerializer(data=request.data, context=self.get_serializer_context())
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        account = data.pop("ad_account", None)
        if account is None:
            raise serializers.ValidationError({"ad_account": "Choose an ad account."})
        data.setdefault("name", "New campaign")
        campaign = services.create_draft(
            self.organization, actor=request.user, ad_account=account, fields=data
        )
        return Response(AdCampaignDetailSerializer(campaign).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=DraftWriteSerializer, responses=AdCampaignDetailSerializer)
    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        campaign = self.get_object()
        payload = DraftWriteSerializer(data=request.data, context=self.get_serializer_context())
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        data.pop("ad_account", None)  # an existing draft can't move accounts
        campaign = services.update_draft(campaign, actor=request.user, fields=data)
        return Response(AdCampaignDetailSerializer(campaign).data)

    @extend_schema(request=GenerateDraftSerializer, responses={202: AIWorkflowRunSerializer})
    @action(detail=False, methods=["post"])
    def generate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = GenerateDraftSerializer(data=request.data, context=self.get_serializer_context())
        payload.is_valid(raise_exception=True)
        v = payload.validated_data
        run = start_workflow(
            self.organization,
            GENERATE_DRAFT,
            user=request.user,
            payload={
                "ad_account_id": str(v["ad_account"].pk),
                "brief": v["brief"],
                "page_account_id": str(v["page_account"].pk) if v.get("page_account") else None,
                "link": v.get("link") or "",
                "daily_budget": str(v["daily_budget"]) if v.get("daily_budget") else None,
                "marketing_campaign_id": str(v["marketing_campaign"].pk)
                if v.get("marketing_campaign")
                else None,
            },
        )
        return Response(AIWorkflowRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=None, responses=IssueSerializer(many=True))
    @action(detail=True, methods=["get"])
    def validate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        issues = validate(self.get_object())
        return Response([{"field": i.field, "message": i.message} for i in issues])

    @extend_schema(request=None, responses=AdCampaignDetailSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        campaign = services.approve_draft(self.get_object(), actor=request.user)
        return Response(AdCampaignDetailSerializer(campaign).data)

    def _propose(self, action_type: str, payload: dict[str, Any] | None = None) -> Response:
        campaign = self.get_object()
        action_obj = propose_ad_action(
            self.organization,
            campaign=campaign,
            action_type=action_type,
            initiated_by="user",
            workflow="manual",
            payload=payload,
            membership=self.membership,
        )
        return self._result(campaign, action_obj)

    @extend_schema(request=None, responses=ActionResultSerializer)
    @action(detail=True, methods=["post"], url_path="create-on-platform")
    def create_on_platform(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._propose(ADS_CREATE)

    @extend_schema(request=None, responses=ActionResultSerializer)
    @action(detail=True, methods=["post"])
    def activate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._propose(ADS_ACTIVATE)

    @extend_schema(request=None, responses=ActionResultSerializer)
    @action(detail=True, methods=["post"])
    def pause(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._propose(ADS_PAUSE)

    @extend_schema(request=BudgetSerializer, responses=ActionResultSerializer)
    @action(detail=True, methods=["post"])
    def budget(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = BudgetSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._propose(
            ADS_BUDGET_CHANGE, {"daily_budget": str(payload.validated_data["daily_budget"])}
        )


# --- Insights summary (analytics layer) -----------------------------------------------------


class AdDailyPointSerializer(serializers.Serializer[Any]):
    date = serializers.DateField()
    spend = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    clicks = serializers.IntegerField(allow_null=True)
    impressions = serializers.IntegerField(allow_null=True)


class AdCurrencyTotalsSerializer(serializers.Serializer[Any]):
    currency = serializers.CharField()
    totals = MetricsSerializer()
    spend_this_month = serializers.DecimalField(max_digits=14, decimal_places=2)
    active_daily_budget = serializers.DecimalField(max_digits=14, decimal_places=2)
    is_mock = serializers.BooleanField()
    daily = AdDailyPointSerializer(many=True)


class AdInsightsSummarySerializer(serializers.Serializer[Any]):
    days = serializers.IntegerField()
    currencies = AdCurrencyTotalsSerializer(many=True)


class AdInsightsSummaryView(OrganizationScopedMixin):
    read_permission = Perm.ADS_VIEW

    @extend_schema(responses=AdInsightsSummarySerializer, tags=["ads"])
    def get(self, request: Request, org_id: str) -> Response:
        try:
            days = max(1, min(int(request.query_params.get("days", 30)), 90))
        except ValueError:
            days = 30
        since = timezone.now().date() - timedelta(days=days - 1)
        org = self.organization
        insights = AdInsight.objects.filter(
            organization=org, ad_account__status=AdAccount.Status.CONNECTED
        )
        out = []
        for currency in sorted(set(insights.values_list("currency", flat=True))):
            rows = insights.filter(currency=currency)
            daily = (
                rows.filter(date__gte=since)
                .values("date")
                .annotate(spend=Sum("spend"), clicks=Sum("clicks"), impressions=Sum("impressions"))
                .order_by("date")
            )
            out.append(
                {
                    "currency": currency,
                    "totals": _metrics(rows, days),
                    "spend_this_month": spend.month_spend(org, currency),
                    "active_daily_budget": spend.active_daily_total(org, currency),
                    "is_mock": rows.filter(is_mock=True).exists(),
                    "daily": list(daily),
                }
            )
        return Response(AdInsightsSummarySerializer({"days": days, "currencies": out}).data)
