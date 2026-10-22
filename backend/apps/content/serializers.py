from typing import Any

from rest_framework import serializers

from apps.marketing.models import Campaign
from apps.organizations.api import OrgScopedRelatedField

from .models import Approval, ContentAsset, ContentItem, ContentVersion, Format, Platform
from .platform_rules import RULES


class SlideSerializer(serializers.Serializer[None]):
    title = serializers.CharField(max_length=200, allow_blank=True)
    body = serializers.CharField(max_length=1000, allow_blank=True)


class VersionFieldsSerializer(serializers.Serializer[None]):
    """Editable text fields of a content version (all optional; omitted = unchanged)."""

    headline = serializers.CharField(max_length=200, required=False, allow_blank=True)
    hook = serializers.CharField(max_length=300, required=False, allow_blank=True)
    caption = serializers.CharField(max_length=10000, required=False, allow_blank=True)
    cta = serializers.CharField(max_length=200, required=False, allow_blank=True)
    hashtags = serializers.ListField(
        child=serializers.CharField(max_length=100), max_length=60, required=False
    )
    script = serializers.CharField(max_length=10000, required=False, allow_blank=True)
    slides = SlideSerializer(many=True, required=False)
    creative_brief = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    alt_text = serializers.CharField(max_length=1000, required=False, allow_blank=True)

    def validate_slides(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(value) > 20:
            raise serializers.ValidationError("Use at most 20 slides.")
        return [dict(s) for s in value]


class ContentVersionSerializer(serializers.ModelSerializer[ContentVersion]):
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, default=None
    )

    class Meta:
        model = ContentVersion
        fields = [
            "id",
            "number",
            "headline",
            "hook",
            "caption",
            "cta",
            "hashtags",
            "script",
            "slides",
            "creative_brief",
            "alt_text",
            "source",
            "ai_model",
            "is_mock",
            "checks",
            "note",
            "created_by_email",
            "created_at",
        ]
        read_only_fields = fields


class ContentAssetSerializer(serializers.ModelSerializer[ContentAsset]):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ContentAsset
        fields = [
            "id",
            "original_filename",
            "content_type",
            "size_bytes",
            "width",
            "height",
            "position",
            "file_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_file_url(self, obj: ContentAsset) -> str:
        return f"/api/v1/orgs/{obj.organization_id}/content/{obj.item_id}/assets/{obj.id}/file/"


class ContentItemSerializer(serializers.ModelSerializer[ContentItem]):
    campaign = OrgScopedRelatedField(Campaign, required=False, allow_null=True)
    campaign_name = serializers.CharField(source="campaign.name", read_only=True, default=None)
    current_version = ContentVersionSerializer(read_only=True)
    version_count = serializers.SerializerMethodField()
    asset_count = serializers.SerializerMethodField()
    pending_approval_id = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = [
            "id",
            "title",
            "platform",
            "format",
            "status",
            "campaign",
            "campaign_name",
            "brief",
            "planned_for",
            "current_version",
            "version_count",
            "asset_count",
            "pending_approval_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "platform",
            "format",
            "status",
            "current_version",
            "version_count",
            "asset_count",
            "pending_approval_id",
            "created_at",
            "updated_at",
        ]

    def get_version_count(self, obj: ContentItem) -> int:
        return obj.versions.count()

    def get_asset_count(self, obj: ContentItem) -> int:
        return obj.assets.count()

    def get_pending_approval_id(self, obj: ContentItem) -> str | None:
        pending = obj.approvals.filter(status=Approval.Status.PENDING).values_list("id", flat=True)
        first = pending.first()
        return str(first) if first else None


class ContentItemCreateSerializer(VersionFieldsSerializer):
    title = serializers.CharField(max_length=200)
    platform = serializers.ChoiceField(choices=Platform.choices)
    format = serializers.ChoiceField(choices=Format.choices, default=Format.POST)
    campaign = OrgScopedRelatedField(Campaign, required=False, allow_null=True)
    brief = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    planned_for = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["format"] not in RULES[attrs["platform"]].formats:
            raise serializers.ValidationError(
                {"format": f"{attrs['format']} is not available on {attrs['platform']}."}
            )
        return attrs


class TargetSerializer(serializers.Serializer[None]):
    platform = serializers.ChoiceField(choices=Platform.choices)
    format = serializers.ChoiceField(choices=Format.choices)


class GenerateContentSerializer(serializers.Serializer[None]):
    brief = serializers.CharField(max_length=2000)
    targets = TargetSerializer(many=True)
    campaign = OrgScopedRelatedField(Campaign, required=False, allow_null=True)

    def validate_targets(self, value: list[dict[str, str]]) -> list[dict[str, str]]:
        if not 1 <= len(value) <= 6:
            raise serializers.ValidationError("Choose between 1 and 6 platform/format targets.")
        unique = {(t["platform"], t["format"]) for t in value}
        if len(unique) != len(value):
            raise serializers.ValidationError("Each platform/format combination only once.")
        for t in value:
            if t["format"] not in RULES[t["platform"]].formats:
                raise serializers.ValidationError(
                    f"{t['format']} is not available on {t['platform']}."
                )
        return [dict(t) for t in value]


class RegenerateSerializer(serializers.Serializer[None]):
    instructions = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


class AssetUploadSerializer(serializers.Serializer[None]):
    file = serializers.FileField()


class SubmitSerializer(serializers.Serializer[None]):
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class DecisionSerializer(serializers.Serializer[None]):
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class ApprovalSerializer(serializers.ModelSerializer[Approval]):
    item_title = serializers.CharField(source="item.title", read_only=True)
    item_platform = serializers.CharField(source="item.platform", read_only=True)
    item_format = serializers.CharField(source="item.format", read_only=True)
    item_status = serializers.CharField(source="item.status", read_only=True)
    version = ContentVersionSerializer(read_only=True)
    requested_by_email = serializers.EmailField(
        source="requested_by.email", read_only=True, default=None
    )
    decided_by_email = serializers.EmailField(
        source="decided_by.email", read_only=True, default=None
    )
    is_current_version = serializers.SerializerMethodField()

    class Meta:
        model = Approval
        fields = [
            "id",
            "item",
            "item_title",
            "item_platform",
            "item_format",
            "item_status",
            "version",
            "status",
            "request_note",
            "requested_by_email",
            "decided_by_email",
            "decided_at",
            "comment",
            "is_current_version",
            "created_at",
        ]
        read_only_fields = fields

    def get_is_current_version(self, obj: Approval) -> bool:
        return obj.item.current_version_id == obj.version_id
