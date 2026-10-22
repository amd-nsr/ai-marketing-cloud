from typing import Any

from rest_framework import serializers

from apps.organizations.api import OrgScopedRelatedField

from .models import Campaign, MarketingPlan


class MarketingPlanListSerializer(serializers.ModelSerializer[MarketingPlan]):
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, default=None
    )
    warning_count = serializers.SerializerMethodField()

    class Meta:
        model = MarketingPlan
        fields = [
            "id",
            "version",
            "title",
            "status",
            "source",
            "horizon_weeks",
            "ai_model",
            "is_mock",
            "parent",
            "created_by_email",
            "warning_count",
            "created_at",
        ]
        read_only_fields = fields

    def get_warning_count(self, obj: MarketingPlan) -> int:
        return len(obj.quality_warnings)


class MarketingPlanSerializer(MarketingPlanListSerializer):
    class Meta(MarketingPlanListSerializer.Meta):
        fields = [
            *MarketingPlanListSerializer.Meta.fields,
            "content",
            "instructions",
            "quality_warnings",
        ]
        read_only_fields = fields


class GeneratePlanSerializer(serializers.Serializer[None]):
    horizon_weeks = serializers.IntegerField(min_value=1, max_value=12, default=4)
    instructions = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


class RevisePlanSerializer(serializers.Serializer[None]):
    content = serializers.JSONField()

    def validate_content(self, value: Any) -> Any:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Expected a plan object.")
        return value


class CampaignSerializer(serializers.ModelSerializer[Campaign]):
    platforms = serializers.ListField(
        child=serializers.ChoiceField(choices=["instagram", "facebook", "tiktok"]),
        required=False,
        max_length=3,
    )
    key_messages = serializers.ListField(
        child=serializers.CharField(max_length=300), required=False, max_length=10
    )
    plan = OrgScopedRelatedField(MarketingPlan, required=False, allow_null=True)
    content_count = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            "id",
            "name",
            "objective",
            "description",
            "status",
            "start_date",
            "end_date",
            "platforms",
            "key_messages",
            "plan",
            "content_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "content_count", "created_at", "updated_at"]

    def get_content_count(self, obj: Campaign) -> int:
        return obj.content_items.exclude(status="archived").count()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "End date must be on or after the start date."}
            )
        if "platforms" in attrs:
            attrs["platforms"] = list(dict.fromkeys(attrs["platforms"]))
        return attrs
