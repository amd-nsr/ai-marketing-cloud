import json
from typing import Any

from rest_framework import serializers

from apps.brand.models import TargetAudience
from apps.marketing.models import Campaign
from apps.organizations.api import OrgScopedRelatedField

from . import documents
from .models import (
    Approval,
    ContentAsset,
    ContentItem,
    ContentTemplate,
    ContentVersion,
    Format,
    LibraryAsset,
    Platform,
    RenderJob,
)
from .platform_rules import RULES
from .prompts import ASSIST_OPERATIONS

MAX_DOCUMENT_BYTES = 512 * 1024


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
    #: Editable design/carousel/video source (documents.py); {} removes it.
    document = serializers.JSONField(required=False)

    def validate_document(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        if len(json.dumps(value)) > MAX_DOCUMENT_BYTES:
            raise serializers.ValidationError("The design is too large to save.")
        try:
            documents.parse_document(value)  # shape only; services checks format and assets
        except documents.DocumentError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

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
            "document",
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
    version_number = serializers.IntegerField(source="version.number", read_only=True, default=None)

    class Meta:
        model = ContentAsset
        fields = [
            "id",
            "original_filename",
            "content_type",
            "size_bytes",
            "width",
            "height",
            "duration_seconds",
            "position",
            "source",
            "page_id",
            "source_hash",
            "version_number",
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
    document_kind = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    thumbnail_type = serializers.SerializerMethodField()

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
            "document_kind",
            "thumbnail_url",
            "thumbnail_type",
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
            "document_kind",
            "thumbnail_url",
            "thumbnail_type",
            "created_at",
            "updated_at",
        ]

    def get_version_count(self, obj: ContentItem) -> int:
        return obj.versions.count()

    def get_asset_count(self, obj: ContentItem) -> int:
        return obj.assets.count()

    def get_document_kind(self, obj: ContentItem) -> str | None:
        return documents.DOCUMENT_KIND_FOR_FORMAT.get(obj.format)

    def _thumbnail(self, obj: ContentItem) -> ContentAsset | None:
        """The first published media: an image, else a (rendered) video."""
        assets = list(obj.assets.all())
        return next((a for a in assets if a.content_type.startswith("image/")), None) or next(
            (a for a in assets if a.content_type.startswith("video/")), None
        )

    def get_thumbnail_url(self, obj: ContentItem) -> str | None:
        first = self._thumbnail(obj)
        return ContentAssetSerializer().get_file_url(first) if first else None

    def get_thumbnail_type(self, obj: ContentItem) -> str | None:
        first = self._thumbnail(obj)
        return first.content_type.split("/")[0] if first else None

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
    objective = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    audience = OrgScopedRelatedField(TargetAudience, required=False, allow_null=True)
    tone = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    language = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    length = serializers.ChoiceField(
        choices=["short", "medium", "long"], required=False, allow_blank=True, default=""
    )

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


class AssistSerializer(serializers.Serializer[None]):
    operation = serializers.ChoiceField(choices=sorted(ASSIST_OPERATIONS))
    field = serializers.ChoiceField(
        choices=["headline", "hook", "caption", "cta", "script", "slide", "hashtags", "text"]
    )
    text = serializers.CharField(max_length=10000, allow_blank=True)
    tone = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    language = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    instructions = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, default=""
    )
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=60), max_length=10, required=False, default=list
    )
    length = serializers.ChoiceField(
        choices=["short", "medium", "long"], required=False, allow_blank=True, default=""
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["operation"] != "draft" and not attrs["text"].strip():
            raise serializers.ValidationError({"text": "There's no text to work with yet."})
        if attrs["operation"] == "translate" and not attrs["language"].strip():
            raise serializers.ValidationError({"language": "Choose a language to translate to."})
        if attrs["operation"] == "tone" and not attrs["tone"].strip():
            raise serializers.ValidationError({"tone": "Describe the tone you want."})
        return attrs


class StoryboardSerializer(serializers.Serializer[None]):
    brief = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class DuplicateSerializer(serializers.Serializer[None]):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    platform = serializers.ChoiceField(choices=Platform.choices, required=False)
    format = serializers.ChoiceField(choices=Format.choices, required=False)
    campaign = OrgScopedRelatedField(Campaign, required=False, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        item: ContentItem = self.context["item"]
        platform = attrs.get("platform", item.platform)
        format = attrs.get("format", item.format)
        if format not in RULES[platform].formats:
            raise serializers.ValidationError(
                {"format": f"{format} is not available on {platform}."}
            )
        return attrs


class RenderUploadSerializer(serializers.Serializer[None]):
    page_id = serializers.CharField(max_length=40)
    file = serializers.FileField()


class RenderJobSerializer(serializers.ModelSerializer[RenderJob]):
    version_number = serializers.IntegerField(source="version.number", read_only=True)
    output = ContentAssetSerializer(read_only=True)

    class Meta:
        model = RenderJob
        fields = [
            "id",
            "item",
            "version_number",
            "status",
            "attempts",
            "error_code",
            "error_message",
            "output",
            "started_at",
            "finished_at",
            "created_at",
        ]
        read_only_fields = fields


class LibraryAssetSerializer(serializers.ModelSerializer[LibraryAsset]):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = LibraryAsset
        fields = [
            "id",
            "kind",
            "source",
            "title",
            "tags",
            "original_filename",
            "content_type",
            "size_bytes",
            "width",
            "height",
            "duration_seconds",
            "generation",
            "is_mock",
            "file_url",
            "created_at",
        ]
        read_only_fields = [f for f in fields if f not in {"title", "tags"}]

    def get_file_url(self, obj: LibraryAsset) -> str:
        return f"/api/v1/orgs/{obj.organization_id}/library/{obj.id}/file/"

    def validate_tags(self, value: Any) -> list[str]:
        if not isinstance(value, list) or len(value) > 20:
            raise serializers.ValidationError("Use a list of at most 20 tags.")
        from .services import _clean_tags

        return _clean_tags([str(v) for v in value])


class LibraryUploadSerializer(serializers.Serializer[None]):
    file = serializers.FileField()
    title = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    tags = serializers.ListField(
        child=serializers.CharField(max_length=40), max_length=20, required=False, default=list
    )


class GenerateImageSerializer(serializers.Serializer[None]):
    prompt = serializers.CharField(min_length=5, max_length=1000)
    visual_style = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    width = serializers.IntegerField(min_value=256, max_value=2048, default=1080)
    height = serializers.IntegerField(min_value=256, max_value=2048, default=1080)


class ContentTemplateSerializer(serializers.ModelSerializer[ContentTemplate]):
    built_in = serializers.SerializerMethodField()

    class Meta:
        model = ContentTemplate
        fields = ["id", "name", "description", "kind", "document", "built_in", "created_at"]
        read_only_fields = ["id", "kind", "built_in", "created_at"]

    def get_built_in(self, obj: ContentTemplate) -> bool:
        return False

    def validate_document(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or len(json.dumps(value)) > MAX_DOCUMENT_BYTES:
            raise serializers.ValidationError("Invalid or too large.")
        try:
            doc = documents.parse_document(value)
        except documents.DocumentError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if doc is None:
            raise serializers.ValidationError("A template needs a design.")
        return doc.model_dump(mode="json")


class BuiltInTemplateSerializer(serializers.Serializer[None]):
    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    kind = serializers.CharField()
    document = serializers.JSONField()
    built_in = serializers.BooleanField()


class CapabilitySerializer(serializers.Serializer[dict[str, Any]]):
    available = serializers.BooleanField()
    is_mock = serializers.BooleanField()
    provider = serializers.CharField(allow_null=True)
    note = serializers.CharField()


class StudioCapabilitiesSerializer(serializers.Serializer[dict[str, Any]]):
    text_generation = CapabilitySerializer()
    image_generation = CapabilitySerializer()
    video_rendering = CapabilitySerializer()
    ai_video_generation = CapabilitySerializer()
    ai_voiceover = CapabilitySerializer()
    max_media_upload_bytes = serializers.IntegerField()
    max_image_upload_bytes = serializers.IntegerField()
