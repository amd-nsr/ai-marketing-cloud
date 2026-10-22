from typing import Any
from zoneinfo import available_timezones

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.organizations.api import OrganizationScopedMixin, OrganizationScopedViewSet
from apps.organizations.roles import Perm
from apps.social.models import SocialAccount

from . import policy as engine
from . import services
from .models import AutomationAction, AutomationPolicy, AutonomyMode


class ScopedAccounts(serializers.PrimaryKeyRelatedField):  # type: ignore[type-arg]
    def get_queryset(self) -> Any:
        view = self.context.get("view")
        org = getattr(view, "organization", None)
        if org is None:
            return SocialAccount.objects.none()
        return SocialAccount.objects.filter(organization=org).exclude(status="disconnected")


class PolicySerializer(serializers.ModelSerializer[AutomationPolicy]):
    allowed_accounts = ScopedAccounts(many=True, required=False)
    allowed_weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6), required=False, max_length=7
    )
    paused_by_email = serializers.EmailField(source="paused_by.email", read_only=True, default=None)
    updated_by_email = serializers.EmailField(
        source="updated_by.email", read_only=True, default=None
    )

    class Meta:
        model = AutomationPolicy
        fields = [
            "mode",
            "paused",
            "paused_at",
            "paused_by_email",
            "auto_publish_enabled",
            "allowed_accounts",
            "allowed_weekdays",
            "window_start_hour",
            "window_end_hour",
            "timezone",
            "max_automated_posts_per_day",
            "auto_generate_drafts",
            "max_generated_drafts_per_week",
            "version",
            "updated_by_email",
            "updated_at",
        ]
        read_only_fields = [
            "paused",
            "paused_at",
            "paused_by_email",
            "version",
            "updated_by_email",
            "updated_at",
        ]
        extra_kwargs = {
            "window_start_hour": {"min_value": 0, "max_value": 23},
            "window_end_hour": {"min_value": 1, "max_value": 24},
            "max_automated_posts_per_day": {"min_value": 0, "max_value": 25},
            "max_generated_drafts_per_week": {"min_value": 0, "max_value": 30},
        }

    def validate_timezone(self, value: str) -> str:
        if value not in available_timezones():
            raise serializers.ValidationError("Unknown time zone.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start = attrs.get("window_start_hour", getattr(self.instance, "window_start_hour", 8))
        end = attrs.get("window_end_hour", getattr(self.instance, "window_end_hour", 20))
        if start >= end:
            raise serializers.ValidationError(
                {"window_end_hour": "The window must end after it starts."}
            )
        mode = attrs.get("mode", getattr(self.instance, "mode", AutonomyMode.MANUAL))
        if attrs.get("auto_publish_enabled") and mode != AutonomyMode.AUTOMATIC:
            raise serializers.ValidationError(
                {"auto_publish_enabled": "Only available in automatic mode."}
            )
        if "allowed_weekdays" in attrs:
            attrs["allowed_weekdays"] = sorted(set(attrs["allowed_weekdays"]))
        return attrs


class ActionSerializer(serializers.ModelSerializer[AutomationAction]):
    content_title = serializers.CharField(source="content_item.title", read_only=True, default=None)
    content_platform = serializers.CharField(
        source="content_item.platform", read_only=True, default=None
    )
    content_caption = serializers.CharField(
        source="content_item.current_version.caption", read_only=True, default=None
    )
    account_name = serializers.CharField(source="social_account.name", read_only=True, default=None)
    account_is_mock = serializers.BooleanField(
        source="social_account.is_mock", read_only=True, default=None
    )
    approved_by_email = serializers.EmailField(
        source="approved_by.email", read_only=True, default=None
    )
    publishing_job_status = serializers.CharField(
        source="publishing_job.status", read_only=True, default=None
    )

    class Meta:
        model = AutomationAction
        fields = [
            "id",
            "action_type",
            "status",
            "workflow",
            "initiated_by",
            "content_item",
            "content_title",
            "content_platform",
            "content_caption",
            "social_account",
            "account_name",
            "account_is_mock",
            "scheduled_for",
            "payload",
            "decision",
            "decision_reasons",
            "policy_version",
            "mode_at_decision",
            "attempts",
            "error",
            "publishing_job",
            "publishing_job_status",
            "ai_run",
            "approved_by_email",
            "approved_at",
            "executed_at",
            "created_at",
        ]
        read_only_fields = fields


class PolicyView(OrganizationScopedMixin):
    read_permission = Perm.AUTOMATION_VIEW
    write_permission = Perm.AUTOMATION_MANAGE

    @extend_schema(responses=PolicySerializer)
    def get(self, request: Request, org_id: str) -> Response:
        policy = engine.get_policy(self.organization)
        return Response(PolicySerializer(policy, context={"view": self}).data)

    @extend_schema(request=PolicySerializer, responses=PolicySerializer)
    def patch(self, request: Request, org_id: str) -> Response:
        policy = engine.get_policy(self.organization)
        serializer = PolicySerializer(
            policy, data=request.data, partial=True, context={"view": self}
        )
        serializer.is_valid(raise_exception=True)
        updated = services.update_policy(
            self.organization, actor=request.user, changes=dict(serializer.validated_data)
        )
        return Response(PolicySerializer(updated, context={"view": self}).data)


_counts = inline_serializer(
    "AutomationCounts", {"actions": serializers.IntegerField(), "jobs": serializers.IntegerField()}
)


class PolicyControlView(OrganizationScopedMixin):
    write_permission = Perm.AUTOMATION_MANAGE
    command: str = ""

    @extend_schema(request=None, responses=PolicySerializer)
    def post(self, request: Request, org_id: str) -> Response:
        if self.command == "pause":
            policy = services.pause(self.organization, actor=request.user)
        else:
            policy = services.resume(self.organization, actor=request.user)
        return Response(PolicySerializer(policy, context={"view": self}).data)


class CancelPendingView(OrganizationScopedMixin):
    write_permission = Perm.AUTOMATION_MANAGE

    @extend_schema(request=None, responses=_counts)
    def post(self, request: Request, org_id: str) -> Response:
        return Response(services.cancel_pending(self.organization, actor=request.user))


class RunNowView(OrganizationScopedMixin):
    """Run the automation workflows now instead of waiting for the scheduler."""

    write_permission = Perm.AUTOMATION_MANAGE

    @extend_schema(
        request=None,
        responses=inline_serializer("AutomationRun", {"proposed": serializers.IntegerField()}),
    )
    def post(self, request: Request, org_id: str) -> Response:
        proposed = services.run_calendar_autopublish(
            self.organization
        ) + services.run_plan_drafting(self.organization)
        return Response({"proposed": proposed})


class ActionViewSet(OrganizationScopedViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    model = AutomationAction
    serializer_class = ActionSerializer
    read_permission = Perm.AUTOMATION_VIEW
    write_permission = Perm.AUTOMATION_APPROVE

    def get_queryset(self) -> Any:
        qs = (
            super()
            .get_queryset()
            .select_related(
                "content_item",
                "content_item__current_version",
                "social_account",
                "approved_by",
                "publishing_job",
            )
        )
        if s := self.request.query_params.get("status"):
            qs = qs.filter(status__in=s.split(","))
        return qs

    @extend_schema(request=None, responses=ActionSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        result = services.approve_action(self.get_object(), approver=self.membership)
        result.refresh_from_db()
        return Response(self.get_serializer(result).data)

    @extend_schema(request=None, responses=ActionSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(
            self.get_serializer(services.reject_action(self.get_object(), actor=request.user)).data
        )

    @extend_schema(request=None, responses=ActionSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(
            self.get_serializer(services.cancel_action(self.get_object(), actor=request.user)).data
        )
